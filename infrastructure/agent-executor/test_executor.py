"""Offline boundary tests: no AWS, Docker, model, or credential-cache access."""

import argparse
import copy
from datetime import datetime, timezone
import importlib.util
import io
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("executor", Path(__file__).with_name("executor.py"))
executor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(executor)

ROLE = {"role_arn": "arn:aws:iam::034362054546:role/aws-reserved/sso.amazonaws.com/"
                   "AWSReservedSSO_AWSInfraInventory_0123456789abcdef", "role_id": "AROA" + "A" * 17}
MANIFEST = {"account_id": executor.ACCOUNT, "region": "us-east-1", "roles": {"inventory": ROLE},
            "image": "sha256:" + "a" * 64, "network": "aws-agent-internal", "proxy": "http://egress:3128"}
NETWORK_ID, PROXY_ID = "b" * 64, "c" * 64
NOW = 2_000_000_000


def credentials(seconds=1800):
    return {"AccessKeyId": "ASIA" + "A" * 16, "SecretAccessKey": "fake-secret-for-offline-tests",
            "SessionToken": "fake-session-for-offline-tests",
            "Expiration": datetime.fromtimestamp(NOW + seconds, timezone.utc).isoformat()}


def identity():
    return {"Account": executor.ACCOUNT,
            "Arn": "arn:aws:sts::034362054546:assumed-role/" + ROLE["role_arn"].rsplit("/", 1)[1] + "/test",
            "UserId": ROLE["role_id"] + ":test"}


def archive(*names, link=False):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as output:
        for name in names:
            item = tarfile.TarInfo(name)
            if link:
                item.type, item.linkname = tarfile.SYMTYPE, "/outside"
            else:
                item.size = 4
            output.addfile(item, None if link else io.BytesIO(b"safe"))
    return stream.getvalue()


class IdentityBoundaryTests(unittest.TestCase):
    def test_exact_role_and_tier(self):
        self.assertEqual(executor.validate_manifest(MANIFEST, "inventory"), ROLE)
        for tier in ("admin", "iam-audit", "", None):
            with self.subTest(tier=tier), self.assertRaises(executor.Rejected):
                executor.validate_manifest(MANIFEST, tier)

    def test_account_region_and_admin_role_rejected(self):
        for changed in ({"account_id": "043509841549"}, {"region": "us-west-2"},
                        {"roles": {"inventory": dict(ROLE, role_arn=ROLE["role_arn"].replace("AWSInfraInventory", "AdministratorAccess"))}}):
            with self.subTest(changed=changed), self.assertRaises(executor.Rejected):
                executor.validate_manifest(dict(MANIFEST, **changed), "inventory")

    def test_sts_matches_account_name_and_unique_role_id(self):
        executor.check_identity(identity(), ROLE)
        for key, value in (("Account", "043509841549"), ("Arn", "arn:aws:iam::034362054546:user/admin"),
                           ("UserId", "AROA" + "B" * 17 + ":test")):
            with self.subTest(key=key), self.assertRaises(executor.Rejected):
                executor.check_identity(dict(identity(), **{key: value}), ROLE)

    def test_only_short_temporary_sessions(self):
        self.assertEqual(executor.validate_credentials(credentials(), NOW), NOW + 1800)
        for seconds in (-1, 119, 3606, 86400):
            with self.subTest(seconds=seconds), self.assertRaises(executor.Rejected):
                executor.validate_credentials(credentials(seconds), NOW)

    def test_malformed_credentials_rejected(self):
        for changed in ({"SessionToken": None}, {"AccessKeyId": "AKIA" + "A" * 16},
                        {"SecretAccessKey": "fake\n[admin]"}, {"Expiration": "2033-05-18T03:33:20"}):
            with self.subTest(changed=changed), self.assertRaises(executor.Rejected):
                executor.validate_credentials(dict(credentials(), **changed), NOW)

    def test_environment_does_not_inherit_admin_or_tool_settings(self):
        with patch.dict(os.environ, {"AWS_PROFILE": "default", "AWS_ACCESS_KEY_ID": "fake-admin",
                                    "DOCKER_HOST": "tcp://host:2375", "CODEX_HOME": "/human/.codex"}):
            env = executor.base_environment()
        self.assertFalse(set(env) & {"AWS_PROFILE", "AWS_ACCESS_KEY_ID", "DOCKER_HOST", "CODEX_HOME"})

    def test_wrong_role_never_reaches_handoff(self):
        args = argparse.Namespace(manifest="unused", tier="inventory", handoff_fd=4, model_key_fd=5)
        with patch.object(executor, "operator_json", return_value=MANIFEST), \
             patch.object(executor.os, "fstat", return_value=argparse.Namespace(st_mode=0o010600)), \
             patch.object(executor, "capture_json", return_value=credentials()) as call, \
             patch.object(executor.time, "time", return_value=NOW), \
             patch.object(executor, "verified_identity", side_effect=executor.Rejected("STS role does not match")), \
             patch.object(executor.os, "fdopen") as handoff:
            with self.assertRaises(executor.Rejected):
                executor.issue(args)
            handoff.assert_not_called()
            self.assertIn("cambridge-agent-inventory", call.call_args.args[0])


