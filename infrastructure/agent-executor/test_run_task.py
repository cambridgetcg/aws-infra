"""Offline routine-runner tests with synthetic inputs and mocked child processes."""
from contextlib import ExitStack
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import tarfile
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

PATH = Path(__file__).with_name('run-task.py')
SPEC = importlib.util.spec_from_file_location('routine_runner', PATH)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
EXSPEC = importlib.util.spec_from_file_location('fixture_executor', PATH.with_name('executor.py'))
ex = importlib.util.module_from_spec(EXSPEC)
EXSPEC.loader.exec_module(ex)


def archive_bytes(name='README.md', data=b'Reviewed synthetic input\n', link=False):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:') as archive:
        member = tarfile.TarInfo(name)
        if link:
            member.type = tarfile.SYMTYPE
            member.linkname = 'README.md'
            archive.addfile(member)
        else:
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return output.getvalue()


class RoutineTaskTests(unittest.TestCase):
    def setUp(self):
        runner.CHILDREN.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.task = {'task_id': 'review-vpcs', 'model': 'gpt-5.6-luna', 'prompt': 'Count VPCs; metadata only.'}
        self.task_raw = json.dumps(self.task).encode()
        self.archive = archive_bytes()
        self.task_path = self.root / 'task.json'
        self.archive_path = self.root / 'input.tar'
        self.task_path.write_bytes(self.task_raw)
        self.archive_path.write_bytes(self.archive)
        self.task_path.chmod(0o600); self.archive_path.chmod(0o600)

    def validation(self, tier='inventory'):
        with patch.object(runner.os, 'getuid', return_value=501), \
                patch.object(runner.os, 'geteuid', return_value=501):
            return runner.validate_inputs(self.task_path, self.archive_path, tier)

    def test_offline_validation_reads_only_source_and_explicit_inputs(self):
        read_paths, output = [], io.StringIO()
        original = runner.owned_bytes

        def read(path, *args, **kwargs):
            read_paths.append(str(path))
            return original(path, *args, **kwargs)

        with patch.object(runner, 'owned_bytes', side_effect=read), patch('sys.stdout', output), \
                patch.object(runner.signal, 'signal'), \
                patch.object(runner.subprocess, 'Popen', side_effect=AssertionError('unexpected process')):
            result = runner.main(['--task', str(self.task_path), '--archive', str(self.archive_path)])
        self.assertEqual(result, 0)
        value = json.loads(output.getvalue())
        self.assertEqual((value['mode'], value['tier'], value['profile']),
                         ('offline_validated', 'inventory', 'cambridge-agent-inventory'))
        self.assertEqual(set(read_paths), {runner.SOURCE, str(self.task_path), str(self.archive_path)})
        self.assertNotIn(self.task['prompt'], output.getvalue())

    def test_exact_schema_and_forbidden_archive_paths_rejected(self):
        self.task_path.write_text(json.dumps(dict(self.task, command='unexpected')))
        with self.assertRaisesRegex(RuntimeError, 'unexpected_task_schema'):
            self.validation()
        self.task_path.write_bytes(self.task_raw)
        for name, link in (('../escape', False), ('.aws/config', False), ('linked', True)):
            with self.subTest(name=name):
                self.archive_path.write_bytes(archive_bytes(name=name, link=link))
                with self.assertRaisesRegex(Exception, 'Archive'):
                    self.validation()

    def test_input_symlink_shared_write_hardlink_and_oversize_rejected(self):
        link = self.root / 'alias.tar'
        link.symlink_to(self.archive_path)
        with self.assertRaisesRegex(RuntimeError, 'noncanonical_input_path'):
            runner.owned_bytes(link, os.getuid(), runner.MAX_ARCHIVE)
        self.archive_path.chmod(0o620)
        with self.assertRaisesRegex(RuntimeError, 'unsafe_input_file'):
            runner.owned_bytes(self.archive_path, os.getuid(), runner.MAX_ARCHIVE)
        self.archive_path.chmod(0o600)
        hard = self.root / 'hard.tar'
        os.link(self.archive_path, hard)
        with self.assertRaisesRegex(RuntimeError, 'unsafe_input_file'):
            runner.owned_bytes(self.archive_path, os.getuid(), runner.MAX_ARCHIVE)
        hard.unlink()
        with self.assertRaisesRegex(RuntimeError, 'input_too_large'):
            runner.owned_bytes(self.archive_path, os.getuid(), 4)

    def staging(self, metadata=None):
        namespace = {'checked': lambda value: runner.require(value, 'invalid frame'),
                     'INPUT': metadata or {'task_sha256': hashlib.sha256(self.task_raw).hexdigest(),
                                          'archive_sha256': hashlib.sha256(self.archive).hexdigest()},
                     'TASK_ID': self.task['task_id'], 'hashlib': hashlib, 'json': json,
                     'os': os, 'stat': __import__('stat')}
        exec(runner.STAGING, namespace)
        return namespace

    def test_exact_frame_reads_leave_credential_bytes_unread(self):
        namespace = self.staging()
        frame = struct.pack('!IQ', len(self.task_raw), len(self.archive)) + self.task_raw + self.archive
        stream = io.BytesIO(frame + b'SYNTHETIC-NONSECRET-HANDOFF')
        namespace['os'] = types.SimpleNamespace(read=lambda fd, size: stream.read(min(17, size)))
        self.assertEqual(namespace['receive_inputs'](ex), (self.task_raw, self.archive))
        self.assertEqual(stream.read(), b'SYNTHETIC-NONSECRET-HANDOFF')

    def test_frame_rejects_size_truncation_and_digest_mismatch(self):
        valid = struct.pack('!IQ', len(self.task_raw), len(self.archive)) + self.task_raw + self.archive
        for frame in (struct.pack('!IQ', 65537, len(self.archive)), valid[:-1],
                      valid[:12] + b'x' + valid[13:]):
            with self.subTest(size=len(frame)):
                namespace = self.staging()
                stream = io.BytesIO(frame)
                namespace['os'] = types.SimpleNamespace(read=lambda fd, size: stream.read(size))
                with self.assertRaises(RuntimeError):
                    namespace['receive_inputs'](ex)

    def test_staging_files_private_exclusive_and_owned_cleanup(self):
        namespace = self.staging()
        stage = self.root / 'submitted-example'
        stage.mkdir(mode=0o700)
        descriptor = os.open(stage, os.O_RDONLY | os.O_DIRECTORY)
        info = os.fstat(descriptor)
        files = {}
        namespace['stage_file'](descriptor, 'task.json', self.task_raw, files)
        self.assertEqual((stage / 'task.json').stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            namespace['stage_file'](descriptor, 'task.json', b'overwrite', files)
        self.assertEqual((stage / 'task.json').read_bytes(), self.task_raw)
        namespace['remove_staging'](str(stage), descriptor, (info.st_dev, info.st_ino), files)
        self.assertFalse(stage.exists())

    def test_cleanup_refuses_a_replaced_inode(self):
        namespace = self.staging()
        stage = self.root / 'submitted-example'
        stage.mkdir(mode=0o700)
        descriptor = os.open(stage, os.O_RDONLY | os.O_DIRECTORY)
        info = os.fstat(descriptor)
        files = {}
        namespace['stage_file'](descriptor, 'task.json', self.task_raw, files)
        original = stage / 'task.json'
        replacement = self.root / 'replacement'
        replacement.write_text('not owned by this submission')
        os.replace(replacement, original)
        with self.assertRaises(RuntimeError):
            namespace['remove_staging'](str(stage), descriptor, (info.st_dev, info.st_ino), files)
        self.assertEqual(original.read_text(), 'not owned by this submission')

    def fixture(self, tier='inventory', bad_ready=False, issuer_code=0, result_tier=None, early_ready=False):
        # Larger than a pipe capacity: the parent must multiplex partial writes
        # with the target reader instead of blocking before its deadline loop.
        archive = archive_bytes(data=b'x' * 262144)
        frame = struct.pack('!IQ', len(self.task_raw), len(archive)) + self.task_raw + archive
        metadata = {'task_sha256': hashlib.sha256(self.task_raw).hexdigest(),
                    'archive_sha256': hashlib.sha256(archive).hexdigest()}
        manifest = self.root / 'manifest.json'
        manifest.write_text(json.dumps({'account_id': '034362054546', 'region': 'us-east-1', 'roles': runner.ROLES}))
        manifest.chmod(0o600)
        calls, descriptors, threads, errors = [], set(), [], []
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
            os.close(fd); descriptors.discard(fd)

        def read_task_frame():
            try:
                received = bytearray()
                while len(received) < len(frame):
                    block = os.read(state['input'], min(4096, len(frame) - len(received)))
                    if not block:
                        break
                    received.extend(block)
                if bytes(received) != frame:
                    raise AssertionError('Task frame changed or truncated')
                state['frame_done'] = True
                os.write(state['output'], b'INVALID READY\n' if bad_ready else runner.READY)
                if bad_ready:
                    close(state['input']); close(state['output'])
            except BaseException as error:
                errors.append(error)

        def fake_popen(argv, **kwargs):
            calls.append((argv, kwargs))
            if len(calls) == 1:
                self.assertEqual(kwargs.get('process_group'), 0)
                self.assertNotIn('start_new_session', kwargs)
                self.assertEqual(argv[:5], ['/usr/bin/sudo', '-n', '-u', 'aws-agent', '-H'])
                self.assertNotIn(self.task['prompt'], argv[-1])
                state['input'] = os.dup(kwargs['stdin'])
                reader, state['output'] = os.pipe()
                descriptors.update((state['input'], state['output']))
                child = Child()
                child.stdout = os.fdopen(reader, 'rb')
                if early_ready:
                    os.write(state['output'], runner.READY)
                else:
                    thread = threading.Thread(target=read_task_frame, daemon=True)
                    threads.append(thread); thread.start()
                return child
            self.assertTrue(state.get('frame_done'))
            self.assertTrue(kwargs.get('start_new_session'))
            self.assertEqual(len(kwargs['pass_fds']), 1)
            handoff = kwargs['pass_fds'][0]
            self.assertEqual(str(handoff), argv[-1])
            self.assertGreaterEqual(handoff, 3)
            self.assertTrue(os.get_blocking(handoff))
            self.assertFalse(any(key.startswith('AWS_') for key in kwargs['env']))
            self.assertIn("TIER='" + tier + "'", argv[-2])
            os.write(handoff, b'SYNTHETIC-NONSECRET')
            self.assertEqual(os.read(state['input'], 64), b'SYNTHETIC-NONSECRET')
            close(state['input'])
            if issuer_code == 0:
                role = runner.ROLES[result_tier or tier]
                value = {'task_id': self.task['task_id'], 'account_id': '034362054546',
                         'principal_id': role['role_id'] + ':fixture',
                         'principal_arn': 'arn:aws:sts::034362054546:assumed-role/'
                         + role['role_arn'].rsplit('/', 1)[1] + '/fixture',
                         'expires_at': '2026-09-18T22:00:00Z', 'result': 'Synthetic metadata\u001b'}
                os.write(state['output'], json.dumps(value).encode())
            close(state['output'])
            return Child(issuer_code)

        def fake_open(path, *args, **kwargs):
            return original_open(os.devnull, os.O_RDONLY) if str(path) == '/dev/tty' else original_open(path, *args, **kwargs)

        def finish():
            for thread in threads:
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())
            for descriptor in tuple(descriptors):
                os.close(descriptor)
            self.assertEqual(errors, [])

        stack = ExitStack()
        for context in (
            patch.object(runner, 'OPERATOR_MANIFEST', str(manifest)),
            patch.object(runner.os, 'getuid', return_value=501),
            patch.object(runner.os, 'geteuid', return_value=501),
            patch.object(runner.os, 'open', side_effect=fake_open),
            patch.object(runner.os, 'isatty', return_value=True),
            patch.dict(os.environ, {'HOME': runner.HUMAN_HOME}, clear=True),
            patch.object(runner.subprocess, 'Popen', side_effect=fake_popen),
        ):
            stack.enter_context(context)
        self.addCleanup(stack.close)
        self.addCleanup(finish)
        return calls, frame, metadata

    def assert_pipeline(self, tier):
        calls, frame, metadata = self.fixture(tier=tier)
        output = runner.live_task(self.task, frame, metadata, tier)
        self.assertEqual(len(calls), 2)
        self.assertNotIn('\x1b', output)
        self.assertTrue(json.loads(output)['principal_id'].startswith(runner.ROLES[tier]['role_id']))

    def test_large_frame_then_ready_gates_inventory_issuer(self):
        self.assert_pipeline('inventory')

    def test_explicit_audit_tier_uses_only_audit_identity(self):
        self.assert_pipeline('iam-audit')

    def test_invalid_and_early_ready_never_issue_credentials(self):
        calls, frame, metadata = self.fixture(bad_ready=True)
        with self.assertRaisesRegex(RuntimeError, 'unexpected_runtime_preflight_output'):
            runner.live_task(self.task, frame, metadata, 'inventory')
        self.assertEqual(len(calls), 1)

    def test_premature_ready_never_issues_credentials(self):
        calls, frame, metadata = self.fixture(early_ready=True)
        with self.assertRaisesRegex(RuntimeError, 'ready_before_inputs_transferred'):
            runner.live_task(self.task, frame, metadata, 'inventory')
        self.assertEqual(len(calls), 1)

    def test_issuer_failure_and_wrong_result_tier_are_rejected(self):
        calls, frame, metadata = self.fixture(issuer_code=1)
        with self.assertRaises(RuntimeError):
            runner.live_task(self.task, frame, metadata, 'inventory')
        self.assertEqual(len(calls), 2)

    def test_wrong_result_tier_is_rejected(self):
        _, frame, metadata = self.fixture(result_tier='iam-audit')
        with self.assertRaisesRegex(RuntimeError, 'result_identity_mismatch'):
            runner.live_task(self.task, frame, metadata, 'inventory')

    def test_conflicting_profile_rejected_before_any_child(self):
        calls, frame, metadata = self.fixture()
        with patch.dict(os.environ, {'AWS_PROFILE': 'default'}):
            with self.assertRaisesRegex(RuntimeError, 'wrong_aws_profile'):
                runner.live_task(self.task, frame, metadata, 'inventory')
        self.assertEqual(calls, [])

    def proof_fixture(self):
        namespace = {'checked': lambda value: runner.require(value, 'invalid receipt'),
                     'hashlib': hashlib, 'json': json, 'os': os}
        exec(runner.PROOFS, namespace)
        manifest = {'image': 'sha256:executor', 'proxy_identity': {'container_id': 'proxy',
                    'image_id': 'sha256:proxy', 'config_sha256': 'policy-fingerprint'}}
        raw = json.dumps(manifest).encode()
        report = {'schema_version': 1, 'activation_ready': False, 'network_checks_status': 'passed',
                  'scope': 'credential-free-network-paths', 'proxy_ipv4': '172.30.240.2',
                  'finished_at': '2026-01-01T00:00:00Z', 'checks': [{'status': 'passed'} for _ in range(28)],
                  'launcher_evidence': {'image': manifest['image'], 'network_id': 'internal-network',
                                       'proxy_container_id': 'proxy', 'proxy_config_sha256': 'policy-fingerprint'}}
        dns = {'schema': 1, 'success': True, 'activation_ready': False, 'finished_at': report['finished_at'],
               'evidence': {'engine_id': 'engine', 'manifest_sha256': hashlib.sha256(raw).hexdigest(),
                            'network_id': 'internal-network', 'outbound_id': 'outbound-network',
                            'image_id': manifest['image'], 'proxy_id': 'proxy', 'proxy_image_id': 'sha256:proxy',
                            'proxy_ipv4': '172.30.240.2', 'proxy_config_sha256': 'policy-fingerprint',
                            'resolver': '1.1.1.1', 'dns_passed': True, 'deadline_cleanup': {'passed': True}}}
        args = [manifest, raw, 'internal-network', '172.30.240.2', 'engine',
                {'Id': 'outbound-network', 'Containers': {'proxy': {}}}, [report], dns]
        return namespace['receipt_proofs'], args

    def test_matching_old_proofs_are_reusable_but_newer_failure_blocks(self):
        verify, args = self.proof_fixture()
        verify(*args)  # Routine usage has identity matching, not a 30-minute expiry.
        failed = copy.deepcopy(args[-2][0])
        failed.update(network_checks_status='failed', finished_at='2026-01-01T00:01:00Z')
        args[-2].append(failed)
        with self.assertRaises(RuntimeError):
            verify(*args)

    def test_changed_image_manifest_engine_and_extra_outbound_peer_block(self):
        for kind in ('image', 'manifest', 'engine', 'peer', 'dns', 'future', 'missing'):
            with self.subTest(kind=kind):
                verify, args = self.proof_fixture()
                if kind == 'image':
                    args[0]['image'] = 'sha256:changed'
                elif kind == 'manifest':
                    args[1] += b' '
                elif kind == 'engine':
                    args[4] = 'changed-engine'
                elif kind == 'peer':
                    args[5]['Containers']['unexpected'] = {}
                elif kind == 'dns':
                    args[-1]['evidence']['dns_passed'] = False
                elif kind == 'future':
                    args[-2][0]['finished_at'] = '2999-01-01T00:00:00Z'
                else:
                    args[-2].clear()
                with self.assertRaises(RuntimeError):
                    verify(*args)


if __name__ == '__main__':
    unittest.main()
