"""Synthetic local authentication records; no AWS, Docker, or model calls."""
import ast
import fcntl
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


auth = load('runtime_auth', 'runtime-auth.py')
ex = load('runtime_auth_executor_fixture', 'executor.py')
runner = load('runtime_auth_runner_fixture', 'run-task.py')
FIXTURE = {'auth_mode': 'chatgpt', 'OPENAI_API_KEY': None,
           'tokens': {'id_token': 'eyJhbGciOiJub25lIn0.eyJzdWIiOiJvZmZsaW5lIn0.signature',
                      'access_token': 'offline-access', 'refresh_token': 'offline-refresh',
                      'account_id': 'offline-account'}}


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        self.directory.chmod(0o700)
        self.path = self.directory / 'auth.json'
        self.quiescent = Mock()

    def write(self, raw):
        self.path.write_bytes(raw)
        self.path.chmod(0o600)

    def state(self, action='status'):
        return auth.authentication_state(ex, self.path, action, self.quiescent)

    def test_missing_and_valid_states_do_not_disclose_authentication(self):
        self.assertEqual(self.state(), {'auth_state': 'missing', 'prepared': False})
        self.assertEqual(self.state('prepare-login'), {'auth_state': 'missing', 'prepared': True})
        self.assertFalse(self.path.exists())
        raw = json.dumps(FIXTURE).encode()
        self.write(raw)
        before = self.path.stat()
        self.assertEqual(self.state(), {'auth_state': 'valid', 'prepared': False})
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertEqual(self.path.stat().st_ino, before.st_ino)
        self.quiescent.assert_called()

    def test_valid_cache_never_replaced_for_login(self):
        raw = json.dumps(FIXTURE).encode()
        self.write(raw)
        with self.assertRaisesRegex(auth.Rejected, '^valid_authentication_preserved$'):
            self.state('prepare-login')
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertEqual(list(self.directory.glob('.invalidated-auth-*')), [])

    def test_exact_sentinel_is_retained_privately_and_recovery_is_idempotent(self):
        self.write(auth.INVALIDATED)
        original = self.path.stat()
        self.assertEqual(self.state(), {'auth_state': 'invalidated', 'prepared': False})
        self.assertTrue(self.path.exists())
        self.assertEqual(self.state('prepare-login'), {'auth_state': 'invalidated', 'prepared': True})
        self.assertFalse(self.path.exists())
        quarantines = list(self.directory.glob('.invalidated-auth-*'))
        self.assertEqual(len(quarantines), 1)
        self.assertEqual(stat.S_IMODE(quarantines[0].stat().st_mode), 0o700)
        saved = quarantines[0] / 'auth.json'
        self.assertEqual(saved.read_bytes(), auth.INVALIDATED)
        self.assertEqual((saved.stat().st_ino, saved.stat().st_mode & 0o777), (original.st_ino, 0o600))
        self.assertEqual(self.state('prepare-login'), {'auth_state': 'missing', 'prepared': True})
        self.assertEqual(list(self.directory.glob('.invalidated-auth-*')), quarantines)

    def test_empty_malformed_api_duplicate_or_similar_sentinel_remains_untouched(self):
        fixtures = (b'', b'not-json', b'[]', b'{"OPENAI_API_KEY":"offline-api"}',
                    auth.INVALIDATED + b'\n',
                    b'{"auth_mode":"chatgpt","tokens":null,"tokens":null}',
                    b'x' * (ex.MAX_MODEL_AUTH + 1))
        for raw in fixtures:
            with self.subTest(size=len(raw)):
                self.write(raw)
                for action in ('status', 'prepare-login'):
                    with self.assertRaisesRegex(auth.Rejected, '^authentication_schema_invalid$'):
                        self.state(action)
                    self.assertEqual(self.path.read_bytes(), raw)
                self.assertEqual(list(self.directory.glob('.invalidated-auth-*')), [])

    def test_auth_file_links_modes_and_fifo_are_rejected_without_blocking(self):
        self.write(auth.INVALIDATED)
        self.path.chmod(0o640)
        with self.assertRaisesRegex(auth.Rejected, 'unsafe_authentication_file'):
            self.state('prepare-login')
        self.path.chmod(0o600)
        link = self.directory / 'other'
        os.link(self.path, link)
        with self.assertRaisesRegex(auth.Rejected, 'unsafe_authentication_file'):
            self.state('prepare-login')
        self.path.unlink()
        self.path.symlink_to(link)
        with self.assertRaises(OSError):
            self.state('prepare-login')
        self.path.unlink()
        os.mkfifo(self.path, 0o600)
        with self.assertRaisesRegex(auth.Rejected, 'unsafe_authentication_file'):
            self.state('prepare-login')
        self.assertEqual(link.read_bytes(), auth.INVALIDATED)

    def test_wrong_owner_or_nonprivate_parent_is_rejected(self):
        self.write(auth.INVALIDATED)
        self.directory.chmod(0o750)
        with self.assertRaisesRegex(auth.Rejected, 'unsafe_authentication_path'):
            self.state()
        self.directory.chmod(0o700)
        with patch.object(auth.os, 'getuid', return_value=os.getuid() + 1):
            with self.assertRaisesRegex(auth.Rejected, 'unsafe_authentication_path'):
                self.state()

    def test_shared_stable_lock_excludes_executor_and_login(self):
        self.write(json.dumps(FIXTURE).encode())
        with ex.model_auth_file(self.path):
            with self.assertRaisesRegex(auth.Rejected, '^authentication_in_use$'):
                self.state('prepare-login')
        lock = self.directory / '.subscription-auth.lock'
        with lock.open('rb') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(auth.Rejected, '^authentication_in_use$'):
                self.state()
        self.quiescent.assert_not_called()

    def test_parent_permissions_rechecked_on_open_descriptor(self):
        self.write(auth.INVALIDATED)
        original_open = os.open

        def open_changed_parent(path, *args, **kwargs):
            if path == self.directory:
                self.directory.chmod(0o750)
            return original_open(path, *args, **kwargs)

        with patch.object(auth.os, 'open', side_effect=open_changed_parent):
            with self.assertRaisesRegex(auth.Rejected, '^unsafe_authentication_path$'):
                self.state('prepare-login')
        self.assertEqual(self.path.read_bytes(), auth.INVALIDATED)

    def test_unsafe_lock_and_nonquiescent_runtime_preserve_sentinel(self):
        self.write(auth.INVALIDATED)
        lock = self.directory / '.subscription-auth.lock'
        lock.symlink_to(self.path)
        with self.assertRaises(OSError):
            self.state('prepare-login')
        lock.unlink()
        self.quiescent.side_effect = auth.Rejected('runtime_not_quiescent')
        with self.assertRaisesRegex(auth.Rejected, '^runtime_not_quiescent$'):
            self.state('prepare-login')
        self.assertEqual(self.path.read_bytes(), auth.INVALIDATED)
        self.assertEqual(list(self.directory.glob('.invalidated-auth-*')), [])

    def test_quarantine_collision_does_not_overwrite_any_file(self):
        self.write(auth.INVALIDATED)
        existing = self.directory / ('.invalidated-auth-' + 'c' * 32)
        existing.mkdir(mode=0o700)
        saved = existing / 'auth.json'
        saved.write_bytes(b'preserve existing evidence')
        with patch.object(auth.secrets, 'token_hex', return_value='c' * 32):
            with self.assertRaises(FileExistsError):
                self.state('prepare-login')
        self.assertEqual(self.path.read_bytes(), auth.INVALIDATED)
        self.assertEqual(saved.read_bytes(), b'preserve existing evidence')

    def test_replaced_authentication_before_rename_is_not_moved(self):
        self.write(auth.INVALIDATED)
        original_mkdir = os.mkdir

        def replace_after_mkdir(*args, **kwargs):
            original_mkdir(*args, **kwargs)
            replacement = self.directory / 'replacement'
            replacement.write_bytes(json.dumps(FIXTURE).encode())
            replacement.chmod(0o600)
            os.replace(replacement, self.path)

        with patch.object(auth.os, 'mkdir', side_effect=replace_after_mkdir):
            with self.assertRaisesRegex(auth.Rejected, '^authentication_changed$'):
                self.state('prepare-login')
        self.assertEqual(json.loads(self.path.read_bytes()), FIXTURE)

    def test_main_output_and_failures_never_include_authentication_or_raw_error(self):
        self.write(json.dumps(FIXTURE).encode())
        for error in (None, RuntimeError('offline-access should never leave the runtime')):
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.object(auth, 'runtime_preflight', return_value=(ex, self.quiescent), side_effect=error), \
                    patch.object(auth, 'MODEL_AUTH', str(self.path), create=True), \
                    patch.object(auth.signal, 'signal'), patch.object(auth.signal, 'setitimer'), \
                    patch.object(auth.sys, 'stdout', stdout), patch.object(auth.sys, 'stderr', stderr):
                code = auth.main(['--action', 'status'])
            output = stdout.getvalue() + stderr.getvalue()
            for token in FIXTURE['tokens'].values():
                self.assertNotIn(token, output)
            if error:
                self.assertEqual(code, 1)
                self.assertEqual(json.loads(stderr.getvalue())['error'], 'runtime_boundary_failed')
                self.assertEqual(stdout.getvalue(), '')
            else:
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(stdout.getvalue()),
                                 {'schema': 1, 'action': 'status', 'runtime_ready': True,
                                  'auth_state': 'valid', 'prepared': False})

    def test_composition_preserves_shared_proof_checks_without_runtime_human_import(self):
        raw = Path(auth.__file__).read_bytes()
        source = auth.compose(runner, raw)
        ast.parse(source)
        self.assertIn(runner.COMMON, source)
        self.assertIn(runner.PROOFS, source)
        self.assertTrue(source.endswith(raw.decode()))
        self.assertNotIn(runner.SOURCE, source)
        self.assertNotIn('import run_task', source)
        changed = types.SimpleNamespace(**vars(runner))
        changed.SOURCE_SHA = '0' * 64
        with self.assertRaisesRegex(auth.Rejected, '^runtime_boundary_failed$'):
            auth.compose(changed, raw)

    def test_standalone_runtime_preflight_fails_without_composed_contract(self):
        with patch.object(auth.os, 'open', side_effect=AssertionError('unexpected file read')):
            with self.assertRaisesRegex(auth.Rejected, '^runtime_boundary_failed$'):
                auth.runtime_preflight()


if __name__ == '__main__':
    unittest.main()
