#!/usr/bin/env python3
"""Small, read-only AWS metadata collector. Credentials stay with the AWS CLI."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
COMMAND_TIMEOUT = 45
MAX_OUTPUT_BYTES = 10 * 1024 * 1024
MAX_ERROR_BYTES = 64 * 1024

# Queries are deliberately explicit. Never replace these with full API responses.
# The second projection below also rejects unexpected fields in CLI output.
COLLECTIONS = {
    "ec2": {
        "operation": ["ec2", "describe-instances"],
        "query": "Reservations[].Instances[].{instance_id:InstanceId,state:State.Name,instance_type:InstanceType,vpc_id:VpcId,subnet_id:SubnetId,availability_zone:Placement.AvailabilityZone,public_ip:PublicIpAddress,private_ip:PrivateIpAddress,security_group_ids:SecurityGroups[].GroupId}",
        "fields": {"instance_id": str, "state": str, "instance_type": str, "vpc_id": str, "subnet_id": str, "availability_zone": str, "public_ip": str, "private_ip": str, "security_group_ids": list},
    },
    "vpc": {
        "operation": ["ec2", "describe-vpcs"],
        "query": "Vpcs[].{vpc_id:VpcId,state:State,cidr:CidrBlock,is_default:IsDefault}",
        "fields": {"vpc_id": str, "state": str, "cidr": str, "is_default": bool},
    },
    "lambda": {
        "operation": ["lambda", "list-functions"],
        "query": "Functions[].{name:FunctionName,arn:FunctionArn,runtime:Runtime,package_type:PackageType,role_arn:Role,memory_mb:MemorySize,timeout_seconds:Timeout,last_modified:LastModified}",
        "fields": {"name": str, "arn": str, "runtime": str, "package_type": str, "role_arn": str, "memory_mb": int, "timeout_seconds": int, "last_modified": str},
    },
    "rds": {
        "operation": ["rds", "describe-db-instances"],
        "query": "DBInstances[].{identifier:DBInstanceIdentifier,arn:DBInstanceArn,engine:Engine,engine_version:EngineVersion,status:DBInstanceStatus,instance_class:DBInstanceClass,vpc_id:DBSubnetGroup.VpcId,multi_az:MultiAZ,publicly_accessible:PubliclyAccessible}",
        "fields": {"identifier": str, "arn": str, "engine": str, "engine_version": str, "status": str, "instance_class": str, "vpc_id": str, "multi_az": bool, "publicly_accessible": bool},
    },
    "ecs": {
        "operation": ["ecs", "list-clusters"],
        "query": "clusterArns[].{arn:@}",
        "fields": {"arn": str},
    },
    "dynamodb": {
        "operation": ["dynamodb", "list-tables"],
        "query": "TableNames[].{name:@}",
        "fields": {"name": str},
    },
    "sqs": {
        "operation": ["sqs", "list-queues", "--page-size", "1000"],
        "query": "QueueUrls[].{url:@} || `[]`",
        "fields": {"url": str},
    },
    "cloudformation": {
        "operation": ["cloudformation", "list-stacks"],
        "query": "StackSummaries[].{name:StackName,id:StackId,status:StackStatus,created_at:CreationTime,deleted_at:DeletionTime}",
        "fields": {"name": str, "id": str, "status": str, "created_at": str, "deleted_at": str},
    },
    "s3": {
        "operation": ["s3api", "list-buckets", "--page-size", "1000"],
        "query": "Buckets[].{name:Name,created_at:CreationDate}",
        "fields": {"name": str, "created_at": str},
        "global": True,
    },
}


class InventoryError(Exception):
    """Only fixed, non-sensitive error codes may cross the CLI boundary."""

    def __init__(self, code: str, status: str = "failed") -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def load_accounts(root: Path = ROOT) -> list[dict]:
    try:
        config = json.loads((root / "config/accounts.json").read_text())
        accounts = config["accounts"]
        if config["version"] != 1 or not isinstance(accounts, list) or not accounts:
            raise ValueError
        aliases = set()
        for account in accounts:
            if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", account["alias"]):
                raise ValueError
            if not re.fullmatch(r"[0-9]{12}", account["account_id"]):
                raise ValueError
            if account["alias"] in aliases:
                raise ValueError
            aliases.add(account["alias"])
            validate_regions(account["default_regions"])
        return accounts
    except (OSError, ValueError, KeyError, TypeError):
        raise InventoryError("invalid_account_manifest") from None


def validate_regions(regions: list[str]) -> list[str]:
    if not isinstance(regions, list) or not regions:
        raise InventoryError("regions_required")
    if any(not isinstance(region, str) or not re.fullmatch(r"[a-z]{2,5}(?:-[a-z0-9]+)+-[0-9]+", region) for region in regions):
        raise InventoryError("invalid_region")
    return list(dict.fromkeys(regions))


def aws_command(operation: list[str], query: str, profile: str, region: str | None = None) -> list[str]:
    if not profile.strip() or any(ord(char) < 32 for char in profile):
        raise InventoryError("invalid_profile")
    command = ["aws", *operation, "--profile", profile, "--output", "json", "--no-cli-pager", "--query", query]
    if region:
        command.extend(["--region", region])
    return command


def build_plan(account: dict, profile: str, regions: list[str] | None = None, services: list[str] | None = None) -> dict:
    selected_regions = validate_regions(regions if regions is not None else account["default_regions"])
    selected_services = list(dict.fromkeys(services if services is not None else COLLECTIONS))
    if not selected_services or any(service not in COLLECTIONS for service in selected_services):
        raise InventoryError("invalid_service")
    collections = []
    for service in selected_services:
        definition = COLLECTIONS[service]
        for region in ([None] if definition.get("global") else selected_regions):
            collections.append({
                "service": service,
                "region": region,
                "scope": "global" if region is None else "regional",
                "command": aws_command(definition["operation"], definition["query"], profile, region or selected_regions[0]),
            })
    return {
        "schema_version": 1,
        "account": {"alias": account["alias"], "account_id": account["account_id"]},
        "profile": profile,
        "regions": selected_regions,
        "services": selected_services,
        "unselected_services": [service for service in COLLECTIONS if service not in selected_services],
        "coverage_note": "Selected metadata only; other services and regions are unscanned. S3 general-purpose bucket names are global; directory buckets, bucket locations and contents are unscanned. CloudFormation includes retained deleted-stack summaries.",
        "identity_command": aws_command(["sts", "get-caller-identity"], "{account_id:Account,principal_arn:Arn}", profile, selected_regions[0]),
        "collections": collections,
    }


def classify_failure(stderr: bytes) -> InventoryError:
    # Do not include any raw stderr in reports: credential helpers can print secrets.
    lowered = stderr.lower()
    if any(marker in lowered for marker in (b"accessdenied", b"unauthorizedoperation", b"not authorized")):
        return InventoryError("access_denied", "denied")
    if any(marker in lowered for marker in (b"expiredtoken", b"invalidclienttokenid", b"unable to locate credentials", b"sso session", b"config profile")) or (b"authorization grant" in lowered and b"expired" in lowered):
        return InventoryError("credentials_unavailable")
    if b"throttl" in lowered or b"requestlimitexceeded" in lowered:
        return InventoryError("throttled")
    return InventoryError("aws_command_failed")


def run_aws(command: list[str]) -> object:
    """Bound time and both pipes without shell execution or unbounded buffering."""
    env = dict(os.environ, AWS_PAGER="", AWS_CLI_AUTO_PROMPT="off", AWS_MAX_ATTEMPTS="2")
    try:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    except FileNotFoundError:
        raise InventoryError("aws_cli_unavailable") from None
    except OSError:
        raise InventoryError("aws_cli_start_failed") from None
    output = bytearray()
    error = bytearray()
    deadline = time.monotonic() + COMMAND_TIMEOUT
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, (output, MAX_OUTPUT_BYTES))
            selector.register(process.stderr, selectors.EVENT_READ, (error, MAX_ERROR_BYTES))
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise InventoryError("command_timeout", "timeout")
                for key, _ in selector.select(min(remaining, 0.25)):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    buffer, limit = key.data
                    if len(buffer) + len(chunk) > limit:
                        raise InventoryError("output_limit_exceeded")
                    buffer.extend(chunk)
        try:
            returncode = process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise InventoryError("command_timeout", "timeout") from None
        if returncode:
            raise classify_failure(bytes(error))
        try:
            return json.loads(output)
        except (ValueError, UnicodeDecodeError):
            raise InventoryError("malformed_output") from None
    except OSError:
        raise InventoryError("aws_io_failed") from None
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()
        process.stderr.close()


def project_record(record: object, fields: dict) -> dict:
    if not isinstance(record, dict) or not any(field in record for field in fields):
        raise InventoryError("malformed_output")
    selected = {}
    for name, expected_type in fields.items():
        value = record.get(name)
        if value is not None and type(value) is not expected_type:
            raise InventoryError("malformed_output")
        if expected_type is list and value is not None and any(type(item) is not str for item in value):
            raise InventoryError("malformed_output")
        selected[name] = value
    return selected


def get_identity(command: list[str], runner=None) -> dict:
    identity = project_record((runner or run_aws)(command), {"account_id": str, "principal_arn": str})
    if not identity["account_id"] or not re.fullmatch(r"[0-9]{12}", identity["account_id"]):
        raise InventoryError("malformed_identity")
    if not identity["principal_arn"] or not identity["principal_arn"].startswith("arn:"):
        raise InventoryError("malformed_identity")
    return identity


def scan_plan(plan: dict, runner=None) -> dict:
    runner = runner or run_aws
    identity = get_identity(plan["identity_command"], runner)
    if identity["account_id"] != plan["account"]["account_id"]:
        raise InventoryError("account_mismatch")
    report = {key: value for key, value in plan.items() if key not in ("collections", "identity_command")}
    report.update({"generated_at": datetime.now(timezone.utc).isoformat(), "identity": identity, "status": "complete", "collections": []})
    for item in plan["collections"]:
        result = {key: item[key] for key in ("service", "region", "scope")}
        try:
            raw = runner(item["command"])
            if not isinstance(raw, list):
                raise InventoryError("malformed_output")
            records = [project_record(record, COLLECTIONS[item["service"]]["fields"]) for record in raw]
            result.update({"status": "ok", "count": len(records), "resources": records})
        except InventoryError as error:
            result.update({"status": error.status, "error": error.code})
            report["status"] = "partial"
        report["collections"].append(result)
    return report


def write_report(report: dict, output: str | None, root: Path = ROOT) -> Path:
    """Write exclusively under inventory/local, using no-follow directory handles."""
    root = root.resolve()
    base = root / "inventory/local"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    destination = Path(output) if output else base / f"{timestamp}-{report['account']['alias']}.json"
    if not destination.is_absolute():
        destination = Path.cwd() / destination
    # Do not resolve the candidate: that would hide symlinks before checking them.
    if ".." in destination.parts:
        raise InventoryError("unsafe_output_path")
    try:
        relative = destination.relative_to(base)
    except ValueError:
        raise InventoryError("output_must_be_in_inventory_local") from None
    if not relative.parts or destination.suffix != ".json":
        raise InventoryError("output_must_be_json_file")
    # Ensure Git really ignores this exact path, including local override rules.
    try:
        ignored = subprocess.run(["git", "-C", str(root), "check-ignore", "--quiet", "--", str(destination)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        raise InventoryError("output_ignore_check_failed") from None
    if ignored.returncode != 0:
        raise InventoryError("output_path_not_ignored")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory_fd = None
    try:
        directory_fd = os.open(root, flags)
        for part in ("inventory", "local", *relative.parts[:-1]):
            try:
                os.mkdir(part, mode=0o700, dir_fd=directory_fd)
            except FileExistsError:
                pass
            next_fd = os.open(part, flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
            # Only the generated inventory tree is private; inventory/ may contain docs.
            if part != "inventory":
                os.fchmod(directory_fd, 0o700)
        descriptor = os.open(relative.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
        with os.fdopen(descriptor, "w") as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
            handle.write("\n")
    except OSError:
        raise InventoryError("output_write_refused") from None
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("accounts", help="List configured accounts without AWS calls")
    identity_parser = subparsers.add_parser("identity", help="Show STS identity using an explicit profile")
    identity_parser.add_argument("--profile", required=True)
    for action in ("plan", "scan"):
        subparser = subparsers.add_parser(action, help="Print collection commands without AWS calls" if action == "plan" else "Verify account, collect selected metadata, write a private local report")
        subparser.add_argument("--account", required=True, help="Account alias from config/accounts.json")
        subparser.add_argument("--profile", required=True)
        subparser.add_argument("--region", action="append", help="Repeat for selected regions; defaults to the account manifest")
        subparser.add_argument("--service", action="append", choices=COLLECTIONS, help="Repeat for selected services; defaults to all supported services")
        if action == "scan":
            subparser.add_argument("--output", help="New .json file under this repository's ignored inventory/local/")
    args = parser.parse_args(argv)
    try:
        if args.action == "identity":
            print(json.dumps(get_identity(aws_command(["sts", "get-caller-identity"], "{account_id:Account,principal_arn:Arn}", args.profile)), indent=2))
            return 0
        accounts = load_accounts()
        if args.action == "accounts":
            print(json.dumps(accounts, indent=2))
            return 0
        account = next((account for account in accounts if account["alias"] == args.account), None)
        if account is None:
            raise InventoryError("unknown_account_alias")
        plan = build_plan(account, args.profile, args.region, args.service)
        if args.action == "plan":
            print(json.dumps(plan, indent=2))
            return 0
        report = scan_plan(plan)
        destination = write_report(report, args.output)
        print(json.dumps({"status": report["status"], "output": str(destination), "collections": len(report["collections"])}))
        return 0 if report["status"] == "complete" else 2
    except InventoryError as error:
        print(json.dumps({"status": error.status, "error": error.code}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
