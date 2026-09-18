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
import tempfile
from types import SimpleNamespace
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


def reader():
    namespace = {"__name__": "reader_test"}
    exec(login.READ_AUTH, namespace)
    return namespace["private_auth_bytes"]


def container_metadata(original, **overrides):
    def metadata(descriptor):
        info = original(descriptor)
        fields = {key: getattr(info, key) for key in (
            "st_mode", "st_nlink", "st_dev", "st_ino", "st_size", "st_mtime_ns")}
        fields.update(st_uid=10001, st_gid=10001)
        fields.update(overrides)
        return SimpleNamespace(**fields)
    return metadata


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

    def test_authentication_parser_preserves_strict_schema_and_bound(self):
        self.assertEqual(login.parse_auth(json.dumps(AUTH).encode()), AUTH)
        for raw in (b"not JSON", b"[]", json.dumps({"OPENAI_API_KEY": "offline-api"}).encode(),
                    b"x" * (login.ex.MAX_MODEL_AUTH + 1)):
            with self.assertRaises(login.ex.Rejected):
                login.parse_auth(raw)

    def test_container_reader_rejects_symlink_nonregular_hardlink_and_mode(self):
        read = reader()
        original = os.fstat
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "auth.json"
            raw = json.dumps(AUTH).encode()
            path.write_bytes(raw); path.chmod(0o600)
            link = Path(directory) / "link"
            link.symlink_to(path)
            fifo = Path(directory) / "fifo"
            os.mkfifo(fifo, 0o600)
            with patch.object(os, "fstat", side_effect=container_metadata(original)):
                self.assertEqual(read(path, login.ex.MAX_MODEL_AUTH), raw)
                for bad in (link, fifo):
                    with self.subTest(path=bad.name), self.assertRaises((OSError, ValueError)):
                        read(bad, login.ex.MAX_MODEL_AUTH)
                hard = Path(directory) / "hard"
                os.link(path, hard)
                with self.assertRaises(ValueError):
                    read(path, login.ex.MAX_MODEL_AUTH)
                hard.unlink()
                path.chmod(0o644)
                with self.assertRaises(ValueError):
                    read(path, login.ex.MAX_MODEL_AUTH)

    def test_container_reader_rejects_wrong_ownership_empty_and_oversize(self):
        read = reader()
        original = os.fstat
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "auth.json"
            path.write_bytes(json.dumps(AUTH).encode()); path.chmod(0o600)
            for changed in ({"st_uid": 0}, {"st_gid": 0}):
                with self.subTest(changed=changed), \
                        patch.object(os, "fstat", side_effect=container_metadata(original, **changed)), \
                        self.assertRaises(ValueError):
                    read(path, login.ex.MAX_MODEL_AUTH)
            for raw in (b"", b"x" * (login.ex.MAX_MODEL_AUTH + 1)):
                path.write_bytes(raw)
                with patch.object(os, "fstat", side_effect=container_metadata(original)), self.assertRaises(ValueError):
                    read(path, login.ex.MAX_MODEL_AUTH)

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

    def test_invalid_schema_does_not_save_authentication(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "auth.json"
            with self.assertRaises(login.ex.Rejected), login.new_auth_target(path) as save:
                save(login.parse_auth(b'{"OPENAI_API_KEY":"offline-invalid"}'))
            self.assertFalse(path.exists())

    def test_failure_diagnostics_expose_only_fixed_phase_and_exception_class(self):
        def failure(args, phase):
            phase("validate-auth")
            raise ValueError("private-synthetic-error-text")
        with patch.object(login, "_login", side_effect=failure), \
                patch.object(login.sys, "stderr", new_callable=io.StringIO) as output, \
                self.assertRaises(ValueError):
            login.login(None)
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(events[-1], {"status": "subscription_login_failed", "phase": "validate-auth",
                                     "error_class": "ValueError"})
        self.assertNotIn("private-synthetic-error-text", output.getvalue())

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
                 patch.object(login.ex, "bounded_command", return_value=json.dumps(AUTH).encode()) as read, \
                 patch.object(login.subprocess, "Popen", side_effect=fake_popen), \
                 patch.object(login.subprocess, "run", return_value=argparse.Namespace(returncode=0)) as cleanup, \
                 patch.object(login.sys, "stderr", new_callable=io.StringIO) as diagnostics, \
                 patch.object(login.sys, "stdout", new_callable=io.StringIO) as output:
                login.login(args)
            self.assertEqual(json.loads(path.read_text()), AUTH)
            for token in AUTH["tokens"].values():
                self.assertNotIn(token, output.getvalue())
                self.assertNotIn(token, diagnostics.getvalue())
            command, options = observed[0]
            for flag in ("--read-only", "--cap-drop", "--log-driver", "--tmpfs"):
                self.assertIn(flag, command)
            self.assertNotIn("--rm", command)
            self.assertFalse({"AWS_ACCESS_KEY_ID", "OPENAI_API_KEY", "CODEX_API_KEY"}.intersection(options["env"]))
            self.assertIn("time.sleep(120)", command[-1])
            self.assertEqual(read.call_args.kwargs["limit"], login.ex.MAX_MODEL_AUTH)
            read_command = read.call_args.args[0]
            self.assertEqual(read_command[:4], ["docker", "exec", "--user", "10001:10001"])
            self.assertEqual(read_command[5:], ["/usr/local/bin/python3", "-I", "-B", "-c", login.READ_AUTH])
            self.assertEqual([json.loads(line)["phase"] for line in diagnostics.getvalue().splitlines()],
                             ["login", "client-complete", "read-auth", "validate-auth", "save-auth"])
            cleanup.assert_called_once()


if __name__ == "__main__":
    unittest.main()
