#!/usr/bin/env python3
"""Runtime-only subscription state and exact invalidation-marker recovery.

The human coordinator composes verified copies of this source and run-task's
COMMON/PROOFS. The resulting source runs under UID 502; authentication bytes
never cross that boundary. This helper neither logs in nor dispatches a task.
"""
import argparse
import ast
import fcntl
import json
import os
from pathlib import Path
import secrets
import signal
import stat
import sys

EXECUTOR_PIN = 'c75abdcc3b02e403850ad7d88f56fab6c0d2cf6c5ef3e115532fd1fcd18e537b'
IMAGE_PIN = 'sha256:3e16293cbcf1e3e27f509303f843738901b1fe616e73a986c97390fe991aecb8'
INVALIDATED = json.dumps({'auth_mode': 'chatgpt', 'OPENAI_API_KEY': None,
                          'tokens': None, 'last_refresh': None}).encode()
ERRORS = frozenset({'runtime_boundary_failed', 'runtime_not_quiescent',
                    'authentication_in_use', 'unsafe_authentication_path',
                    'unsafe_authentication_file', 'authentication_changed',
                    'authentication_schema_invalid', 'valid_authentication_preserved',
                    'authentication_recovery_failed', 'runtime_check_interrupted'})


class Rejected(Exception):
    pass


def require(value, code):
    if not value:
        raise Rejected(code)


def compose(runner, helper_source):
    """Use exact already-reviewed bytes, not a later file read or runtime import.

    Caller must verify both source pins before importing/composing these modules.
    Invoke the returned program with --action status or --action prepare-login.
    """
    require(isinstance(helper_source, bytes) and len(helper_source) <= 32768,
            'runtime_boundary_failed')
    expected = {
        'SOURCE_SHA': EXECUTOR_PIN,
        'RUNTIME_SOURCE': '/Users/aws-agent/agent-runtime/bundle/executor.py',
        'RUNTIME_MANIFEST': '/Users/aws-agent/agent-runtime/tasks/manifest.json',
        'MODEL_AUTH': '/Users/aws-agent/agent-runtime/model-auth/auth.json',
        'TASKS': '/Users/aws-agent/agent-runtime/tasks',
    }
    require(all(getattr(runner, key, None) == value for key, value in expected.items()),
            'runtime_boundary_failed')
    constants = dict(expected, ROLES=runner.ROLES, PROFILES=runner.PROFILES,
                     RUNTIME_AUTH_COMPOSED=True)
    source = '\n'.join(key + '=' + repr(value) for key, value in constants.items()) + '\n'
    source += runner.COMMON + runner.PROOFS + '\n' + helper_source.decode('utf-8')
    ast.parse(source)
    return source


def private_directory_info(info):
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o700,
            'unsafe_authentication_path')


def private_directory(path):
    require(path.resolve() == path, 'unsafe_authentication_path')
    private_directory_info(path.lstat())


def private_file(info):
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600,
            'unsafe_authentication_file')


def fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_size,
            info.st_uid, info.st_mode, info.st_nlink)


def unique_json(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'authentication_schema_invalid')
        value[key] = item
    return value


def authentication_state(ex, path, action, quiescent):
    """Serialize with executor/login and return only a state, never cache data."""
    require(action in ('status', 'prepare-login'), 'runtime_boundary_failed')
    path = Path(path)
    require(path.is_absolute() and path.name == 'auth.json', 'unsafe_authentication_path')
    private_directory(path.parent)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    lock = None
    try:
        directory_info = os.fstat(directory)
        private_directory_info(directory_info)
        require(fingerprint(directory_info) == fingerprint(path.parent.lstat()),
                'unsafe_authentication_path')
        lock = os.open('.subscription-auth.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
                       | os.O_NONBLOCK, 0o600, dir_fd=directory)
        private_file(os.fstat(lock))
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Rejected('authentication_in_use') from None
        quiescent()
        try:
            descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 dir_fd=directory)
        except FileNotFoundError:
            return {'auth_state': 'missing', 'prepared': action == 'prepare-login'}
        with os.fdopen(descriptor, 'rb') as stream:
            original = os.fstat(stream.fileno())
            private_file(original)
            raw = stream.read(ex.MAX_MODEL_AUTH + 1)
            require(fingerprint(os.fstat(stream.fileno())) == fingerprint(original),
                    'authentication_changed')
        require(len(raw) <= ex.MAX_MODEL_AUTH, 'authentication_schema_invalid')
        current = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
        require(fingerprint(current) == fingerprint(original), 'authentication_changed')
        if raw != INVALIDATED:
            try:
                value = json.loads(raw, object_pairs_hook=unique_json)
                ex.validate_model_auth(value)
            except Exception:
                raise Rejected('authentication_schema_invalid') from None
            require(action == 'status', 'valid_authentication_preserved')
            return {'auth_state': 'valid', 'prepared': False}
        if action == 'status':
            return {'auth_state': 'invalidated', 'prepared': False}
        # A newly created private directory makes the destination exclusive;
        # no existing authentication file or quarantine record is overwritten.
        quarantine_name = '.invalidated-auth-' + secrets.token_hex(16)
        os.mkdir(quarantine_name, mode=0o700, dir_fd=directory)
        quarantine = os.open(quarantine_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                             dir_fd=directory)
        try:
            private_directory_info(os.fstat(quarantine))
            current = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
            require(fingerprint(current) == fingerprint(original), 'authentication_changed')
            os.rename(path.name, 'auth.json', src_dir_fd=directory, dst_dir_fd=quarantine)
            require(fingerprint(os.stat('auth.json', dir_fd=quarantine, follow_symlinks=False))
                    == fingerprint(original), 'authentication_changed')
            os.fsync(quarantine)
            os.fsync(directory)
        finally:
            os.close(quarantine)
        return {'auth_state': 'invalidated', 'prepared': True}
    finally:
        if lock is not None:
            os.close(lock)
        os.close(directory)