class FileBoundaryTests(unittest.TestCase):
    def test_operator_json_rejects_symlink_and_writable_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text("{}")
            path.chmod(0o600)
            self.assertEqual(executor.operator_json(path), {})
            link = Path(directory) / "link"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                executor.operator_json(link)
            path.chmod(0o666)
            with self.assertRaises(executor.Rejected):
                executor.operator_json(path)

    def test_archive_extracts_regular_file(self):
        with tempfile.TemporaryDirectory() as directory:
            executor.unpack(archive("src/readme.txt"), directory)
            self.assertEqual((Path(directory) / "src/readme.txt").read_text(), "safe")

    def test_archive_rejects_traversal_and_sensitive_config(self):
        for name in ("../outside", "/outside", "a/../../outside", ".aws/config", "a/.codex/config.toml",
                     ".ssh/key", ".openclaw/config", ".git/config", ".env.production"):
            with self.subTest(name=name), self.assertRaises(executor.Rejected):
                executor.unpack(archive(name))

    def test_archive_rejects_links_duplicates_and_oversize(self):
        for raw in (archive("link", link=True), archive("a/b", "a/./b"), b"x" * (executor.MAX_ARCHIVE + 1)):
            with self.assertRaises(executor.Rejected):
                executor.unpack(raw)

    def test_json_and_model_key_limits(self):
        for raw in (b"[]", b"not JSON", b" " * 100):
            with self.assertRaises(executor.Rejected):
                executor.read_json(io.BytesIO(raw), 32)
        for key in (None, "short", "fake-key\nother", "x" * 4097):
            with self.assertRaises(executor.Rejected):
                executor.validate_model_key(key)


