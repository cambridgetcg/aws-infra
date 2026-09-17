"""Offline fixtures: no test uses AWS credentials or invokes the AWS CLI."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import aws_inventory as inventory


ACCOUNT = {"alias": "fixture", "account_id": "123456789012", "default_regions": ["us-east-1"], "verification": "documented-unverified"}
IDENTITY = {"account_id": ACCOUNT["account_id"], "principal_arn": "arn:aws:iam::123456789012:role/fixture"}


class PlanningTests(unittest.TestCase):
    def test_plan_is_offline_and_marks_exact_coverage(self):
        with patch.object(inventory, "run_aws", side_effect=AssertionError("Unexpected AWS call")), patch.object(inventory, "load_accounts", return_value=[ACCOUNT]), redirect_stdout(io.StringIO()) as output:
            status = inventory.main(["plan", "--account", "fixture", "--profile", "chosen", "--region", "eu-west-2", "--service", "lambda"])
        self.assertEqual(status, 0)
        plan = json.loads(output.getvalue())
        self.assertEqual(plan["regions"], ["eu-west-2"])
        self.assertEqual(plan["services"], ["lambda"])
        self.assertIn("ec2", plan["unselected_services"])
        self.assertEqual(len(plan["collections"]), 1)
        self.assertEqual(plan["collections"][0]["region"], "eu-west-2")
        self.assertIn("unscanned", plan["coverage_note"])

    def test_default_regions_and_global_collection_once(self):
        plan = inventory.build_plan(ACCOUNT, "chosen", ["us-east-1", "eu-west-2", "us-east-1"], ["ec2", "s3", "s3"])
        self.assertEqual(plan["regions"], ["us-east-1", "eu-west-2"])
        self.assertEqual([(item["service"], item["region"]) for item in plan["collections"]], [("ec2", "us-east-1"), ("ec2", "eu-west-2"), ("s3", None)])
        self.assertEqual(inventory.build_plan(ACCOUNT, "chosen")["regions"], ACCOUNT["default_regions"])
        self.assertEqual(len(inventory.build_plan(ACCOUNT, "chosen")["collections"]), 9)

    def test_explicit_profile_required(self):
        for args in (["identity"], ["plan", "--account", "fixture"], ["scan", "--account", "fixture"]):
            with self.subTest(args=args), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                inventory.main(args)
            self.assertEqual(caught.exception.code, 2)

    def test_no_pagination_truncation_and_queries_always_present(self):
        for item in inventory.build_plan(ACCOUNT, "chosen")["collections"]:
            command = item["command"]
            self.assertEqual(command[0], "aws")
            self.assertIn("--query", command)
            self.assertIn("--profile", command)
            self.assertNotIn("--no-paginate", command)
            self.assertNotIn("--max-items", command)
            if item["service"] in ("sqs", "s3"):
                self.assertIn("--page-size", command)

    def test_invalid_manifest_is_sanitized(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config/accounts.json").write_text("invalid private content")
            with self.assertRaisesRegex(inventory.InventoryError, "^invalid_account_manifest$"):
                inventory.load_accounts(root)


class CollectionTests(unittest.TestCase):
    def test_wrong_account_stops_before_any_resource_call(self):
        runner = Mock(return_value={**IDENTITY, "account_id": "999999999999"})
        with self.assertRaisesRegex(inventory.InventoryError, "^account_mismatch$"):
            inventory.scan_plan(inventory.build_plan(ACCOUNT, "chosen"), runner)
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(runner.call_args.args[0][1:3], ["sts", "get-caller-identity"])

    def test_identity_failure_stops_before_any_resource_call(self):
        runner = Mock(side_effect=inventory.InventoryError("credentials_unavailable"))
        with self.assertRaisesRegex(inventory.InventoryError, "credentials_unavailable"):
            inventory.scan_plan(inventory.build_plan(ACCOUNT, "chosen"), runner)
        self.assertEqual(runner.call_count, 1)

    def test_denial_is_preserved_and_later_collections_continue(self):
        runner = Mock(side_effect=[IDENTITY, inventory.InventoryError("access_denied", "denied"), [{"name": "fixture-table"}]])
        report = inventory.scan_plan(inventory.build_plan(ACCOUNT, "chosen", services=["ec2", "dynamodb"]), runner)
        self.assertEqual(report["status"], "partial")
        denied, success = report["collections"]
        self.assertEqual(denied["status"], "denied")
        self.assertEqual(denied["error"], "access_denied")
        self.assertNotIn("resources", denied)
        self.assertNotIn("count", denied)
        self.assertEqual(success["resources"], [{"name": "fixture-table"}])
        self.assertEqual(runner.call_count, 3)

    def test_global_request_once_in_multi_region_scan(self):
        runner = Mock(side_effect=[IDENTITY, [], [], []])
        report = inventory.scan_plan(inventory.build_plan(ACCOUNT, "chosen", ["us-east-1", "eu-west-2"], ["sqs", "s3"]), runner)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(runner.call_count, 4)
        self.assertEqual(sum(call.args[0][1:3] == ["s3api", "list-buckets"] for call in runner.call_args_list), 1)
        self.assertEqual(report["collections"][0]["count"], 0)

    def test_projection_excludes_unrequested_fields_and_nested_secrets(self):
        raw = {"name": "fixture-function", "arn": "arn:aws:lambda:us-east-1:123456789012:function:fixture", "Environment": {"Variables": {"TOKEN": "fixture-secret"}}, "Tags": {"private": "fixture-secret"}, "Code": {"Location": "fixture-secret"}}
        runner = Mock(side_effect=[{**IDENTITY, "extra": "fixture-secret"}, [raw]])
        report = inventory.scan_plan(inventory.build_plan(ACCOUNT, "chosen", services=["lambda"]), runner)
        self.assertNotIn("fixture-secret", json.dumps(report))
        self.assertEqual(report["collections"][0]["resources"][0]["name"], "fixture-function")
        self.assertEqual(report["identity"], IDENTITY)

    def test_nested_values_in_scalar_fields_are_rejected(self):
        runner = Mock(side_effect=[IDENTITY, [{"name": {"token": "fixture-secret"}}]])
        report = inventory.scan_plan(inventory.build_plan(ACCOUNT, "chosen", services=["lambda"]), runner)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["collections"][0]["error"], "malformed_output")
        self.assertNotIn("fixture-secret", json.dumps(report))

    def test_malformed_and_timeout_results_are_never_empty(self):
        for result in ({"unexpected": []}, ["not a record"], [{}], inventory.InventoryError("command_timeout", "timeout")):
            with self.subTest(result=result):
                runner = Mock(side_effect=[IDENTITY, result])
                report = inventory.scan_plan(inventory.build_plan(ACCOUNT, "chosen", services=["ecs"]), runner)
                self.assertEqual(report["status"], "partial")
                self.assertNotIn("resources", report["collections"][0])

    def test_scan_cli_returns_nonzero_for_partial_report(self):
        report = {"status": "partial", "collections": [{"status": "denied"}]}
        with patch.object(inventory, "load_accounts", return_value=[ACCOUNT]), patch.object(inventory, "scan_plan", return_value=report), patch.object(inventory, "write_report", return_value=Path("inventory/local/report.json")) as writer, redirect_stdout(io.StringIO()) as output:
            status = inventory.main(["scan", "--account", "fixture", "--profile", "chosen"])
        self.assertEqual(status, 2)
        self.assertEqual(json.loads(output.getvalue())["status"], "partial")
        writer.assert_called_once_with(report, None)


class ProcessBoundaryTests(unittest.TestCase):
    # Local Python child processes simulate the CLI pipes. No AWS invocation.
    def test_malformed_stdout_is_sanitized(self):
        with self.assertRaisesRegex(inventory.InventoryError, "^malformed_output$"):
            inventory.run_aws([sys.executable, "-c", "print('fixture-secret')"])

    def test_stderr_never_leaks(self):
        with self.assertRaises(inventory.InventoryError) as caught:
            inventory.run_aws([sys.executable, "-c", "import sys; sys.stderr.write('AccessDenied fixture-secret'); sys.exit(1)"])
        self.assertEqual(caught.exception.code, "access_denied")
        self.assertEqual(caught.exception.status, "denied")
        self.assertNotIn("fixture-secret", str(caught.exception))

    def test_expired_oauth_grant_classifies_credentials(self):
        error = inventory.classify_failure(b"The provided authorization grant is expired fixture-secret")
        self.assertEqual(error.code, "credentials_unavailable")
        self.assertNotIn("fixture-secret", str(error))

    def test_process_deadline_is_enforced(self):
        with patch.object(inventory, "COMMAND_TIMEOUT", 0.1), self.assertRaises(inventory.InventoryError) as caught:
            inventory.run_aws([sys.executable, "-c", "import time; time.sleep(5)"])
        self.assertEqual(caught.exception.code, "command_timeout")

    def test_output_limit_is_enforced(self):
        with patch.object(inventory, "MAX_OUTPUT_BYTES", 100), self.assertRaisesRegex(inventory.InventoryError, "^output_limit_exceeded$"):
            inventory.run_aws([sys.executable, "-c", "print('x' * 10000)"])

    def test_cli_arguments_are_not_interpreted_by_a_shell(self):
        marker = "$(printf fixture-secret); `echo unexpected`"
        result = inventory.run_aws([sys.executable, "-c", "import json,sys; print(json.dumps(sys.argv[1]))", marker])
        self.assertEqual(result, marker)


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (self.root / ".gitignore").write_text("/inventory/local/\n")
        self.report = {"account": {"alias": "fixture"}, "status": "complete", "collections": []}

    def test_private_report_and_no_overwrite(self):
        path = inventory.write_report(self.report, None, self.root)
        self.assertEqual(json.loads(path.read_text()), self.report)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        with self.assertRaisesRegex(inventory.InventoryError, "^output_write_refused$"):
            inventory.write_report({**self.report, "changed": True}, str(path), self.root)
        self.assertEqual(json.loads(path.read_text()), self.report)

    def test_output_outside_ignored_tree_is_refused(self):
        for path in (self.root / "report.json", self.root / "inventory/local/../escape.json"):
            with self.subTest(path=path), self.assertRaises(inventory.InventoryError):
                inventory.write_report(self.report, str(path), self.root)
        self.assertFalse((self.root / "report.json").exists())

    def test_ignored_rule_is_required(self):
        (self.root / ".gitignore").write_text("")
        with self.assertRaisesRegex(inventory.InventoryError, "^output_path_not_ignored$"):
            inventory.write_report(self.report, None, self.root)

    def test_symlinked_directory_and_destination_are_refused(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / "inventory").mkdir()
        (self.root / "inventory/local").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(inventory.InventoryError):
            inventory.write_report(self.report, None, self.root)
        self.assertEqual(list(outside.iterdir()), [])
        (self.root / "inventory/local").unlink()
        (self.root / "inventory/local").mkdir()
        target = outside / "untouched.json"
        target.write_text("original")
        link = self.root / "inventory/local/link.json"
        link.symlink_to(target)
        with self.assertRaises(inventory.InventoryError):
            inventory.write_report(self.report, str(link), self.root)
        self.assertEqual(target.read_text(), "original")

    def test_tracked_output_path_is_refused_even_with_ignore_rule(self):
        path = self.root / "inventory/local/tracked.json"
        path.parent.mkdir(parents=True)
        path.write_text("existing")
        subprocess.run(["git", "-C", str(self.root), "add", "--force", "inventory/local/tracked.json"], check=True)
        with self.assertRaisesRegex(inventory.InventoryError, "^output_path_not_ignored$"):
            inventory.write_report(self.report, str(path), self.root)
        self.assertEqual(path.read_text(), "existing")


if __name__ == "__main__":
    unittest.main()
