"""Bootstrap safety tests: fake account metadata and temporary files; no native writes."""

import argparse
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("bootstrap_local", Path(__file__).with_name("bootstrap-local.py"))
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class BootstrapTests(unittest.TestCase):
    def test_account_selection_rejects_existing_and_skips_used_uids(self):
        with self.assertRaises(bootstrap.Rejected):
            bootstrap.choose_uid({"aws-agent": 502})
        with patch.object(bootstrap.pwd, "getpwuid", side_effect=KeyError):
            self.assertEqual(bootstrap.choose_uid({"person": 502, "service": 503}), 504)

    def test_known_human_and_private_home_required(self):
        value = {"RecordName": ["yournameisai"], "UniqueID": ["501"], "NFSHomeDirectory": ["/Users/yournameisai"]}
        metadata = argparse.Namespace(st_uid=501, st_mode=stat.S_IFDIR | 0o700)
        bootstrap.validate_human(value, metadata)
        for change in ({"UniqueID": ["502"]}, {"RecordName": ["other"]}, {"NFSHomeDirectory": ["/elsewhere"]}):
            with self.assertRaises(bootstrap.Rejected):
                bootstrap.validate_human(dict(value, **change), metadata)
        with self.assertRaises(bootstrap.Rejected):
            bootstrap.validate_human(value, argparse.Namespace(st_uid=501, st_mode=stat.S_IFDIR | 0o755))

    def test_no_password_or_admin_attributes(self):
        attributes = bootstrap.attributes(502, "EXAMPLE-GUID")
        self.assertEqual(attributes["dsAttrTypeStandard:AuthenticationAuthority"], [";DisabledUser;"])
        self.assertEqual(attributes["dsAttrTypeStandard:UserShell"], ["/usr/bin/false"])
        self.assertEqual(attributes["dsAttrTypeStandard:PrimaryGroupID"], ["20"])
        self.assertFalse(any("Password" in key or "GroupMembership" in key for key in attributes))

    def test_verification_requests_full_native_attribute_name(self):
        expected = {key.rsplit(":", 1)[-1]: value for key, value in bootstrap.attributes(502, "GUID").items()}
        with patch.object(bootstrap, "record", return_value=expected) as record, \
             patch.object(bootstrap.os, "getgrouplist", return_value=[20]), \
             patch.object(bootstrap.pwd, "getpwnam", return_value=argparse.Namespace(pw_uid=502)), \
             patch.object(bootstrap, "command", return_value=b"aws-agent 502\n"):
            bootstrap.verify_account(502, "GUID")
            self.assertIn("dsAttrTypeNative:IsHidden", record.call_args.args[1])
            self.assertNotIn("IsHidden", record.call_args.args[1])

    def test_default_is_plan_and_never_native_creation(self):
        content = {name: b"reviewed" for name in bootstrap.FILES}
        with patch.object(bootstrap, "preflight", return_value=(502, content)), \
             patch.object(bootstrap, "apply") as apply, patch.object(bootstrap, "NativeDirectory") as native, \
             patch.object(bootstrap.sys, "argv", ["bootstrap-local.py"]), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(bootstrap.main(), 0)
            self.assertEqual(json.loads(output.getvalue())["mode"], "plan")
            apply.assert_not_called()
            native.assert_not_called()

    def test_apply_refuses_nonroot_before_preflight_or_writes(self):
        with patch.object(bootstrap.os, "geteuid", return_value=501), \
             patch.object(bootstrap, "preflight") as preflight, patch.object(bootstrap.os, "open") as opened:
            with self.assertRaises(bootstrap.Rejected):
                bootstrap.apply()
            preflight.assert_not_called()
            opened.assert_not_called()

    def test_source_symlinks_and_shared_write_refused(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(bootstrap, "HUMAN_UID", os.getuid()):
            path = Path(directory) / "file"
            path.write_bytes(b"reviewed")
            path.chmod(0o600)
            self.assertEqual(bootstrap.reviewed_bytes(path), b"reviewed")
            link = Path(directory) / "link"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                bootstrap.reviewed_bytes(link)
            path.chmod(0o666)
            with self.assertRaises(bootstrap.Rejected):
                bootstrap.reviewed_bytes(path)

    def test_staging_only_named_files_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(bootstrap, "ACCOUNT_HOME", Path(directory)), \
             patch.object(bootstrap, "FILES", {"executor.py": "agent-runtime/bundle/executor.py"}), \
             patch.object(bootstrap.os, "chown"):
            bootstrap.stage(502, {"executor.py": b"reviewed code"})
            target = Path(directory) / "agent-runtime/bundle/executor.py"
            self.assertEqual(target.read_bytes(), b"reviewed code")
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                bootstrap.stage(502, {"executor.py": b"replacement"})
            self.assertEqual(target.read_bytes(), b"reviewed code")

    def test_only_nonsecret_proxy_policy_is_world_readable(self):
        content = {"executor.py": b"reviewed code", "egress.squid.conf": b"reviewed nonsecret policy"}
        files = {"executor.py": "agent-runtime/bundle/executor.py", "egress.squid.conf": "agent-runtime/proxy/egress.squid.conf"}
        with tempfile.TemporaryDirectory() as directory, patch.object(bootstrap, "ACCOUNT_HOME", Path(directory)), \
             patch.object(bootstrap, "FILES", files), patch.object(bootstrap.os, "chown"):
            previous_umask = os.umask(0o077)
            try:
                bootstrap.stage(502, content)
            finally:
                os.umask(previous_umask)
            self.assertEqual(stat.S_IMODE((Path(directory) / files["egress.squid.conf"]).stat().st_mode), 0o644)
            self.assertEqual(stat.S_IMODE((Path(directory) / files["executor.py"]).stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE((Path(directory) / "agent-runtime/proxy").stat().st_mode), 0o700)
            modes = {item["source"]: item["mode"] for item in bootstrap.plan(502, content)["files"]}
            self.assertEqual(modes, {"executor.py": "0600", "egress.squid.conf": "0644"})


if __name__ == "__main__":
    unittest.main()
