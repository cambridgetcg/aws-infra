"""Offline smoke-runner tests: mocked processes and synthetic bytes in local pipes."""
from contextlib import ExitStack
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

PATH = Path(__file__).with_name('run-inventory-smoke.py')
SPEC = importlib.util.spec_from_file_location('inventory_smoke', PATH)
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


class SmokeRunnerTests(unittest.TestCase):
    def setUp(self):
        smoke.CHILDREN.clear()

    def fixture(self, ready=True, issuer_code=0, result_role=None):
        calls, descriptors = [], set()
        state = {}
        original_open = os.open

        class Child:
            pid = 123456789

            def __init__(self, code=0):
                self.code, self.stdout = code, None

            def poll(self):
                return self.code

            def wait(self, timeout=None):
                return self.code

        def close(fd):
            os.close(fd)
            descriptors.discard(fd)

        def fake_popen(argv, **kwargs):
            calls.append((argv, kwargs))
            if len(calls) == 1:
                self.assertEqual(kwargs.get('process_group'), 0)
                self.assertNotIn('start_new_session', kwargs)
                self.assertEqual(argv[:5], ['/usr/bin/sudo', '-n', '-u', 'aws-agent', '-H'])
                self.assertEqual(kwargs['env']['HOME'], smoke.HUMAN_HOME)
                state['input'] = os.dup(kwargs['stdin'])
                reader, state['output'] = os.pipe()
                descriptors.update((state['input'], state['output']))
                child = Child()
                child.stdout = os.fdopen(reader, 'rb')
                os.write(state['output'], smoke.READY if ready else b'INVALID READY\n')
                if not ready:
                    close(state['input']); close(state['output'])
                return child
            self.assertTrue(ready)
            self.assertTrue(kwargs.get('start_new_session'))
            self.assertEqual(len(kwargs['pass_fds']), 1)
            handoff = kwargs['pass_fds'][0]
            self.assertGreaterEqual(handoff, 3)
            self.assertEqual(str(handoff), argv[-1])
            self.assertFalse(any(key.startswith('AWS_') for key in kwargs['env']))
            # The fixture's simulated runtime consumes these nonsecret bytes;
            # the parent runner never reads the handoff pipe.
            os.write(handoff, b'SYNTHETIC-NONSECRET')
            self.assertEqual(os.read(state['input'], 64), b'SYNTHETIC-NONSECRET')
            close(state['input'])
            if issuer_code == 0:
                value = {'task_id': 'inventory-smoke', 'account_id': '034362054546',
                         'principal_id': (result_role or smoke.ROLE['role_id']) + ':fixture',
                         'principal_arn': 'arn:aws:sts::034362054546:assumed-role/'
                         + smoke.ROLE['role_arn'].rsplit('/', 1)[1] + '/fixture',
                         'expires_at': '2026-09-18T22:00:00Z', 'result': 'Synthetic metadata only\u001b'}
                os.write(state['output'], json.dumps(value).encode())
            close(state['output'])
            return Child(issuer_code)

        def fake_open(path, *args, **kwargs):
            return original_open(os.devnull, os.O_RDONLY) if str(path) == '/dev/tty' else original_open(path, *args, **kwargs)

        stack = ExitStack()
        for context in (
            patch.object(smoke, 'source_bytes', return_value=b'fixture'),
            patch.object(smoke, 'private_json', return_value={}),
            patch.object(smoke.os, 'getuid', return_value=501),
            patch.object(smoke.os, 'geteuid', return_value=501),
            patch.object(smoke.os, 'open', side_effect=fake_open),
            patch.object(smoke.os, 'isatty', return_value=True),
            patch.dict(os.environ, {'HOME': smoke.HUMAN_HOME}, clear=True),
            patch.object(smoke.subprocess, 'Popen', side_effect=fake_popen),
        ):
            stack.enter_context(context)
        self.addCleanup(stack.close)
        self.addCleanup(lambda: [os.close(fd) for fd in tuple(descriptors)])
        return calls

    def test_ready_gates_private_pipe_and_preserves_terminal(self):
        calls = self.fixture()
        output = smoke.live_task()
        self.assertEqual(json.loads(output)['result'], 'Synthetic metadata only\u001b')
        self.assertNotIn('\x1b', output)
        self.assertEqual(len(calls), 2)

    def test_invalid_ready_never_starts_issuer(self):
        calls = self.fixture(ready=False)
        with self.assertRaises(RuntimeError):
            smoke.live_task()
        self.assertEqual(len(calls), 1)

    def test_failed_issuance_cannot_return_success(self):
        self.fixture(issuer_code=1)
        with self.assertRaises(RuntimeError):
            smoke.live_task()

    def test_result_with_wrong_role_is_rejected(self):
        self.fixture(result_role='AROAUNEXPECTEDROLE')
        with self.assertRaisesRegex(RuntimeError, 'result_inventory_identity_mismatch'):
            smoke.live_task()

    def test_reviewed_executor_pin_matches_maintained_source(self):
        self.assertEqual(hashlib.sha256(PATH.with_name('executor.py').read_bytes()).hexdigest(), smoke.SOURCE_SHA)

    def test_default_mode_opens_no_credential_files_or_processes(self):
        output = io.StringIO()
        with patch('sys.argv', [str(PATH)]), patch('sys.stdout', output), \
                patch.object(smoke.os, 'open', side_effect=AssertionError('unexpected low-level file access')), \
                patch.object(smoke.subprocess, 'Popen', side_effect=AssertionError('unexpected process')):
            with self.assertRaises(SystemExit) as result:
                runpy.run_path(str(PATH), run_name='__main__')
        self.assertEqual(result.exception.code, 0)
        self.assertEqual(json.loads(output.getvalue())['mode'], 'offline_plan')


if __name__ == '__main__':
    unittest.main()