class ProcessBoundaryTests(unittest.TestCase):
    def test_fixed_container_boundary(self):
        command = executor.docker_command(MANIFEST, "aws-agent-test", NETWORK_ID, "172.30.50.2")
        for option in ("--privileged", "--volume", "--mount", "-v", "--device", "--env-file"):
            self.assertNotIn(option, command)
        self.assertIn("10001:10001", command)
        self.assertIn("--read-only", command)
        self.assertIn("no-new-privileges", command)
        self.assertEqual(command[command.index("--pull") + 1], "never")
        self.assertEqual(command[command.index("--network") + 1], NETWORK_ID)
        self.assertEqual(command[command.index("--dns") + 1], "127.0.0.1")
        self.assertEqual(command[command.index("--add-host") + 1], "egress:172.30.50.2")
        self.assertIn("net.ipv6.conf.all.disable_ipv6=1", command)
        self.assertIn("net.ipv6.conf.default.disable_ipv6=1", command)
        self.assertEqual([command[i + 1] for i, item in enumerate(command) if item == "--env"],
                         ["HTTP_PROXY=http://egress:3128", "HTTPS_PROXY=http://egress:3128"])

    def test_mutable_image_or_arbitrary_network_rejected(self):
        for changed in ({"image": "executor:latest"}, {"network": "host"}, {"proxy": "http://outside:3128"}):
            with self.assertRaises(executor.Rejected):
                executor.docker_command(dict(MANIFEST, **changed), "test", NETWORK_ID, "172.30.50.2")

    def test_bounded_command_streams_both_directions(self):
        output = executor.bounded_command([sys.executable, "-I", "-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"],
                                           executor.base_environment(), timeout=5, limit=200000, payload=b"a" * 180000)
        self.assertEqual(len(output), 180000)

    def test_bounded_command_rejects_flood(self):
        with self.assertRaisesRegex(executor.Rejected, "size limit"):
            executor.bounded_command([sys.executable, "-I", "-c", "import sys; sys.stdout.buffer.write(b'x' * 1000000)"],
                                     executor.base_environment(), timeout=5, limit=1024)

    def test_bounded_command_timeout_and_failure_suppress_output(self):
        for source, timeout in (("import time; time.sleep(5)", 0.05),
                                ("import sys; print('private fixture'); sys.exit(1)", 5)):
            with self.assertRaises(executor.Rejected) as caught:
                executor.bounded_command([sys.executable, "-I", "-c", source], executor.base_environment(), timeout=timeout, limit=1024)
            self.assertNotIn("private fixture", str(caught.exception))

    def test_literal_credentials_redacted(self):
        envelope = {"credentials": credentials(), "model_api_key": "fake-model-key"}
        output = executor.redact(" ".join([envelope["model_api_key"], *list(credentials().values())[:3]]), envelope)
        self.assertEqual(output.count("[REDACTED]"), 4)

    def test_result_projects_only_known_fields_and_checks_real_reported_id(self):
        value = {"task_id": "test", "account_id": executor.ACCOUNT, "principal_arn": identity()["Arn"],
                 "principal_id": identity()["UserId"], "expires_at": credentials()["Expiration"], "result": "summary",
                 "unexpected": "omit this"}
        result = executor.project_result(value, {"task_id": "test"}, credentials(), ROLE)
        self.assertNotIn("unexpected", result)
        self.assertEqual(result["principal_id"], identity()["UserId"])
        for changes in ({"principal_id": "wrong-role-id:session"}, {"principal_id": None},
                        {"expires_at": "wrong-expiry"}, {"principal_arn": "wrong-role-arn"}):
            with self.subTest(changes=changes), self.assertRaises(executor.Rejected):
                executor.project_result(dict(value, **changes), {"task_id": "test"}, credentials(), ROLE)


class NetworkBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = (Path(self.directory.name) / "squid.conf").resolve()
        self.config.write_text("safe")
        self.config.chmod(0o600)
        self.manifest = dict(MANIFEST, proxy_identity={"container_id": PROXY_ID, "image_id": "sha256:" + "d" * 64,
                              "config_path": str(self.config), "config_sha256": hashlib.sha256(b"safe").hexdigest()})
        self.network = {"Id": NETWORK_ID, "Internal": True, "Driver": "bridge", "EnableIPv6": False,
                        "Options": {"com.docker.network.bridge.gateway_mode_ipv4": "isolated"},
                        "IPAM": {"Config": [{"Subnet": "172.30.50.0/24"}]},
                        "Containers": {PROXY_ID: {"Name": "aws-agent-egress", "IPv4Address": "172.30.50.2/24"}}}
        self.proxy = {"Id": PROXY_ID, "Image": "sha256:" + "d" * 64, "Name": "/aws-agent-egress", "Running": True,
                      "Paused": False, "ReadonlyRootfs": True, "Privileged": False, "Path": "/usr/sbin/squid",
                      "Args": ["-N", "-f", "/etc/squid/squid.conf"],
                      "Mounts": [{"Type": "bind", "RW": False, "Source": str(self.config), "Destination": "/etc/squid/squid.conf"}],
                      "Networks": {"aws-agent-internal": {"NetworkID": NETWORK_ID, "IPAddress": "172.30.50.2"}}}

    def validate(self, version="28.0.0", network=None, proxy=None):
        return executor.validate_network(self.manifest, {"Version": version},
                                         self.network if network is None else network, self.proxy if proxy is None else proxy)

    def test_verified_network_returns_id_and_proxy_ip(self):
        self.assertEqual(self.validate(), (NETWORK_ID, "172.30.50.2"))

    def test_old_engine_or_nonisolated_network_rejected(self):
        for version in ("27.5.0", "bad", ""):
            with self.assertRaises(executor.Rejected):
                self.validate(version=version)
        for changes in ({"Internal": False}, {"Driver": "host"}, {"EnableIPv6": True}, {"Options": {}},
                        {"Containers": {"e" * 64: {"Name": "aws-agent-egress", "IPv4Address": "172.30.50.2/24"}}}):
            with self.subTest(changes=changes), self.assertRaises(executor.Rejected):
                self.validate(network=dict(self.network, **changes))

    def test_proxy_identity_startup_and_readonly_config_enforced(self):
        for changes in ({"Image": "sha256:" + "e" * 64}, {"Id": "e" * 64}, {"Running": False}, {"Paused": True},
                        {"ReadonlyRootfs": False}, {"Privileged": True}, {"Path": "/bin/sh"}, {"Args": ["-N"]},
                        {"Mounts": [dict(self.proxy["Mounts"][0], RW=True)]},
                        {"Mounts": [*self.proxy["Mounts"], {"Type": "tmpfs", "Destination": "/etc"}]}):
            with self.subTest(changes=changes), self.assertRaises(executor.Rejected):
                self.validate(proxy=dict(self.proxy, **changes))

    def test_proxy_ip_must_match_both_inspections_and_subnet(self):
        for address in ("172.30.50.3", "127.0.0.1", "169.254.169.254", "192.0.2.2", "::1", "malformed"):
            proxy = copy.deepcopy(self.proxy)
            proxy["Networks"]["aws-agent-internal"]["IPAddress"] = address
            with self.subTest(address=address), self.assertRaises(executor.Rejected):
                self.validate(proxy=proxy)

    def test_local_and_actual_mounted_config_hashes_checked(self):
        with patch.object(executor, "capture_json", side_effect=[{"Version": "29.1.5"}, self.network, self.proxy]), \
             patch.object(executor, "bounded_command", return_value=archive("squid.conf")) as read:
            self.assertEqual(executor.inspect_network(self.manifest, {}), (NETWORK_ID, "172.30.50.2"))
            self.assertEqual(read.call_args.args[0], ["docker", "cp", PROXY_ID + ":/etc/squid/squid.conf", "-"])
        self.config.write_text("changed")
        with patch.object(executor, "capture_json", side_effect=[{"Version": "29.1.5"}, self.network, self.proxy]), \
             patch.object(executor, "bounded_command") as read:
            with self.assertRaisesRegex(executor.Rejected, "Local proxy config"):
                executor.inspect_network(self.manifest, {})
            read.assert_not_called()

    def test_mounted_config_mismatch_or_link_rejected(self):
        for copied in (archive("squid.conf", link=True), archive("squid.conf", "extra.conf")):
            with patch.object(executor, "capture_json", side_effect=[{"Version": "29.1.5"}, self.network, self.proxy]), \
                 patch.object(executor, "bounded_command", return_value=copied), self.assertRaises(executor.Rejected):
                executor.inspect_network(self.manifest, {})
        self.config.write_text("other")
        self.manifest["proxy_identity"]["config_sha256"] = hashlib.sha256(b"other").hexdigest()
        with patch.object(executor, "capture_json", side_effect=[{"Version": "29.1.5"}, self.network, self.proxy]), \
             patch.object(executor, "bounded_command", return_value=archive("squid.conf")), \
             self.assertRaisesRegex(executor.Rejected, "Mounted proxy config"):
            executor.inspect_network(self.manifest, {})


if __name__ == "__main__":
    unittest.main()
