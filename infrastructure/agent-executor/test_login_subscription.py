"""Synthetic credentials only; no Docker, AWS, model, or login calls."""
import argparse
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("login_subscription", Path(__file__).with_name("login-subscription.py"))
login = importlib.util.module_from_spec(spec)
spec.loader.exec_module(login)

AUTH = {"auth_mode": "chatgpt", "OPENAI_API_KEY": None,
        "tokens": {"id_token": "eyJhbGciOiJub25lIn0.eyJzdWIiOiJvZmZsaW5lIn0.signature",
                   "access_token": "offline-access", "refresh_token": "offline-refresh", "account_id": "offline-account"}}
MANIFEST = {"image": "sha256:" + "a" * 64, "network": "aws-agent-internal", "proxy": "http://egress:3128",
            "proxy_identity": {"container_id": "b" * 64, "config_sha256": "d" * 64}}
NETWORK = "c" * 64
IP = "172.30.50.2"


def report():
    return {"schema_version": 1, "activation_ready": False, "network_checks_status": "passed", "proxy_ipv4": IP,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "launcher_evidence": {"image": MANIFEST["image"], "network_id": NETWORK, "proxy_container_id": "b" * 64,
                                  "proxy_config_sha256": "d" * 64}}


def auth_tar(mode=0o600, link=False, value=AUTH):
    raw = io.BytesIO()
    payload = json.dumps(value).encode()
    with tarfile.open(fileobj=raw, mode="w:") as archive:
        entry = tarfile.TarInfo("auth.json")
        entry.mode, entry.uid, entry.gid = mode, 10001, 10001
        if link:
            entry.type, entry.linkname = tarfile.SYMTYPE, "/outside"
        else:
            entry.size = len(payload)
        archive.addfile(entry, None if link else io.BytesIO(payload))
    return raw.getvalue()


class LoginTests(unittest.TestCase):
    def test_default_is_offline(self):
        with patch.object(login.sys, "argv", ["login-subscription.py"]), \
             patch.object(login, "login") as called, patch.object(login.sys, "stdout", new_callable=io.StringIO):
            self.assertEqual(login.main(), 0)
            called.assert_not_called()

    def test_only_expected_device_url_and_prompted_code_are_displayed(self):
        state = {}
        for line in ("ABCD-EFGH", "https://untrusted.example/codex/device", AUTH["tokens"]["access_token"]):
            self.assertIsNone(login.prompt_line(line, state))
        self.assertEqual(login.prompt_line("\x1b[94m" + login.DEVICE_URL + "\x1b[0m", state), login.DEVICE_URL)
        self.assertIsNone(login.prompt_line("2. Enter this one-time code (expires in 15 minutes)", state))
        self.assertEqual(login.prompt_line("ABCD-EFGH", state), "One-time device code: ABCD-EFGH")
        self.assertIsNone(login.prompt_line("ABCD-EFGH", state))

    def test_network_evidence_must_be_recent_passed_and_exact(self):
        login.verify_network_evidence(report(), MANIFEST, NETWORK, IP)
        for changed in ({"network_checks_status": "inconclusive"}, {"launcher_evidence": {}},
                        {"launcher_evidence": dict(report()["launcher_evidence"], proxy_config_sha256="e" * 64)},
                        {"finished_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()},
                        {"proxy_ipv4": "172.30.50.3"}):
            with self.assertRaises(login.ex.Rejected):
                login.verify_network_evidence(dict(report(), **changed), MANIFEST, NETWORK, IP)

    def test_copy_accepts_only_private_regular_chatgpt_auth(self):
        self.assertEqual(login.extract_auth(auth_tar()), AUTH)
        for raw in (auth_tar(mode=0o644), auth_tar(link=True), auth_tar(value={"OPENAI_API_KEY": "offline-api"}),
                    b"x" * 131073):
            with self.assertRaises(login.ex.Rejected):
                login.extract_auth(raw)

    def test_new_target_is_private_atomic_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "auth.json"
            with login.new_auth_target(path) as save:
                original = path.stat().st_ino
                save(AUTH)
            self.assertNotEqual(path.stat().st_ino, original)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError), login.new_auth_target(path):
                pass
            self.assertEqual(json.loads(path.read_text()), AUTH)
            link = path.parent / "link"
            link.symlink_to(path)
            with self.assertRaises(FileExistsError), login.new_auth_target(link):
                pass

    def test_abort_removes_only_its_empty_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "auth.json"
            with self.assertRaises(RuntimeError), login.new_auth_target(path):
                raise RuntimeError("offline abort")
            self.assertFalse(path.exists())
            with login.new_auth_target(path) as save:
                path.unlink()
                path.write_text("preserve-other-writer")
                with self.assertRaises(login.ex.Rejected):
                    save(AUTH)
            self.assertEqual(path.read_text(), "preserve-other-writer")

    def test_login_uses_exact_controls_and_never_prints_copied_auth(self):
        real_popen = subprocess.Popen
        observed = []
        prompt = login.DEVICE_URL + "\n2. Enter this one-time code\nABCD-EFGH\n" + login.READY + "\n"
        def fake_popen(command, **kwargs):
            observed.append((command, kwargs))
            return real_popen([sys.executable, "-I", "-c", "import time; print(" + repr(prompt) + ", flush=True); time.sleep(30)"], **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "auth.json"
            args = argparse.Namespace(manifest="unused", network_evidence="unused", output_auth=str(path))
            with patch.object(login.ex, "require_runtime_user"), \
                 patch.object(login.ex, "operator_json", side_effect=[MANIFEST, report()]), \
                 patch.object(login.ex, "inspect_network", return_value=(NETWORK, IP)), \
                 patch.object(login.ex, "bounded_command", return_value=auth_tar()) as copy, \
                 patch.object(login.subprocess, "Popen", side_effect=fake_popen), \
                 patch.object(login.subprocess, "run", return_value=argparse.Namespace(returncode=0)) as cleanup, \
                 patch.object(login.sys, "stdout", new_callable=io.StringIO) as output:
                login.login(args)
            self.assertEqual(json.loads(path.read_text()), AUTH)
            for token in AUTH["tokens"].values():
                self.assertNotIn(token, output.getvalue())
            command, options = observed[0]
            for flag in ("--read-only", "--cap-drop", "--log-driver", "--tmpfs"):
                self.assertIn(flag, command)
            self.assertNotIn("--rm", command)
            self.assertFalse({"AWS_ACCESS_KEY_ID", "OPENAI_API_KEY", "CODEX_API_KEY"}.intersection(options["env"]))
            self.assertIn("time.sleep(120)", command[-1])
            self.assertEqual(copy.call_args.kwargs["limit"], 131072)
            cleanup.assert_called_once()


if __name__ == "__main__":
    unittest.main()
