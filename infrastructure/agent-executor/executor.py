#!/usr/bin/env python3
"""Explicit human issuance -> isolated runtime -> whole Codex process. No daemon starts."""

import argparse
import base64
from datetime import datetime
import hashlib
import io
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import selectors
import signal
import stat
import subprocess
import sys
import tarfile
import time

ACCOUNT = "034362054546"
PROFILES = {"inventory": "cambridge-agent-inventory", "iam-audit": "cambridge-iam-audit"}
PERMISSION_SETS = {"inventory": "AWSInfraInventory", "iam-audit": "AWSInfraIAMAudit"}
MAX_ARCHIVE = 8 * 1024 * 1024
MAX_HANDOFF = 2 * MAX_ARCHIVE


class Rejected(Exception):
    """Only fixed, non-secret diagnostic strings belong in this exception."""


def require(condition, message):
    if not condition:
        raise Rejected(message)


def read_json(stream, limit):
    raw = stream.read(limit + 1)
    require(len(raw) <= limit, "Input exceeds the permitted size")
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise Rejected("Invalid JSON input") from None
    require(isinstance(value, dict), "Expected a JSON object")
    return value


def operator_bytes(path, limit):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        require(stat.S_ISREG(metadata.st_mode) and metadata.st_uid == os.getuid()
                and not metadata.st_mode & 0o022, "Operator file must be owned and not writable by others")
        content = stream.read(limit + 1)
        require(len(content) <= limit, "Operator file exceeds the size limit")
        return content


def operator_json(path):
    return read_json(io.BytesIO(operator_bytes(path, 65536)), 65536)


def validate_manifest(manifest, tier):
    require(tier in PROFILES, "Unsupported access tier")
    require(manifest.get("account_id") == ACCOUNT and manifest.get("region") == "us-east-1",
            "Unexpected account or region")
    role = manifest.get("roles", {}).get(tier, {})
    prefix = rf"arn:aws:iam::{ACCOUNT}:role/aws-reserved/sso\.amazonaws\.com/(?:us-east-1/)?"
    require(isinstance(role.get("role_arn"), str) and re.fullmatch(
        prefix + "AWSReservedSSO_" + PERMISSION_SETS[tier] + r"_[0-9a-fA-F]{16}", role["role_arn"]),
        "Expected the exact provisioned role ARN for this tier")
    require(isinstance(role.get("role_id"), str) and re.fullmatch(r"AROA[A-Z0-9]{17}", role["role_id"]),
            "Expected the provisioned IAM role ID")
    return role


def validate_credentials(value, now=None):
    now = time.time() if now is None else now
    require(isinstance(value, dict), "Missing temporary credentials")
    for key in ("AccessKeyId", "SecretAccessKey", "SessionToken", "Expiration"):
        item = value.get(key)
        require(isinstance(item, str) and 1 <= len(item) <= 16384 and not any(c in item for c in "\r\n\x00"),
                "Malformed temporary credentials")
    require(re.fullmatch(r"ASIA[A-Z0-9]{12,124}", value["AccessKeyId"]), "Only STS temporary keys are accepted")
    try:
        expiry = datetime.fromisoformat(value["Expiration"].replace("Z", "+00:00"))
        require(expiry.tzinfo is not None, "Credential expiration needs a timezone")
        seconds = expiry.timestamp() - now
    except (ValueError, OverflowError):
        raise Rejected("Invalid credential expiration") from None
    require(120 <= seconds <= 3605, "Session must have 2–60 minutes remaining")
    return expiry.timestamp()


def check_identity(identity, role):
    role_name = role["role_arn"].rsplit("/", 1)[1]
    require(identity.get("Account") == ACCOUNT, "STS account does not match")
    require(isinstance(identity.get("Arn"), str) and identity["Arn"].startswith(
        f"arn:aws:sts::{ACCOUNT}:assumed-role/{role_name}/"), "STS role does not match")
    require(isinstance(identity.get("UserId"), str) and identity["UserId"].startswith(role["role_id"] + ":"),
            "STS role ID does not match")


def base_environment():
    return {"PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
            "AWS_EC2_METADATA_DISABLED": "true", "AWS_PAGER": "", "AWS_CLI_AUTO_PROMPT": "off"}


