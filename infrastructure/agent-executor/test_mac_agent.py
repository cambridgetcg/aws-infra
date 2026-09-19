"""Offline queue/authentication tests: private fixtures, no live service calls."""
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch


PATH = Path(__file__).with_name('mac-agent.py')
SPEC = importlib.util.spec_from_file_location('mac_agent_fixture', PATH)
agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent)
START_SESSION = agent.start_session
REAL_POPEN = subprocess.Popen
REAL_RUN = subprocess.run


def validate_fixture(task_path, archive_path, tier):
    """The runner's already-tested input checks are outside these queue tests."""
    raw, archive = Path(task_path).read_bytes(), Path(archive_path).read_bytes()
    task = json.loads(raw)
    metadata = {'task_sha256': hashlib.sha256(raw).hexdigest(),
                'archive_sha256': hashlib.sha256(archive).hexdigest(),
                'task_bytes': len(raw), 'archive_bytes': len(archive)}
    return task, struct.pack('!IQ', len(raw), len(archive)) + raw + archive, metadata


class MacAgentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.base.chmod(0o700)
        self.root = self.base / 'automation'
        self.root.mkdir(mode=0o700)
        for name in ('jobs', 'support'):
            (self.root / name).mkdir(mode=0o700)
        self.source = self.base / 'source'
        self.source.mkdir(mode=0o700)
        for name in ('mac-agent.py', 'runtime-auth.py', 'run-task.py', 'executor.py'):
            self.file(self.source / name, b'# synthetic source; never contacts services\n')
        self.task = self.base / 'task.json'
        self.archive = self.base / 'input.tar'
        self.file(self.task, json.dumps({'task_id': 'offline-test', 'model': 'gpt-5.6-luna',
                                      'prompt': 'Synthetic read-only task.'}).encode())
        self.file(self.archive, b'synthetic archive: runner validation stubbed')
        self.runner = types.SimpleNamespace(
            validate_inputs=Mock(side_effect=validate_fixture),
            PROFILES={'inventory': 'cambridge-agent-inventory', 'iam-audit': 'cambridge-iam-audit'},
            ROLES={'inventory': {'role_id': 'fixture-inventory'}, 'iam-audit': {'role_id': 'fixture-audit'}},
            executor_module=Mock(return_value=types.SimpleNamespace(check_identity=Mock())))
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in (('ROOT', self.root), ('HERE', self.source), ('UID', os.getuid()),
                            ('HUMAN', str(self.base)), ('SESSION_END', None), ('LAST_TICKET', 0),
                            ('CHILD', None), ('LOADED_SHA', agent.digest((self.source / 'mac-agent.py').read_bytes()))):
            self.stack.enter_context(patch.object(agent, name, value))
        self.stack.enter_context(patch.object(agent, 'runner_module', return_value=self.runner))
        self.launch = self.stack.enter_context(patch.object(agent, 'start_session', return_value={'status': 'session_active'}))
        # Any unplanned process creation would be a real auth/browser/runtime action.
        self.stack.enter_context(patch.object(agent.subprocess, 'Popen', side_effect=AssertionError('unexpected process')))
        self.stack.enter_context(patch.object(agent.subprocess, 'run', side_effect=AssertionError('unexpected command')))
        self.stdout = io.StringIO()
        self.stack.enter_context(patch('sys.stdout', self.stdout))

    def file(self, path, raw):
        path.write_bytes(raw)
        path.chmod(0o600)

    def queue(self, kind='submit', tier='inventory'):
        result = agent.submit(types.SimpleNamespace(command=kind, task=self.task, archive=self.archive, tier=tier))
        return self.root / 'jobs' / result['job']

    def state(self, path):
        return json.loads((path / 'status.json').read_bytes())

    def outcome(self, path, aws='ready', runtime=None, code=0, output=None):
        with patch.object(agent, 'aws_identity', return_value=aws) as identity, \
                patch.object(agent, 'aws_login') as login, \
                patch.object(agent, 'runtime_auth', return_value=runtime or {'auth_state': 'valid'}) as auth, \
                patch.object(agent, 'support_action') as support, \
                patch.object(agent, 'task_command', return_value=['synthetic-task']) as command, \
                patch.object(agent, 'run_process', return_value=(code, output or b'{"result":"fixture result"}', b'')) as child:
            agent.process_job(path)
        return identity, login, auth, support, command, child

    def test_plan_defaults_to_inventory_and_never_opens_session(self):
        for tier in (None, 'iam-audit'):
            self.stdout.seek(0); self.stdout.truncate(0)
            args = ['plan', '--task', str(self.task), '--archive', str(self.archive)]
            if tier:
                args += ['--tier', tier]
            self.assertEqual(agent.main(args), 0)
            value = json.loads(self.stdout.getvalue())
            self.assertEqual(value['tier'], tier or 'inventory')
            self.assertFalse(value['authentication_started'])
            self.assertNotIn('Synthetic read-only task.', self.stdout.getvalue())
        self.assertEqual(list((self.root / 'jobs').iterdir()), [])
        self.launch.assert_not_called()

    def test_submit_snapshots_inputs_privately_and_publishes_ready_last(self):
        writes = []
        original = agent.write_new

        def write(path, raw):
            writes.append(path.name)
            return original(path, raw)

        with patch.object(agent, 'write_new', side_effect=write):
            path = self.queue()
        self.assertEqual(writes[-1], 'ready')
        self.assertEqual((path / 'task.json').read_bytes(), self.task.read_bytes())
        self.assertEqual((path / 'input.tar').read_bytes(), self.archive.read_bytes())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(item.stat().st_mode) == 0o600 for item in path.iterdir()))
        before = agent.validate_request(path, self.runner)
        self.file(self.task, b'{"changed":"original input after submission"}')
        self.assertEqual(agent.validate_request(path, self.runner), before)
        self.assertEqual(self.state(path)['execution_started'], False)

    def test_changed_queued_source_or_input_blocks_before_any_authentication(self):
        for filename in ('executor.py', 'input.tar'):
            with self.subTest(filename=filename):
                path = self.queue()
                target = self.source / filename if filename.endswith('.py') else path / filename
                original = target.read_bytes()
                self.file(target, original + b'changed')
                calls = self.outcome(path)
                state = self.state(path)
                self.assertEqual((state['status'], state['execution_started']), ('blocked', False))
                self.assertIn(state['reason'], ('queued_source_changed_resubmit', 'queued_inputs_changed'))
                for call in calls:
                    call.assert_not_called()
                self.file(target, original)

    def test_resume_preserves_job_and_rechecks_snapshot_before_requeue(self):
        path = self.queue()
        agent.receipt(path, status='blocked', reason='sso_login_required')
        request = (path / 'request.json').read_bytes()
        self.launch.reset_mock()
        self.assertEqual(agent.resume(path.name), {'job': path.name, 'status': 'queued'})
        self.assertEqual((path / 'request.json').read_bytes(), request)
        self.assertFalse(self.state(path)['execution_started'])
        self.launch.assert_called_once()
        agent.receipt(path, status='blocked')
        self.file(path / 'input.tar', b'edited after block')
        self.launch.reset_mock()
        with self.assertRaisesRegex(agent.Stopped, '^queued_inputs_changed$'):
            agent.resume(path.name)
        self.launch.assert_not_called()
        self.assertEqual(self.state(path)['status'], 'blocked')

    def test_resume_rejects_running_failed_succeeded_and_uncertain_start(self):
        for status, started in (('running', True), ('failed', True), ('succeeded', True),
                                ('blocked', True), ('queued', True), ('validating', False),
                                ('checking_aws', False), ('failed', False)):
            with self.subTest(status=status, started=started):
                path = self.queue()
                agent.receipt(path, status=status, execution_started=started)
                self.launch.reset_mock()
                with self.assertRaisesRegex(agent.Stopped, '^execution_may_have_started_create_new_reviewed_task$'):
                    agent.resume(path.name)
                self.launch.assert_not_called()
                self.assertEqual(self.state(path)['status'], status)

    def test_request_tier_or_job_disagreement_blocks_before_authentication(self):
        for change in ({'tier': 'iam-audit'}, {'job': 'f' * 32}):
            with self.subTest(change=change):
                path = self.queue()
                agent.receipt(path, **change)
                calls = self.outcome(path)
                self.assertEqual(self.state(path)['status'], 'blocked')
                self.assertEqual(self.state(path)['reason'], 'queued_identity_changed')
                for call in calls:
                    call.assert_not_called()

    def test_valid_sessions_reused_and_started_flag_is_durable_before_child(self):
        path = self.queue()

        def child(command, *args):
            self.assertEqual(command, ['synthetic-task'])
            self.assertEqual((self.state(path)['status'], self.state(path)['execution_started']), ('running', True))
            return 0, b'{"result":"fixture result"}', b''

        with patch.object(agent, 'aws_identity', return_value='ready'), \
                patch.object(agent, 'aws_login') as login, \
                patch.object(agent, 'runtime_auth', return_value={'auth_state': 'valid'}), \
                patch.object(agent, 'support_action') as support, \
                patch.object(agent, 'task_command', return_value=['synthetic-task']), \
                patch.object(agent, 'run_process', side_effect=child) as run:
            agent.process_job(path)
            self.assertEqual(self.state(path)['status'], 'succeeded')
            with self.assertRaisesRegex(agent.Stopped, '^job_cannot_be_replayed$'):
                agent.process_job(path)
        self.assertEqual(run.call_count, 1)
        login.assert_not_called(); support.assert_not_called()
        self.assertEqual(stat.S_IMODE((path / 'result.json').stat().st_mode), 0o600)

    def test_only_recognized_sso_expiry_or_absence_requires_login(self):
        allowed = [
            b'Error when retrieving token from sso: Token has expired and refresh failed',
            b'The SSO session associated with this profile has expired or is otherwise invalid. To refresh this SSO session run aws sso login.',
            b'\nError loading SSO Token: Token for fixture-session does not exist\n',
        ]
        denied = [
            b'An error occurred (AccessDenied) when calling GetCallerIdentity',
            b'An error occurred (InvalidClientTokenId) when calling GetCallerIdentity',
            b'An error occurred (ExpiredToken) when calling GetCallerIdentity',
            b'Error loading SSO Token: Token for fixture-session is invalid',
            b'Error loading SSO Token: Token for fixture-session contains no accessToken',
            b'Error loading SSO Token: Token for fixture-session does not exist but path is malformed',
            b'Error loading SSO Token: missing required metadata',
            b'The config profile (cambridge-agent-inventory) could not be found',
            b'SSL validation failed', b'Connect timeout on endpoint URL', b'',
        ]
        for message in allowed:
            self.assertEqual(agent.aws_error(message), 'sso_login_required', message)
        for message in denied:
            self.assertEqual(agent.aws_error(message), 'aws_check_failed', message)

    def test_sso_login_success_still_requires_matching_second_identity(self):
        for second in ('ready', 'aws_check_failed', 'sso_login_required'):
            with self.subTest(second=second):
                path = self.queue()
                with patch.object(agent, 'aws_identity', side_effect=['sso_login_required', second]) as identity, \
                        patch.object(agent, 'aws_login') as login, \
                        patch.object(agent, 'runtime_auth', return_value={'auth_state': 'valid'}), \
                        patch.object(agent, 'task_command', return_value=['synthetic-task']), \
                        patch.object(agent, 'run_process', return_value=(0, b'{"result":"ok"}', b'')) as child:
                    agent.process_job(path)
                login.assert_called_once_with('cambridge-agent-inventory')
                self.assertEqual(identity.call_count, 2)
                self.assertEqual(child.call_count, 1 if second == 'ready' else 0)
                self.assertEqual(self.state(path)['status'], 'succeeded' if second == 'ready' else 'blocked')

    def test_generic_aws_failure_does_not_login_or_fall_back(self):
        path = self.queue(tier='iam-audit')
        identity, login, auth, support, command, child = self.outcome(path, aws='aws_check_failed')
        identity.assert_called_once_with(self.runner, 'iam-audit')
        for call in (login, auth, support, command, child):
            call.assert_not_called()
        self.assertEqual(self.state(path)['reason'], 'aws_check_failed')

    def test_model_renewal_requires_proofs_prepare_login_and_saved_auth_before_execution(self):
        for initial in ('missing', 'invalidated'):
            with self.subTest(initial=initial):
                path = self.queue()
                order = []
                states = iter([initial, initial, 'valid', 'valid'])

                def auth(runner, action='status', expected_sha=None):
                    self.assertEqual(expected_sha, agent.source_pins()['runtime-auth.py'])
                    order.append('auth:' + action)
                    return {'auth_state': next(states)}

                with patch.object(agent, 'aws_identity', return_value='ready'), \
                        patch.object(agent, 'runtime_auth', side_effect=auth), \
                        patch.object(agent, 'support_action', side_effect=lambda name: order.append(name)), \
                        patch.object(agent, 'task_command', return_value=['synthetic-task']), \
                        patch.object(agent, 'run_process', side_effect=lambda *args: (order.append('task') or (0, b'{"result":"ok"}', b''))):
                    agent.process_job(path)
                self.assertEqual(order, ['auth:status', 'refresh-proofs', 'auth:prepare-login',
                                         'login-subscription', 'auth:status', 'task', 'auth:status'])
                self.assertEqual(self.state(path)['status'], 'succeeded')

    def test_login_without_saved_auth_remains_blocked_before_task(self):
        path = self.queue()
        with patch.object(agent, 'aws_identity', return_value='ready'), \
                patch.object(agent, 'runtime_auth', return_value={'auth_state': 'missing'}), \
                patch.object(agent, 'support_action'), \
                patch.object(agent, 'task_command') as task:
            agent.process_job(path)
        task.assert_not_called()
        self.assertEqual((self.state(path)['status'], self.state(path)['execution_started']), ('blocked', False))
        self.assertEqual(self.state(path)['reason'], 'codex_login_not_saved')

    def test_short_session_blocks_new_browser_flow_before_login(self):
        for provider in ('aws', 'codex'):
            with self.subTest(provider=provider):
                path = self.queue()
                with patch.object(agent, 'SESSION_END', time.monotonic() + 60):
                    _, login, _, support, command, child = self.outcome(
                        path, aws='sso_login_required' if provider == 'aws' else 'ready',
                        runtime={'auth_state': 'missing'})
                login.assert_not_called(); support.assert_not_called()
                command.assert_not_called(); child.assert_not_called()
                self.assertEqual(self.state(path)['status'], 'blocked')
                self.assertEqual(self.state(path)['reason'], 'new_session_needed_for_' + provider + '_login')

    def test_task_failures_and_invalid_results_never_become_resumable(self):
        for code, output in ((1, b'private child diagnostics'), (0, b'invalid JSON'), (0, b'{"result":false}')):
            with self.subTest(code=code, output=output):
                path = self.queue()
                self.outcome(path, code=code, output=output)
                self.assertEqual((self.state(path)['status'], self.state(path)['execution_started']), ('failed', True))
                with self.assertRaisesRegex(agent.Stopped, '^execution_may_have_started_create_new_reviewed_task$'):
                    agent.resume(path.name)
                self.assertNotIn('private child diagnostics', self.stdout.getvalue())

    def test_empty_and_whitespace_results_preserve_evidence_check_cleanup_and_never_resume(self):
        for text in ('', ' \t\r\n', '\u2003'):
            with self.subTest(text=text):
                path = self.queue()
                raw = json.dumps({'result': text, 'fixture_metadata': 'private-evidence-marker'}).encode()
                order = []

                def auth(runner, action='status', expected_sha=None):
                    if order:
                        order.append('post_task_check')
                        self.assertEqual((path / 'result.json').read_bytes(), raw)
                        self.assertEqual(self.state(path)['status'], 'running')
                        self.assertTrue(self.state(path)['execution_started'])
                    else:
                        order.append('pre_task_check')
                    return {'auth_state': 'valid'}

                def child(*args):
                    order.append('task')
                    return 0, raw, b''

                with patch.object(agent, 'aws_identity', return_value='ready'), \
                        patch.object(agent, 'runtime_auth', side_effect=auth) as checks, \
                        patch.object(agent, 'task_command', return_value=['synthetic-task']), \
                        patch.object(agent, 'run_process', side_effect=child) as process:
                    agent.process_job(path)
                    self.assertEqual(order, ['pre_task_check', 'task', 'post_task_check'])
                    self.assertEqual(checks.call_count, 2)
                    self.assertEqual((self.state(path)['status'], self.state(path)['execution_started']),
                                     ('failed', True))
                    self.assertEqual(self.state(path)['reason'], 'empty_task_result_no_automatic_replay')
                    self.assertEqual((path / 'result.json').read_bytes(), raw)
                    self.assertEqual(stat.S_IMODE((path / 'result.json').stat().st_mode), 0o600)
                    self.assertEqual(stat.S_IMODE((path / 'status.json').stat().st_mode), 0o600)
                    self.launch.reset_mock()
                    with self.assertRaisesRegex(agent.Stopped, '^execution_may_have_started_create_new_reviewed_task$'):
                        agent.resume(path.name)
                    with self.assertRaisesRegex(agent.Stopped, '^job_cannot_be_replayed$'):
                        agent.process_job(path)
                    self.launch.assert_not_called()
                    process.assert_called_once()
                self.assertNotIn('private-evidence-marker', self.stdout.getvalue())

    def test_empty_result_does_not_mask_failed_post_task_check(self):
        path = self.queue()
        raw = b'{"result":""}'
        with patch.object(agent, 'aws_identity', return_value='ready'), \
                patch.object(agent, 'runtime_auth', side_effect=[{'auth_state': 'valid'}, {'auth_state': 'invalidated'}]) as checks, \
                patch.object(agent, 'task_command', return_value=['synthetic-task']), \
                patch.object(agent, 'run_process', return_value=(0, raw, b'')):
            agent.process_job(path)
        self.assertEqual(checks.call_count, 2)
        self.assertEqual((self.state(path)['status'], self.state(path)['execution_started']), ('failed', True))
        self.assertEqual(self.state(path)['reason'], 'post_task_cleanup_or_auth_failed')
        self.assertEqual((path / 'result.json').read_bytes(), raw)
        with self.assertRaisesRegex(agent.Stopped, '^execution_may_have_started_create_new_reviewed_task$'):
            agent.resume(path.name)

    def test_nonempty_result_with_surrounding_whitespace_is_accepted_unchanged(self):
        path = self.queue()
        raw = json.dumps({'result': ' \nfixture summary\t '}).encode()
        _, _, checks, _, _, process = self.outcome(path, output=raw)
        self.assertEqual((self.state(path)['status'], self.state(path)['execution_started']), ('succeeded', True))
        self.assertEqual((path / 'result.json').read_bytes(), raw)
        self.assertEqual(checks.call_count, 2)
        process.assert_called_once()

    def test_post_task_auth_failure_stays_failed_even_with_result_saved(self):
        path = self.queue()
        with patch.object(agent, 'aws_identity', return_value='ready'), \
                patch.object(agent, 'runtime_auth', side_effect=[{'auth_state': 'valid'}, {'auth_state': 'invalidated'}]), \
                patch.object(agent, 'task_command', return_value=['synthetic-task']), \
                patch.object(agent, 'run_process', return_value=(0, b'{"result":"already executed"}', b'')):
            agent.process_job(path)
        self.assertEqual((self.state(path)['status'], self.state(path)['execution_started']), ('failed', True))
        self.assertTrue((path / 'result.json').exists())
        with self.assertRaises(agent.Stopped):
            agent.resume(path.name)

    def test_auth_only_job_never_starts_task(self):
        path = self.queue(kind='auth')
        _, login, _, support, command, child = self.outcome(path)
        self.assertEqual((self.state(path)['status'], self.state(path)['execution_started']), ('succeeded', False))
        login.assert_not_called(); support.assert_not_called()
        command.assert_not_called(); child.assert_not_called()
        self.assertFalse((path / 'task.json').exists())

    def test_aws_identity_uses_only_selected_profile_and_checks_exact_role(self):
        for tier in self.runner.ROLES:
            with self.subTest(tier=tier), patch.object(agent, 'run_process', return_value=(0, b'{"Account":"fixture"}', b'')) as child:
                self.assertEqual(agent.aws_identity(self.runner, tier), 'ready')
                args = child.call_args.args[0]
                self.assertEqual(args[args.index('--profile') + 1], self.runner.PROFILES[tier])
                self.assertNotIn('default', args)
                self.runner.executor_module().check_identity.assert_called_with({'Account': 'fixture'}, self.runner.ROLES[tier])
        self.runner.executor_module().check_identity.side_effect = RuntimeError('wrong role')
        with patch.object(agent, 'run_process', return_value=(0, b'{"Account":"wrong"}', b'')), self.assertRaisesRegex(agent.Stopped, '^aws_identity_mismatch$'):
            agent.aws_identity(self.runner, 'inventory')

    def test_private_file_and_lock_guards_reject_symlink_hardlink_mode_and_wrong_owner(self):
        self.file(self.base / 'safe', b'fixture')
        (self.base / 'symlink').symlink_to(self.base / 'safe')
        with self.assertRaises(agent.Stopped):
            agent.owned(self.base / 'symlink')
        os.link(self.base / 'safe', self.base / 'hardlink')
        with self.assertRaisesRegex(agent.Stopped, '^unsafe_file$'):
            agent.owned(self.base / 'safe')
        (self.base / 'hardlink').unlink()
        (self.base / 'safe').chmod(0o644)
        with self.assertRaisesRegex(agent.Stopped, '^unsafe_file$'):
            agent.owned(self.base / 'safe')
        (self.base / 'safe').chmod(0o600)
        with patch.object(agent, 'UID', os.getuid() + 12345), self.assertRaisesRegex(agent.Stopped, '^unsafe_file$'):
            agent.owned(self.base / 'safe')
        self.file(self.root / 'session.lock', b'')
        (self.root / 'session.lock').chmod(0o644)
        with self.assertRaisesRegex(agent.Stopped, '^unsafe_lock$'):
            with agent.locked('session.lock'):
                self.fail('unsafe lock acquired')

    def test_active_session_lock_prevents_second_worker_and_terminal_launch(self):
        with agent.locked('session.lock'):
            self.assertTrue(agent.active_session())
            self.assertEqual(START_SESSION(), {'status': 'session_active'})
            with self.assertRaisesRegex(agent.Stopped, '^session_busy$'):
                with agent.locked('session.lock'):
                    self.fail('second worker acquired the lock')
        self.assertFalse(agent.active_session())

    def test_simultaneous_start_requests_open_only_one_terminal(self):
        with patch.object(agent.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0)) as open_terminal:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: START_SESSION(), range(2)))
        # A concurrent active_session() probe can briefly hold session.lock.
        # The other caller may observe that conservative busy result before
        # launch.lock/launch.json coalesces it as terminal_opening.
        statuses = [value['status'] for value in results]
        self.assertEqual(len(statuses), 2)
        self.assertEqual(statuses.count('terminal_opened'), 1)
        self.assertTrue(set(statuses) <= {'terminal_opened', 'terminal_opening', 'session_active'})
        open_terminal.assert_called_once()
        self.assertEqual(open_terminal.call_args.args[0][:3], ['/usr/bin/open', '-a', 'Terminal'])
        script = self.root / 'KINGDOM AWS Session.command'
        self.assertEqual(stat.S_IMODE(script.stat().st_mode), 0o700)
        self.assertIn(agent.digest((self.source / 'mac-agent.py').read_bytes()), script.read_text())

    def test_worker_loaded_source_and_runtime_helper_changes_fail_closed(self):
        path = self.queue()
        with patch.object(agent, 'LOADED_SHA', '0' * 64), self.assertRaisesRegex(agent.Stopped, '^worker_source_changed_restart_session$'):
            agent.validate_request(path, self.runner)
        with patch.object(agent, 'run_process') as process:
            for pin in (None, '0' * 64):
                with self.subTest(pin=pin), self.assertRaisesRegex(agent.Stopped, '^runtime_auth_source_changed$'):
                    agent.runtime_auth(self.runner, expected_sha=pin)
            process.assert_not_called()

    def test_captured_task_command_rechecks_actual_inputs_before_starting(self):
        # A harmless runner fixture exercises the generated wrapper in a real
        # Python child, including a file change after the command was composed.
        source = b'''import argparse, hashlib, json
from pathlib import Path
def require(ok, reason):
 if not ok: raise RuntimeError(reason)
def validate_inputs(task, archive, tier):
 raw, data = Path(task).read_bytes(), Path(archive).read_bytes()
 return {}, None, {'task_sha256':hashlib.sha256(raw).hexdigest(),
  'archive_sha256':hashlib.sha256(data).hexdigest(),
  'task_bytes':len(raw),'archive_bytes':len(data)}
def main():
 p=argparse.ArgumentParser()
 for name in ('task','archive','tier'):p.add_argument('--'+name)
 p.add_argument('--run',action='store_true')
 args=p.parse_args()
 validate_inputs(args.task,args.archive,args.tier)
 print(json.dumps({'result':'synthetic task started'}))
 return 0
'''
        self.file(self.source / 'run-task.py', source)
        path = self.queue()
        request = agent.validate_request(path, self.runner)
        with patch.object(agent, 'RUNNER_SHA', agent.digest(source)), patch.object(agent, 'PYTHON', sys.executable):
            command = agent.task_command(path, request)
        with patch.object(agent.subprocess, 'Popen', REAL_POPEN):
            first = REAL_RUN(command, capture_output=True, timeout=5, check=False)
            self.assertEqual(first.returncode, 0)
            self.assertEqual(json.loads(first.stdout), {'result': 'synthetic task started'})
            self.file(path / 'input.tar', b'changed between validation and execution')
            second = REAL_RUN(command, capture_output=True, timeout=5, check=False)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(second.stdout, b'')
        self.assertIn(b'queued_inputs_changed', second.stderr)

    def test_fixture_child_output_is_bounded_and_cleanup_reaps_child(self):
        command = [sys.executable, '-I', '-S', '-B', '-c', 'import sys; print("fixture"); print("diagnostic", file=sys.stderr)']
        with patch.object(agent.subprocess, 'Popen', REAL_POPEN), patch.object(agent, 'keep_ticket'):
            code, output, errors = agent.run_process(command, 5, 1024)
            self.assertEqual((code, output, errors), (0, b'fixture\n', b'diagnostic\n'))
            oversized = [*command[:-1], 'import os; os.write(1,b"x"*2048)']
            with self.assertRaisesRegex(agent.Stopped, '^child_output_limit$'):
                agent.run_process(oversized, 5, 128)
            self.assertIsNone(agent.CHILD)

    def test_session_deadline_stops_fixture_child_without_leaving_it_running(self):
        children = []

        def spawn(*args, **kwargs):
            child = REAL_POPEN(*args, **kwargs)
            children.append(child)
            return child

        command = [sys.executable, '-I', '-S', '-B', '-c', 'import time; time.sleep(10)']
        with patch.object(agent.subprocess, 'Popen', side_effect=spawn), patch.object(agent, 'keep_ticket'), \
                patch.object(agent, 'SESSION_END', time.monotonic() + 0.1):
            with self.assertRaisesRegex(agent.Stopped, '^child_deadline$'):
                agent.run_process(command, 10)
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())
        self.assertIsNone(agent.CHILD)

    def test_login_codes_go_only_to_mock_terminal_and_are_not_returned(self):
        terminal = io.StringIO()
        fake_open = Mock()
        fake_open.return_value.__enter__ = Mock(return_value=terminal)
        fake_open.return_value.__exit__ = Mock(return_value=False)
        command = [sys.executable, '-I', '-S', '-B', '-c',
                   'print("unrecognized-provider-output"); print("One-time device code: ABCD-EFGH")']
        with patch.object(agent.subprocess, 'Popen', REAL_POPEN), patch.object(agent, 'keep_ticket'), \
                patch('builtins.open', fake_open), patch.object(agent.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0)) as browser:
            self.assertEqual(agent.run_process(command, 5, 1024, login=True), (0, b'', b''))
        fake_open.assert_called_once_with('/dev/tty', 'w')
        self.assertEqual(terminal.getvalue(), agent.DEVICE_URL + '\nOne-time device code: ABCD-EFGH\n')
        browser.assert_called_once()
        self.assertEqual(browser.call_args.args[0], ['/usr/bin/open', agent.DEVICE_URL])
        self.assertNotIn('ABCD-EFGH', self.stdout.getvalue())


if __name__ == '__main__':
    unittest.main()
