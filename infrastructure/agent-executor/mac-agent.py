#!/usr/bin/env python3
"""Local task queue and guided authentication for the verified Mac AWS runtime.

No daemon, password storage, arbitrary command dispatch or credential export.
The human Terminal owns OS/browser prompts; agents see only bounded receipts.
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shlex
import signal
import stat
import struct
import subprocess
import sys
import time
import types
import uuid

HERE = Path(__file__).resolve().parent
ROOT = Path('/Users/yournameisai/.aws/agent-runtime/automation')
PYTHON = '/opt/homebrew/bin/python3.13'
HUMAN = '/Users/yournameisai'
UID = 501
RUNNER_SHA = '3264e9087a41157c35c8ac9c05937641500ad26854178018e1da7e63bc5999c1'
SUPPORT = {
    'refresh-proofs': ('bd385fb96e4cf43413aa10a36de856c2a9f6d4e22bc4d76636e336cc3ea054f3', 360),
    'login-subscription': ('50594c79e0f3da278a99ebe6224a99e5970c2ad5f134ee80a85e4e1cd138848d', 960),
}
SESSION_SECONDS = 2700
IDLE_SECONDS = 600
MAX_JOBS = 24
JOB_PATTERN = r'[0-9a-f]{32}'
DEVICE_URL = 'https://auth.openai.com/codex/device'
CHILD = None
LAST_TICKET = 0.0
SESSION_END = None
LOADED_SHA = globals().get('_loaded_source_sha') or hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class Stopped(Exception):
    """Only fixed, non-sensitive reason codes cross the agent interface."""


def require(value, reason):
    if not value:
        raise Stopped(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def human_env():
    return {'HOME': HUMAN, 'USER': 'yournameisai', 'LOGNAME': 'yournameisai',
            'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
            'LANG': 'C', 'AWS_EC2_METADATA_DISABLED': 'true', 'AWS_PAGER': ''}


def owned(path, limit=65536, private=True):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path, 'noncanonical_path')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == UID and info.st_nlink == 1
                and not info.st_mode & (0o077 if private else 0o022), 'unsafe_file')
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, 'file_limit')
    return raw


def directory(path, create=False):
    if create:
        path.mkdir(mode=0o700, exist_ok=True)
    info = path.lstat()
    require(path.resolve() == path and stat.S_ISDIR(info.st_mode) and info.st_uid == UID
            and stat.S_IMODE(info.st_mode) == 0o700, 'unsafe_directory')


def initialize():
    require(os.getuid() == os.geteuid() == UID and os.environ.get('HOME') == HUMAN,
            'expected_human_account')
    directory(ROOT.parent)
    directory(ROOT, create=True)
    for name in ('jobs', 'support'):
        directory(ROOT / name, create=True)


def write_new(path, raw):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as out:
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())
    sync_directory(path.parent)


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def save(path, value):
    temporary = path.parent / ('.write-' + uuid.uuid4().hex)
    write_new(temporary, (json.dumps(value, sort_keys=True) + '\n').encode())
    try:
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


@contextmanager
def locked(name, blocking=False):
    fd = os.open(ROOT / name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == UID and info.st_nlink == 1
                and stat.S_IMODE(info.st_mode) == 0o600, 'unsafe_lock')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            raise Stopped('session_busy') from None
        yield
    finally:
        os.close(fd)


def runner_module():
    path = HERE / 'run-task.py'
    raw = owned(path, 65536, False)
    require(digest(raw) == RUNNER_SHA, 'runner_source_changed')
    module = types.ModuleType('reviewed_runner')
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def source_pins():
    return {name: digest(owned(HERE / name, 131072, False))
            for name in ('mac-agent.py', 'runtime-auth.py', 'run-task.py', 'executor.py')}


def job_path(job):
    require(isinstance(job, str) and re.fullmatch(JOB_PATTERN, job), 'invalid_job_id')
    path = ROOT / 'jobs' / job
    directory(path)
    return path


def receipt(path, **changes):
    current = json.loads(owned(path / 'status.json'))
    current.update(changes, updated_at=time.time())
    save(path / 'status.json', current)
    return current


def submit(args):
    runner = runner_module()
    if args.command == 'auth':
        task, frame, metadata = None, None, None
    else:
        task, frame, metadata = runner.validate_inputs(args.task, args.archive, args.tier)
    if args.command == 'plan':
        return {'status': 'offline_validated', 'tier': args.tier, 'inputs': metadata,
                'task_id': task['task_id'], 'model': task['model'], 'authentication_started': False}
    job = uuid.uuid4().hex
    path = ROOT / 'jobs' / job
    path.mkdir(mode=0o700)
    sync_directory(path.parent)
    request = {'schema': 1, 'job': job, 'kind': 'auth' if task is None else 'task',
               'tier': args.tier, 'created_at': time.time(), 'pins': source_pins(), 'inputs': metadata}
    if frame is not None:
        task_size, archive_size = struct.unpack('!IQ', frame[:12])
        write_new(path / 'task.json', frame[12:12 + task_size])
        write_new(path / 'input.tar', frame[12 + task_size:])
        require(archive_size == len(frame) - 12 - task_size, 'unexpected_input_frame')
    write_new(path / 'request.json', json.dumps(request).encode())
    save(path / 'status.json', {'job': job, 'status': 'queued', 'execution_started': False,
                              'tier': args.tier, 'updated_at': time.time()})
    # Publish last: the worker never sees a partial submission.
    write_new(path / 'ready', b'1\n')
    start_session()
    return {'job': job, 'status': 'queued', 'next': 'kingdom-aws status ' + job}


def active_session():
    try:
        with locked('session.lock'):
            return False
    except Stopped as error:
        if str(error) == 'session_busy':
            return True
        raise


def start_session():
    if active_session():
        return {'status': 'session_active'}
    # Coalesce simultaneous launches before the Terminal has acquired its lock.
    with locked('launch.lock', blocking=True):
        if active_session():
            return {'status': 'session_active'}
        marker = ROOT / 'launch.json'
        if marker.exists():
            previous = json.loads(owned(marker))
            if 0 <= time.time() - previous.get('opened_at', 0) < 20:
                return {'status': 'terminal_opening'}
        script = HERE / 'mac-agent.py'
        pin = digest(owned(script, 131072, False))
        # Execute the verified bytes, rather than reopening a mutable source path.
        bootstrap = ("import hashlib,pathlib,sys; p=pathlib.Path(" + repr(str(script)) + "); "
                     "b=p.read_bytes(); assert hashlib.sha256(b).hexdigest()==" + repr(pin) + "; "
                     "sys.argv=[str(p),'_serve']; exec(compile(b,str(p),'exec'),"
                     "{'__name__':'__main__','__file__':str(p),'_loaded_source_sha':" + repr(pin) + "})")
        command = ['/usr/bin/env', '-i'] + [k + '=' + v for k, v in human_env().items()]
        command += [PYTHON, '-I', '-S', '-B', '-c', bootstrap]
        terminal = ROOT / 'KINGDOM AWS Session.command'
        contents = ('#!/bin/sh\numask 077\n' + shlex.join(command) + '\n').encode()
        temporary = ROOT / ('.terminal-' + uuid.uuid4().hex)
        write_new(temporary, contents)
        temporary.chmod(0o700)
        os.replace(temporary, terminal)
        result = subprocess.run(['/usr/bin/open', '-a', 'Terminal', str(terminal)],
                                env=human_env(), stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        require(result.returncode == 0, 'terminal_open_failed')
        save(marker, {'opened_at': time.time()})
    return {'status': 'terminal_opened', 'instruction': 'Complete only prompts shown in KINGDOM AWS Session.'}


def keep_ticket():
    global LAST_TICKET
    require(SESSION_END is None or time.monotonic() < SESSION_END, 'session_deadline')
    if time.monotonic() - LAST_TICKET >= 45:
        result = subprocess.run(['/usr/bin/sudo', '-n', '-v'], env=human_env(),
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=5)
        require(result.returncode == 0, 'mac_auth_expired')
        LAST_TICKET = time.monotonic()


def run_process(command, seconds, limit=524288, login=False):
    """Bound child output; device codes are sent only to the controlling Terminal."""
    global CHILD
    deadline = min(time.monotonic() + seconds, SESSION_END or float('inf'))
    output, errors, pending = bytearray(), bytearray(), b''
    CHILD = subprocess.Popen(command, cwd='/', env=human_env(), stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, process_group=0)
    try:
        with selectors.DefaultSelector() as selector:
            for stream in (CHILD.stdout, CHILD.stderr):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
            while selector.get_map():
                require(time.monotonic() < deadline, 'child_deadline')
                keep_ticket()
                for key, _ in selector.select(0.2):
                    data = os.read(key.fd, 16384)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    target = output if key.fileobj is CHILD.stdout else errors
                    target.extend(data)
                    require(len(target) <= limit, 'child_output_limit')
                    if login and key.fileobj is CHILD.stdout:
                        pending += data
                        require(len(pending) <= 32768, 'login_prompt_limit')
                        while b'\n' in pending:
                            line, pending = pending.split(b'\n', 1)
                            if re.fullmatch(rb'One-time device code: [A-Z0-9]{4}-[A-Z0-9]{4,8}', line):
                                with open('/dev/tty', 'w') as tty:
                                    tty.write(DEVICE_URL + '\n' + line.decode('ascii') + '\n')
                                subprocess.run(['/usr/bin/open', DEVICE_URL], env=human_env(),
                                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                               stderr=subprocess.DEVNULL, timeout=5)
            code = CHILD.wait(timeout=max(.1, deadline - time.monotonic()))
        return code, bytes(output) if not login else b'', bytes(errors) if not login else b''
    finally:
        if CHILD.poll() is None:
            try:
                os.killpg(CHILD.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                CHILD.wait(timeout=35)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(CHILD.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                CHILD.wait(timeout=5)
        CHILD.stdout.close()
        CHILD.stderr.close()
        CHILD = None


def runtime_command(source, arguments=()):
    env = {'HOME': '/Users/aws-agent', 'USER': 'aws-agent', 'LOGNAME': 'aws-agent',
           'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C'}
    return ['/usr/bin/sudo', '-n', '-u', 'aws-agent', '-H', '/usr/bin/env', '-i',
            *[key + '=' + value for key, value in env.items()], PYTHON, '-I', '-S', '-B',
            '-c', source, *arguments]


def runtime_auth(runner, action='status', expected_sha=None):
    body = owned(HERE / 'runtime-auth.py', 32768, False)
    require(expected_sha is not None and digest(body) == expected_sha, 'runtime_auth_source_changed')
    helper = types.ModuleType('runtime_auth_composer')
    exec(compile(body, str(HERE / 'runtime-auth.py'), 'exec'), helper.__dict__)
    source = helper.compose(runner, body)
    code, output, _ = run_process(runtime_command(source, ['--action', action]), 90, 65536)
    require(code == 0, 'runtime_auth_check_failed')
    value = json.loads(output)
    require(value.get('auth_state') in ('valid', 'missing', 'invalidated')
            and value.get('runtime_ready') is True, 'unexpected_runtime_auth_status')
    return value


def task_command(path, request):
    raw = owned(HERE / 'run-task.py', 65536, False)
    require(digest(raw) == request['pins']['run-task.py'] == RUNNER_SHA, 'runner_source_changed')
    # Execute the captured source and validate the actual frame against submission
    # fingerprints. A later file edit cannot silently change the reviewed task.
    source = '__file__=' + repr(str(HERE / 'run-task.py')) + '\n__name__="queued_runner"\n'
    source += raw.decode() + '\n'
    source += ('_original_validate=validate_inputs\n'
               'def validate_inputs(*args,**kwargs):\n'
               ' value=_original_validate(*args,**kwargs)\n'
               ' require(value[2]==' + repr(request['inputs']) + ',"queued_inputs_changed")\n'
               ' return value\n'
               'raise SystemExit(main())\n')
    return [PYTHON, '-I', '-S', '-B', '-c', source,
            '--task', str(path / 'task.json'), '--archive', str(path / 'input.tar'),
            '--tier', request['tier'], '--run']


def support_action(name):
    pin, seconds = SUPPORT[name]
    raw = owned(ROOT / 'support' / (name + '.py'), 180000)
    require(digest(raw) == pin, 'support_source_changed')
    compile(raw, 'reviewed-' + name, 'exec')
    code, _, _ = run_process(runtime_command(raw.decode(), ['--login'] if name == 'login-subscription' else []),
                             seconds, 2097152, login=name == 'login-subscription')
    require(code == 0, name.replace('-', '_') + '_failed')


def aws_error(error):
    """Recognize SSO renewal failures only; never label all STS failures expired."""
    text = error.decode('utf-8', 'replace')
    markers = ('Error when retrieving token from sso: Token has expired and refresh failed',
               'The SSO session associated with this profile has expired or is otherwise invalid')
    missing = re.search(r'^Error loading SSO Token: Token for [^\r\n]+ does not exist\s*$', text.strip())
    return 'sso_login_required' if any(marker in text for marker in markers) or missing else 'aws_check_failed'


def aws_identity(runner, tier):
    command = ['/opt/homebrew/bin/aws', 'sts', 'get-caller-identity', '--profile', runner.PROFILES[tier],
               '--region', 'us-east-1', '--output', 'json', '--no-cli-pager',
               '--cli-connect-timeout', '10', '--cli-read-timeout', '15']
    code, output, error = run_process(command, 45, 65536)
    if code:
        return aws_error(error)
    try:
        runner.executor_module().check_identity(json.loads(output), runner.ROLES[tier])
    except Exception:
        raise Stopped('aws_identity_mismatch') from None
    return 'ready'


def aws_login(profile):
    # Native CLI handles the browser, callback and refresh cache. Never capture its output.
    with open('/dev/tty', 'r+') as tty:
        command = ['/opt/homebrew/bin/aws', 'sso', 'login', '--profile', profile]
        process = subprocess.Popen(command, env=human_env(), stdin=tty, stdout=tty, stderr=tty, process_group=0)
        end = min(time.monotonic() + 600, SESSION_END or float('inf'))
        try:
            while process.poll() is None:
                require(time.monotonic() < end, 'aws_login_deadline')
                keep_ticket()
                time.sleep(.2)
            require(process.returncode == 0, 'aws_login_failed')
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)


def validate_request(path, runner):
    request = json.loads(owned(path / 'request.json'))
    require(set(request) == {'schema', 'job', 'kind', 'tier', 'created_at', 'pins', 'inputs'}
            and request['schema'] == 1 and request['job'] == path.name
            and request['kind'] in ('task', 'auth') and request['tier'] in runner.ROLES,
            'invalid_request')
    require(request['pins'] == source_pins(), 'queued_source_changed_resubmit')
    require(request['pins']['mac-agent.py'] == LOADED_SHA, 'worker_source_changed_restart_session')
    state = json.loads(owned(path / 'status.json'))
    require(state.get('job') == request['job'] and state.get('tier') == request['tier'],
            'queued_identity_changed')
    if request['kind'] == 'task':
        _, _, metadata = runner.validate_inputs(path / 'task.json', path / 'input.tar', request['tier'])
        require(metadata == request['inputs'], 'queued_inputs_changed')
    return request


def process_job(path):
    with locked('queue.lock', blocking=True):
        state = json.loads(owned(path / 'status.json'))
        require(state.get('status') == 'queued' and state.get('execution_started') is False,
                'job_cannot_be_replayed')
        receipt(path, status='validating')
    try:
        runner = runner_module()
        request = validate_request(path, runner)
        tier = request['tier']
        receipt(path, status='checking_aws')
        aws = aws_identity(runner, tier)
        if aws == 'sso_login_required':
            require(SESSION_END is None or SESSION_END - time.monotonic() >= 1400, 'new_session_needed_for_aws_login')
            receipt(path, status='needs_aws_login')
            print('AWS SSO needs renewal. Complete the browser sign-in.', flush=True)
            aws_login(runner.PROFILES[tier])
            aws = aws_identity(runner, tier)
        require(aws == 'ready', aws)
        receipt(path, status='checking_runtime')
        helper_sha = request['pins']['runtime-auth.py']
        runtime = runtime_auth(runner, expected_sha=helper_sha)
        if runtime['auth_state'] != 'valid':
            require(SESSION_END is None or SESSION_END - time.monotonic() >= 2150, 'new_session_needed_for_codex_login')
            receipt(path, status='renewing_codex')
            # Proof refresh and clean-state validation precede any auth file change.
            support_action('refresh-proofs')
            runtime_auth(runner, 'prepare-login', expected_sha=helper_sha)
            receipt(path, status='needs_codex_login')
            print('Codex needs a separate subscription sign-in. Use the newest code below.', flush=True)
            support_action('login-subscription')
            require(runtime_auth(runner, expected_sha=helper_sha)['auth_state'] == 'valid', 'codex_login_not_saved')
        if request['kind'] == 'auth':
            receipt(path, status='succeeded', reason='auth_ready_local_schema_and_aws_identity')
            return
        # Durable before launch. Crashes/failures from here are never automatically retried.
        receipt(path, status='running', execution_started=True)
        command = task_command(path, request)
        code, output, _ = run_process(command, 650)
        require(code == 0, 'task_failed_no_automatic_replay')
        result = json.loads(output)
        require(isinstance(result, dict) and isinstance(result.get('result'), str), 'invalid_task_result')
        write_new(path / 'result.json', output)
        require(runtime_auth(runner, expected_sha=helper_sha)['auth_state'] == 'valid', 'post_task_cleanup_or_auth_failed')
        receipt(path, status='succeeded', result_file=str(path / 'result.json'))
    except BaseException as error:
        current = json.loads(owned(path / 'status.json'))
        reason = str(error) if isinstance(error, Stopped) else type(error).__name__
        receipt(path, status='failed' if current.get('execution_started') else 'blocked', reason=reason)
        print('Request stopped: ' + reason + '. Inspect kingdom-aws status before continuing.', flush=True)
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise


def jobs():
    entries = list((ROOT / 'jobs').iterdir())
    require(len(entries) <= 256, 'queue_limit_archive_old_receipts')
    result = []
    for path in entries:
        require(re.fullmatch(JOB_PATTERN, path.name), 'unexpected_queue_entry')
        directory(path)
        if not (path / 'ready').exists():
            continue
        require(owned(path / 'ready', 8) == b'1\n', 'invalid_ready_marker')
        result.append(path)
    return sorted(result, key=lambda path: path.stat().st_mtime_ns)


def serve():
    global SESSION_END
    require(os.isatty(0) and os.isatty(1), 'human_terminal_required')
    with locked('session.lock'):
        print('KINGDOM AWS session: queued read-only tasks run serially.\n'
              'Enter your Mac password only at its prompt. Browser sign-ins appear only when needed.\n'
              'This window closes its session after 45 minutes or 10 minutes idle; no background service is installed.', flush=True)
        subprocess.run(['/usr/bin/sudo', '-v'], env=human_env(), check=True)
        SESSION_END = time.monotonic() + SESSION_SECONDS
        save(ROOT / 'session.json', {'status': 'active', 'pid': os.getpid(), 'expires_at': time.time() + SESSION_SECONDS})
        count, last_work = 0, time.monotonic()
        try:
            while time.monotonic() < SESSION_END and time.monotonic() - last_work < IDLE_SECONDS:
                if (ROOT / 'stop').exists():
                    break
                keep_ticket()
                pending = [path for path in jobs() if json.loads(owned(path / 'status.json')).get('status') == 'queued']
                if pending:
                    # Normal reuse needs one task budget; renewal checks its own budget.
                    if SESSION_END - time.monotonic() < 900 or count >= MAX_JOBS:
                        break
                    process_job(pending[0])
                    count += 1
                    last_work = time.monotonic()
                    completed = json.loads(owned(pending[0] / 'status.json'))
                    if completed.get('reason', '').startswith('new_session_needed_'):
                        break
                else:
                    time.sleep(.5)
        finally:
            save(ROOT / 'session.json', {'status': 'closed', 'closed_at': time.time()})
            subprocess.run(['/usr/bin/sudo', '-k'], env=human_env(), stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            if (ROOT / 'stop').exists():
                (ROOT / 'stop').unlink()
            print('KINGDOM AWS session closed. Queued work can continue with kingdom-aws start.', flush=True)


def status(job=None):
    paths = [job_path(job)] if job else jobs()
    records = [json.loads(owned(path / 'status.json')) for path in paths]
    return {'session_active': active_session(), 'jobs': records}


def resume(job):
    path = job_path(job)
    with locked('queue.lock', blocking=True):
        state = json.loads(owned(path / 'status.json'))
        require(state.get('execution_started') is False and state.get('status') in ('blocked', 'queued'),
                'execution_may_have_started_create_new_reviewed_task')
        validate_request(path, runner_module())
        receipt(path, status='queued', reason='explicitly_resumed_before_execution')
    start_session()
    return {'job': job, 'status': 'queued'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('plan', 'submit', 'auth'):
        child = sub.add_parser(command)
        if command != 'auth':
            child.add_argument('--task', required=True)
            child.add_argument('--archive', required=True)
        child.add_argument('--tier', choices=('inventory', 'iam-audit'), default='inventory')
    sub.add_parser('start')
    sub.add_parser('stop')
    sub.add_parser('_serve', help=argparse.SUPPRESS)
    child = sub.add_parser('status'); child.add_argument('job', nargs='?')
    child = sub.add_parser('resume'); child.add_argument('job')
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        if args.command != 'plan':
            initialize()
        if args.command in ('plan', 'submit', 'auth'):
            value = submit(args)
        elif args.command == 'start':
            value = start_session()
        elif args.command == 'status':
            value = status(args.job)
        elif args.command == 'resume':
            value = resume(args.job)
        elif args.command == 'stop':
            if active_session():
                if not (ROOT / 'stop').exists():
                    write_new(ROOT / 'stop', b'stop after current request\n')
            value = {'status': 'stop_requested_after_current_request'}
        else:
            def interrupted(number, frame):
                for item in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
                    signal.signal(item, signal.SIG_IGN)
                raise KeyboardInterrupt()
            for number in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
                signal.signal(number, interrupted)
            serve()
            return 0
        print(json.dumps(value, sort_keys=True))
        return 0
    except BaseException as error:
        print(json.dumps({'status': 'stopped', 'reason': str(error) if isinstance(error, Stopped)
                          else type(error).__name__}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