def runtime_preflight():
    require(globals().get('RUNTIME_AUTH_COMPOSED') is True,
            'runtime_boundary_failed')
    require(os.getuid() == os.geteuid() == 502 and os.getgid() == 20
            and 80 not in os.getgroups() and os.environ.get('HOME') == '/Users/aws-agent'
            and not os.access('/Users/yournameisai', os.X_OK), 'runtime_boundary_failed')
    require(not any(key.startswith(('AWS_', 'OPENAI_', 'CODEX_', 'SSH_', 'DOCKER_'))
                    for key in os.environ), 'runtime_boundary_failed')
    for path in ('/Users/aws-agent', '/Users/aws-agent/agent-runtime',
                 '/Users/aws-agent/agent-runtime/bundle', TASKS, str(Path(MODEL_AUTH).parent)):
        private_directory(Path(path))
    ex = module(RUNTIME_SOURCE, 502)
    require(SOURCE_SHA == EXECUTOR_PIN, 'runtime_boundary_failed')
    raw = file_bytes(RUNTIME_MANIFEST, 502, 65536)
    manifest = json.loads(raw)
    require(manifest.get('image') == IMAGE_PIN and manifest.get('roles') == ROLES,
            'runtime_boundary_failed')
    for tier, role in ROLES.items():
        require(ex.validate_manifest(manifest, tier) == role, 'runtime_boundary_failed')
    env = ex.base_environment()
    env['HOME'] = '/Users/aws-agent'
    call = lambda args: ex.bounded_command(['docker', *args], env, timeout=15, limit=65536)
    require(call(['context', 'show']).strip() == b'colima-aws-agent', 'runtime_boundary_failed')
    network, proxy = ex.inspect_network(manifest, env)
    check_receipts(ex, manifest, raw, network, proxy, env)
    metadata = json.loads(call(['image', 'inspect', IMAGE_PIN, '--format',
                               '{"id":{{json .Id}},"os":{{json .Os}},"arch":{{json .Architecture}},'
                               '"user":{{json .Config.User}},"entrypoint":{{json .Config.Entrypoint}},'
                               '"volumes":{{json .Config.Volumes}}}']))
    require(metadata == {'id': IMAGE_PIN, 'os': 'linux', 'arch': 'arm64',
                         'user': '10001:10001', 'entrypoint': ['/usr/local/bin/python3',
                         '-I', '-B', '/opt/executor.py', 'entry'], 'volumes': None},
            'runtime_boundary_failed')

    def quiescent():
        with os.scandir(TASKS) as entries:
            for count, entry in enumerate(entries, 1):
                require(count <= 256 and not entry.name.startswith('submitted-'),
                        'runtime_not_quiescent')
        ids = call(['container', 'ls', '--all', '--no-trunc', '--format', '{{.ID}}']).splitlines()
        require(ids == [manifest['proxy_identity']['container_id'].encode()],
                'runtime_not_quiescent')

    return ex, quiescent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--action', choices=('status', 'prepare-login'), required=True)
    args = parser.parse_args(argv)
    os.umask(0o077)

    def interrupted(number, frame):
        raise Rejected('runtime_check_interrupted')

    for number in (signal.SIGALRM, signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(number, interrupted)
    signal.setitimer(signal.ITIMER_REAL, 75)
    try:
        ex, quiescent = runtime_preflight()
        state = authentication_state(ex, MODEL_AUTH, args.action, quiescent)
        print(json.dumps(dict(schema=1, action=args.action, runtime_ready=True, **state), sort_keys=True))
        return 0
    except BaseException as error:
        code = str(error) if isinstance(error, Rejected) and str(error) in ERRORS else 'runtime_boundary_failed'
        print(json.dumps({'schema': 1, 'action': args.action, 'error': code}, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


if __name__ == '__main__':
    sys.exit(main())