def bounded_command(command, env, *, timeout, limit, payload=None):
    """Drain bounded stdout while streaming stdin; no unbounded communicate() buffer."""
    process = None
    try:
        process = subprocess.Popen(command, env=env, stdin=subprocess.PIPE if payload is not None else subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
        deadline, output = time.monotonic() + timeout, bytearray()
        with selectors.DefaultSelector() as selector:
            os.set_blocking(process.stdout.fileno(), False)
            selector.register(process.stdout, selectors.EVENT_READ)
            if payload is not None:
                pending = memoryview(payload)
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                require(remaining > 0, "Required command timed out; output suppressed")
                for key, event in selector.select(min(remaining, 0.2)):
                    if event & selectors.EVENT_WRITE:
                        if pending:
                            written = os.write(key.fd, pending[:65536])
                            pending = pending[written:]
                        if not pending:
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                    else:
                        chunk = os.read(key.fd, min(65536, limit + 1 - len(output)))
                        output.extend(chunk)
                        require(len(output) <= limit, "Required command output exceeded the size limit")
                        if not chunk:
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
            returncode = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        require(returncode == 0, "Required command failed; output suppressed")
        return bytes(output)
    except (OSError, subprocess.TimeoutExpired):
        raise Rejected("Required command failed or timed out; output suppressed") from None
    finally:
        if process is not None:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            for stream in (process.stdin, process.stdout):
                if stream is not None and not stream.closed:
                    stream.close()


def capture_json(command, env, timeout=30):
    return read_json(io.BytesIO(bounded_command(command, env, timeout=timeout, limit=65536)), 65536)


def validate_model_key(key):
    require(isinstance(key, str) and 8 <= len(key) <= 4096 and not any(c in key for c in "\r\n\x00"),
            "Missing dedicated model API key")


def verified_identity(credentials, role):
    env = base_environment()
    env.update({"AWS_ACCESS_KEY_ID": credentials["AccessKeyId"],
                "AWS_SECRET_ACCESS_KEY": credentials["SecretAccessKey"],
                "AWS_SESSION_TOKEN": credentials["SessionToken"],
                "AWS_CONFIG_FILE": "/dev/null", "AWS_SHARED_CREDENTIALS_FILE": "/dev/null"})
    # In the container only, inherit the launcher's fixed outbound proxy.
    for name in ("HTTP_PROXY", "HTTPS_PROXY"):
        if os.environ.get(name) == "http://egress:3128":
            env[name] = os.environ[name]
    identity = capture_json(["aws", "sts", "get-caller-identity", "--region", "us-east-1",
                             "--output", "json", "--no-cli-pager"], env)
    check_identity(identity, role)
    return identity


def issue(args):
    manifest = operator_json(args.manifest)
    role = validate_manifest(manifest, args.tier)
    require(args.handoff_fd >= 3 and args.model_key_fd >= 3 and args.handoff_fd != args.model_key_fd,
            "Use separate private file descriptors for key input and handoff")
    kind = os.fstat(args.handoff_fd).st_mode
    require(stat.S_ISFIFO(kind) or stat.S_ISSOCK(kind), "Credential handoff must be a pipe or socket, never a terminal/file")
    env = base_environment()
    env["HOME"] = str(Path.home())
    env["AWS_CONFIG_FILE"] = str(Path.home() / ".aws/config")
    env["AWS_SHARED_CREDENTIALS_FILE"] = "/dev/null"
    credentials = capture_json(["aws", "configure", "export-credentials", "--profile",
                                PROFILES[args.tier], "--format", "process"], env)
    validate_credentials(credentials)
    verified_identity(credentials, role)  # Reject admin/wrong-role credentials before transporting them.
    with os.fdopen(os.dup(args.model_key_fd), "rb") as stream:
        key = stream.read(4097).decode("utf-8").strip()
    validate_model_key(key)
    envelope = {"tier": args.tier, "credentials": credentials, "model_api_key": key}
    with os.fdopen(os.dup(args.handoff_fd), "wb") as stream:
        stream.write(json.dumps(envelope).encode())


def validate_task(task):
    require(isinstance(task.get("task_id"), str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", task["task_id"]),
            "Invalid task ID")
    require(isinstance(task.get("model"), str) and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}", task["model"])
            and not task["model"].startswith("REPLACE"), "Select an approved model")
    require(isinstance(task.get("prompt"), str) and 1 <= len(task["prompt"]) <= 16384, "Invalid task prompt")


def unpack(raw, destination=None):
    require(len(raw) <= MAX_ARCHIVE, "Input archive is too large")
    try:
        archive = tarfile.open(fileobj=io.BytesIO(raw), mode="r:")
    except tarfile.TarError:
        raise Rejected("Input must be an uncompressed tar archive") from None
    total, seen = 0, set()
    blocked = {".aws", ".codex", ".openclaw", ".ssh", ".git"}
    with archive:
        for item in archive:
            path = PurePosixPath(item.name)
            require(not path.is_absolute() and ".." not in path.parts and path.parts
                    and not any(part in blocked or part.startswith(".env") for part in path.parts),
                    "Archive contains a forbidden path")
            require(item.isdir() or item.isfile(), "Archive links and special files are forbidden")
            require(str(path) not in seen and not any(x in item.name for x in ("\x00", "\r", "\n")),
                    "Archive contains a duplicate or malformed path")
            seen.add(str(path))
            total += item.size
            require(total <= MAX_ARCHIVE and len(seen) <= 2000, "Archive contents exceed limits")
            if destination:
                target = Path(destination).joinpath(*path.parts)
                if item.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("xb") as output, archive.extractfile(item) as source:
                        output.write(source.read())


def validate_network(manifest, version, network, proxy):
    """Validate inspected facts; operational probes remain a separate prerequisite."""
    match = re.fullmatch(r"([0-9]+)\.[0-9]+\.[0-9]+(?:[-+].*)?", version.get("Version", ""))
    require(match and int(match.group(1)) >= 28, "Docker Engine server 28 or newer is required")
    require(network.get("Internal") is True and network.get("Driver") == "bridge"
            and network.get("EnableIPv6") is False
            and network.get("Options", {}).get("com.docker.network.bridge.gateway_mode_ipv4") == "isolated",
            "Docker network must be an IPv4-only internal bridge with isolated gateway mode")
    network_id = network.get("Id", "")
    require(re.fullmatch(r"[0-9a-f]{64}", network_id), "Invalid inspected network ID")
    expected = manifest.get("proxy_identity", {})
    proxy_id, image_id = expected.get("container_id", ""), expected.get("image_id", "")
    require(re.fullmatch(r"[0-9a-f]{64}", proxy_id)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", image_id), "Pin the exact proxy container and image IDs")
    peers = network.get("Containers", {})
    require(set(peers) == {proxy_id} and peers[proxy_id].get("Name") == "aws-agent-egress",
            "Dedicated network must contain only the pinned egress proxy")
    require(proxy.get("Id") == proxy_id and proxy.get("Image") == image_id
            and proxy.get("Name") == "/aws-agent-egress" and proxy.get("Running") is True
            and proxy.get("Paused") is False and proxy.get("ReadonlyRootfs") is True
            and proxy.get("Privileged") is False, "Proxy identity or runtime configuration does not match")
    require(proxy.get("Path") == "/usr/sbin/squid"
            and proxy.get("Args") == ["-N", "-f", "/etc/squid/squid.conf"],
            "Proxy must run the reviewed Squid command directly")
    expected_path = expected.get("config_path", "")
    require(isinstance(expected_path, str) and Path(expected_path).is_absolute()
            and str(Path(expected_path).resolve()) == expected_path, "Use the canonical private proxy config path")
    mounts = proxy.get("Mounts", [])
    configs = [mount for mount in mounts if mount.get("Type") != "tmpfs"]
    require(len(configs) == 1 and configs[0].get("Type") == "bind" and configs[0].get("RW") is False
            and configs[0].get("Source") == expected_path
            and configs[0].get("Destination") == "/etc/squid/squid.conf"
            and all(mount.get("Destination") in {"/run", "/tmp", "/var/log/squid", "/var/spool/squid", "/var/cache/squid"}
                    for mount in mounts if mount.get("Type") == "tmpfs"),
            "Proxy must use only the exact read-only config bind and permitted temporary storage")
    endpoint = proxy.get("Networks", {}).get("aws-agent-internal", {})
    require(endpoint.get("NetworkID") == network_id, "Proxy network ID does not match")
    try:
        address = ipaddress.IPv4Address(endpoint.get("IPAddress", ""))
        peer_address = ipaddress.IPv4Interface(peers[proxy_id].get("IPv4Address", "")).ip
        subnets = [ipaddress.IPv4Network(value["Subnet"]) for value in network.get("IPAM", {}).get("Config", [])]
    except (ValueError, KeyError):
        raise Rejected("Invalid proxy IPv4 endpoint") from None
    require(address == peer_address and address.is_private and not address.is_loopback
            and not address.is_link_local and not address.is_unspecified and not address.is_multicast
            and any(address in subnet and address not in (subnet.network_address, subnet.broadcast_address) for subnet in subnets),
            "Proxy IPv4 endpoint does not match the inspected private network")
    return network_id, str(address)


def inspect_network(manifest, env):
    version = capture_json(["docker", "version", "--format", "{{json .Server}}"], env)
    network = capture_json(["docker", "network", "inspect", "aws-agent-internal", "--format", "{{json .}}"], env)
    expected = manifest.get("proxy_identity", {})
    proxy_id = expected.get("container_id", "")
    require(re.fullmatch(r"[0-9a-f]{64}", proxy_id), "Pin the exact proxy container ID")
    # Project only necessary metadata: never inspect/export proxy environment values.
    fields = {"Id": ".Id", "Name": ".Name", "Image": ".Image", "Path": ".Path", "Args": ".Args",
              "Running": ".State.Running", "Paused": ".State.Paused", "ReadonlyRootfs": ".HostConfig.ReadonlyRootfs",
              "Privileged": ".HostConfig.Privileged", "Mounts": ".Mounts", "Networks": ".NetworkSettings.Networks"}
    projection = "{" + ",".join(json.dumps(key) + ":{{json " + value + "}}" for key, value in fields.items()) + "}"
    proxy = capture_json(["docker", "container", "inspect", proxy_id, "--format", projection], env)
    result = validate_network(manifest, version, network, proxy)
    fingerprint = expected.get("config_sha256", "")
    require(re.fullmatch(r"[0-9a-f]{64}", fingerprint), "Pin the reviewed proxy config fingerprint")
    local_config = operator_bytes(expected["config_path"], 65536)
    require(hashlib.sha256(local_config).hexdigest() == fingerprint, "Local proxy config fingerprint does not match")
    # Docker cp reads the daemon's actual mounted file, including on a VM-backed engine.
    raw = bounded_command(["docker", "cp", proxy_id + ":/etc/squid/squid.conf", "-"], env, timeout=30, limit=131072)
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
            members = archive.getmembers()
            require(len(members) == 1 and members[0].isfile() and members[0].size <= 65536,
                    "Unexpected proxy config copy")
            content = archive.extractfile(members[0]).read(65537)
    except tarfile.TarError:
        raise Rejected("Invalid proxy config copy") from None
    require(hashlib.sha256(content).hexdigest() == fingerprint, "Mounted proxy config fingerprint does not match")
    return result


def docker_command(manifest, name, network_id, proxy_ip):
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", manifest.get("image", "")), "Use a verified immutable local image ID")
    require(manifest.get("network") == "aws-agent-internal" and manifest.get("proxy") == "http://egress:3128",
            "Use the dedicated internal network and fixed egress proxy")
    require(re.fullmatch(r"[0-9a-f]{64}", network_id), "Use the inspected network ID")
    try:
        address = ipaddress.IPv4Address(proxy_ip)
    except ValueError:
        raise Rejected("Use the inspected proxy IPv4 address") from None
    command = ["docker", "run", "--pull", "never", "--rm", "--name", name, "--platform", "linux/arm64",
               "--user", "10001:10001", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
               "--pids-limit", "128", "--memory", "2g", "--cpus", "2", "--log-driver", "none",
               "--network", network_id, "--dns", "127.0.0.1", "--add-host", f"egress:{address}",
               "--sysctl", "net.ipv6.conf.all.disable_ipv6=1", "--sysctl", "net.ipv6.conf.default.disable_ipv6=1",
               "--interactive"]
    for path, size in (("/run/session", "1m"), ("/home/agent", "64m"), ("/work", "256m"), ("/tmp", "64m")):
        command += ["--tmpfs", f"{path}:rw,nosuid,nodev,uid=10001,gid=10001,mode=0700,size={size}"]
    command += ["--env", "HTTP_PROXY=http://egress:3128", "--env", "HTTPS_PROXY=http://egress:3128",
                "--entrypoint", "/usr/local/bin/python3", manifest["image"], "-I", "-B", "/opt/executor.py", "entry"]
    return command


def redact(text, envelope):
    for secret in [envelope["model_api_key"], *[envelope["credentials"][key]
                  for key in ("AccessKeyId", "SecretAccessKey", "SessionToken")]]:
        text = text.replace(secret, "[REDACTED]")
    return text


def project_result(result, task, credentials, role):
    require(result.get("task_id") == task["task_id"] and result.get("account_id") == ACCOUNT
            and isinstance(result.get("result"), str)
            and result.get("expires_at") == credentials["Expiration"], "Unexpected executor result")
    # This checks output consistency, not attestation of an untrusted task's report.
    check_identity({"Account": result["account_id"], "Arn": result.get("principal_arn"),
                    "UserId": result.get("principal_id")}, role)
    return {key: result[key] for key in ("task_id", "account_id", "principal_arn", "principal_id", "expires_at", "result")}


def run(args):
    require(os.getuid() not in (0, 501), "Run the executor launcher under a separate unprivileged OS account")
    require(sys.platform != "darwin" or 80 not in os.getgroups(), "Executor OS account must not be an administrator")
    manifest = operator_json(args.manifest)
    role = validate_manifest(manifest, args.tier)
    task = operator_json(args.task)
    validate_task(task)
    envelope = read_json(sys.stdin.buffer, MAX_HANDOFF)
    require(envelope.get("tier") == args.tier, "Credential tier does not match the requested task")
    expiry = validate_credentials(envelope.get("credentials"))
    validate_model_key(envelope.get("model_api_key"))
    with Path(args.archive).open("rb") as stream:
        raw = stream.read(MAX_ARCHIVE + 1)
    unpack(raw)
    name = "aws-agent-" + secrets.token_hex(16)
    env = base_environment()
    env["HOME"] = str(Path.home())
    network_id, proxy_ip = inspect_network(manifest, env)
    command = docker_command(manifest, name, network_id, proxy_ip)
    envelope.update({"role": role, "task": task, "archive": base64.b64encode(raw).decode()})
    try:
        output = bounded_command(command, env, payload=json.dumps(envelope).encode(),
                                 timeout=max(1, expiry - time.time()), limit=524288)
        result = read_json(io.BytesIO(output), 524288)
        result = project_result(result, task, envelope["credentials"], role)
        sys.stdout.write(redact(json.dumps(result), envelope) + "\n")
    finally:
        subprocess.run(["docker", "rm", "--force", name], env=env, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)


def entry():
    require(os.getuid() == 10001, "Unexpected container user")
    os.umask(0o077)
    envelope = read_json(sys.stdin.buffer, MAX_HANDOFF)
    tier, role = envelope.get("tier"), envelope.get("role")
    validate_manifest({"account_id": ACCOUNT, "region": "us-east-1", "roles": {tier: role}}, tier)
    expiry = validate_credentials(envelope.get("credentials"))
    validate_model_key(envelope.get("model_api_key"))
    task = envelope.get("task", {})
    validate_task(task)
    credentials = envelope["credentials"]
    identity = verified_identity(credentials, role)
    raw = base64.b64decode(envelope["archive"], validate=True)
    unpack(raw, "/work")
    session = Path("/run/session")
    (session / "config").write_text("[profile task]\nregion = us-east-1\noutput = json\n")
    (session / "credentials").write_text("[task]\naws_access_key_id = " + credentials["AccessKeyId"]
        + "\naws_secret_access_key = " + credentials["SecretAccessKey"]
        + "\naws_session_token = " + credentials["SessionToken"] + "\n")
    env = base_environment()
    env.update({"HOME": "/home/agent", "CODEX_API_KEY": envelope["model_api_key"],
                "AWS_PROFILE": "task", "AWS_CONFIG_FILE": "/run/session/config",
                "AWS_SHARED_CREDENTIALS_FILE": "/run/session/credentials", "AWS_REGION": "us-east-1",
                "HTTP_PROXY": "http://egress:3128", "HTTPS_PROXY": "http://egress:3128"})
    # The outer container is the sandbox. No host tools, host config, MCP setup or caches are imported.
    command = ["codex", "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check",
               "--sandbox", "danger-full-access", "-c", 'approval_policy="never"', "-c", 'web_search="disabled"',
               "--model", task["model"], "--cd", "/work", "--output-last-message", "/run/session/result.txt", "-"]
    process = subprocess.Popen(command, env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        process.communicate(task["prompt"].encode(), timeout=max(1, expiry - time.time() - 30))
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        raise Rejected("Task stopped before credential expiry") from None
    require(process.returncode == 0, "Codex task failed; subprocess output suppressed")
    with (session / "result.txt").open("rb") as stream:
        result = stream.read(262145)
    require(len(result) <= 262144, "Task result is too large")
    print(json.dumps({"task_id": task["task_id"], "account_id": ACCOUNT, "principal_arn": identity["Arn"], "principal_id": identity["UserId"],
                      "expires_at": credentials["Expiration"], "result": redact(result.decode("utf-8", "replace"), envelope)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("issue", "run"):
        command = commands.add_parser(name)
        command.add_argument("--manifest", required=True)
        command.add_argument("--tier", choices=tuple(PROFILES), default="inventory")
        if name == "issue":
            command.add_argument("--model-key-fd", type=int, required=True)
            command.add_argument("--handoff-fd", type=int, required=True)
        else:
            command.add_argument("--task", required=True)
            command.add_argument("--archive", required=True)
    commands.add_parser("entry")
    args = parser.parse_args()
    try:
        if args.command == "entry":
            entry()
        else:
            {"issue": issue, "run": run}[args.command](args)
        return 0
    except Rejected as error:
        print(str(error), file=sys.stderr)
    except Exception:
        print("Executor failed; sensitive diagnostics suppressed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
