#!/usr/bin/env python3
"""One inventory smoke task through the reviewed issuer and isolated launcher.

Offline unless --run. Human UID501 must already have a Terminal sudo ticket and
the separate runtime login. This wrapper never authenticates, reads credentials,
or receives the handoff bytes. Fixed reviewed source/paths/tier only.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time

HUMAN_HOME = '/Users/yournameisai'
RUNTIME_HOME = '/Users/aws-agent'
SOURCE = HUMAN_HOME + '/Desktop/aws-infra/infrastructure/agent-executor/executor.py'
RUNTIME_SOURCE = RUNTIME_HOME + '/agent-runtime/bundle/executor.py'
SOURCE_SHA = 'c75abdcc3b02e403850ad7d88f56fab6c0d2cf6c5ef3e115532fd1fcd18e537b'
OPERATOR_MANIFEST = HUMAN_HOME + '/.aws/agent-runtime/manifest.json'
RUNTIME_MANIFEST = RUNTIME_HOME + '/agent-runtime/tasks/manifest.json'
MODEL_AUTH = RUNTIME_HOME + '/agent-runtime/model-auth/auth.json'
TASK = RUNTIME_HOME + '/agent-runtime/tasks/inventory-smoke.json'
ARCHIVE = RUNTIME_HOME + '/agent-runtime/tasks/input.tar'
ROLE = {'role_arn': 'arn:aws:iam::034362054546:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_AWSInfraInventory_8e46b293825d7d57',
        'role_id': 'AROAQQABDK6JNUAHMXKMZ'}
PYTHON = '/opt/homebrew/bin/python3.13'
READY = b'AWS_AGENT_INVENTORY_SMOKE_READY\n'
RESULT_LIMIT = 524288
TOTAL_SECONDS = 600
GRACE_SECONDS = 35
CHILDREN = []


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def source_bytes(path, owner):
    require(str(Path(path).resolve()) == path, 'source_path_changed')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == owner and info.st_nlink == 1
                and not info.st_mode & 0o022, 'unsafe_executor_source')
        raw = stream.read(131073)
    require(len(raw) <= 131072 and hashlib.sha256(raw).hexdigest() == SOURCE_SHA, 'executor_source_pin_mismatch')
    return raw


def private_json(path, owner):
    parent = Path(path).parent
    metadata = parent.lstat()
    require(str(parent.resolve()) == str(parent) and stat.S_ISDIR(metadata.st_mode)
            and metadata.st_uid == owner and not metadata.st_mode & 0o077, 'unsafe_manifest_directory')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        metadata = os.fstat(stream.fileno())
        require(stat.S_ISREG(metadata.st_mode) and metadata.st_uid == owner and metadata.st_nlink == 1
                and not metadata.st_mode & 0o077, 'unsafe_manifest_file')
        raw = stream.read(65537)
    require(len(raw) <= 65536, 'manifest_too_large')
    value = json.loads(raw)
    require(value.get('account_id') == '034362054546' and value.get('region') == 'us-east-1'
            and value.get('roles', {}).get('inventory') == ROLE, 'inventory_identity_pin_mismatch')
    return value


# Both bootstraps read/compile the verified bytes themselves. They never execute
# an unverified source path after the check. Literal code below contains no auth.
COMMON = r'''
import argparse,hashlib,json,os,stat,sys,signal,types
from pathlib import Path
def checked(ok):
 if not ok: raise RuntimeError('Fixed child preflight failed')
def stop(signum,frame):
 raise RuntimeError('Task interrupted')
for number in (signal.SIGTERM,signal.SIGHUP,signal.SIGINT):signal.signal(number,stop)
def file_bytes(path,owner,limit,private=True):
 checked(str(Path(path).resolve())==path)
 with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK),'rb') as stream:
  info=os.fstat(stream.fileno())
  checked(stat.S_ISREG(info.st_mode) and info.st_uid==owner and info.st_nlink==1 and not info.st_mode & (0o077 if private else 0o022))
  raw=stream.read(limit+1)
 checked(len(raw)<=limit)
 return raw
def private_parent(path,owner):
 parent=Path(path).parent;info=parent.lstat()
 checked(parent.resolve()==parent and stat.S_ISDIR(info.st_mode) and info.st_uid==owner and not info.st_mode & 0o077)
def module(path,owner):
 raw=file_bytes(path,owner,131072,False)
 checked(hashlib.sha256(raw).hexdigest()==SOURCE_SHA)
 value=types.ModuleType('pinned_executor');value.__file__=path
 exec(compile(raw,path,'exec'),value.__dict__)
 checked(value.PROFILES['inventory']=='cambridge-agent-inventory')
 return value
'''


def bootstrap_constants():
    return '\n'.join(name + '=' + repr(value) for name, value in {
        'SOURCE_SHA': SOURCE_SHA, 'SOURCE': SOURCE, 'RUNTIME_SOURCE': RUNTIME_SOURCE,
        'OPERATOR_MANIFEST': OPERATOR_MANIFEST, 'RUNTIME_MANIFEST': RUNTIME_MANIFEST,
        'MODEL_AUTH': MODEL_AUTH, 'TASK': TASK, 'ARCHIVE': ARCHIVE, 'ROLE': ROLE,
    }.items()) + '\n'


ISSUER = r'''
try:
 checked(os.getuid()==os.geteuid()==501)
 private_parent(OPERATOR_MANIFEST,501)
 manifest=json.loads(file_bytes(OPERATOR_MANIFEST,501,65536))
 checked(manifest.get('account_id')=='034362054546' and manifest.get('region')=='us-east-1' and manifest.get('roles',{}).get('inventory')==ROLE)
 ex=module(SOURCE,501)
 checked(len(sys.argv)==2 and int(sys.argv[1])>=3)
 ex.issue(argparse.Namespace(manifest=OPERATOR_MANIFEST,tier='inventory',handoff_fd=int(sys.argv[1])))
except BaseException:
 sys.exit(1)
'''

TARGET = r'''
try:
 signal.signal(signal.SIGALRM,stop);signal.setitimer(signal.ITIMER_REAL,600)
 checked(os.getuid()==os.geteuid()==502 and os.getgid()==20 and 80 not in os.getgroups())
 checked(not os.access('/Users/yournameisai',os.X_OK))
 for path in (RUNTIME_SOURCE,RUNTIME_MANIFEST,MODEL_AUTH,TASK,ARCHIVE):private_parent(path,502)
 ex=module(RUNTIME_SOURCE,502)
 manifest=json.loads(file_bytes(RUNTIME_MANIFEST,502,65536))
 checked(ex.validate_manifest(manifest,'inventory')==ROLE)
 task=json.loads(file_bytes(TASK,502,65536));ex.validate_task(task)
 checked(set(task)=={'task_id','model','prompt'} and task['task_id']=='inventory-smoke' and task['model']=='gpt-5.6-luna')
 archive=file_bytes(ARCHIVE,502,ex.MAX_ARCHIVE);ex.unpack(archive)
 # Authentication metadata only here; ex.run owns its private read/refresh cycle.
 info=os.lstat(MODEL_AUTH)
 checked(stat.S_ISREG(info.st_mode) and info.st_uid==502 and info.st_nlink==1 and not info.st_mode & 0o077)
 env=ex.base_environment();env['HOME']='/Users/aws-agent'
 context=ex.bounded_command(['docker','context','show'],env,timeout=15,limit=4096)
 checked(context.strip()==b'colima-aws-agent')
 ex.inspect_network(manifest,env)
 # Fixed READY is the only preflight output; no credential/auth content is emitted.
 sys.stdout.write('AWS_AGENT_INVENTORY_SMOKE_READY\n');sys.stdout.flush()
 ex.run(argparse.Namespace(manifest=RUNTIME_MANIFEST,tier='inventory',model_auth=MODEL_AUTH,task=TASK,archive=ARCHIVE))
 signal.setitimer(signal.ITIMER_REAL,0)
except BaseException:
 sys.exit(1)
'''


def clean_environment(home, user):
    return {'HOME': home, 'USER': user, 'LOGNAME': user,
            'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C'}


def interrupt(signum, frame):
    raise RuntimeError('task_interrupted')


def signal_group(process, number):
    if process.poll() is None:
        try:
            os.killpg(process.pid, number)
        except (ProcessLookupError, PermissionError):
            pass


def cleanup():
    # SIGTERM unwinds target ex.run's finally, removing only its own container.
    # The reviewed executor starts its Docker/AWS children in separate groups;
    # its own unwinding terminates those children before returning.
    for process in CHILDREN:
        signal_group(process, signal.SIGTERM)
    deadline = time.monotonic() + GRACE_SECONDS
    while any(process.poll() is None for process in CHILDREN) and time.monotonic() < deadline:
        time.sleep(0.1)
    forced = any(process.poll() is None for process in CHILDREN)
    for process in CHILDREN:
        signal_group(process, signal.SIGKILL)
    for process in CHILDREN:
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            forced = True
    return not forced


def live_task():
    require(os.getuid() == os.geteuid() == 501, 'run_as_human_uid501')
    require(os.environ.get('HOME') == HUMAN_HOME, 'wrong_human_home')
    require(all(os.environ.get(key) in (None, 'cambridge-agent-inventory')
                for key in ('AWS_PROFILE', 'AWS_DEFAULT_PROFILE')), 'wrong_aws_profile')
    require(not any(key in os.environ for key in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY',
                'AWS_SESSION_TOKEN', 'AWS_SECURITY_TOKEN', 'AWS_CONFIG_FILE', 'AWS_SHARED_CREDENTIALS_FILE',
                'AWS_WEB_IDENTITY_TOKEN_FILE', 'AWS_ROLE_ARN', 'AWS_CONTAINER_CREDENTIALS_RELATIVE_URI',
                'AWS_CONTAINER_CREDENTIALS_FULL_URI')), 'inherited_aws_provider_override')
    tty = os.open('/dev/tty', os.O_RDONLY | os.O_NOCTTY)
    try:
        require(os.isatty(tty), 'terminal_required_for_existing_sudo_ticket')
    finally:
        os.close(tty)
    source_bytes(SOURCE, 501)
    private_json(OPERATOR_MANIFEST, 501)
    constants = bootstrap_constants()
    for code in (constants + COMMON + ISSUER, constants + COMMON + TARGET):
        ast.parse(code)
    deadline = time.monotonic() + TOTAL_SECONDS
    handoff_read, handoff_write = os.pipe()
    require(handoff_write >= 3, 'private_handoff_descriptor_required')
    target = issuer = None
    output = bytearray()
    try:
        runtime_env = clean_environment(RUNTIME_HOME, 'aws-agent')
        argv = ['/usr/bin/sudo', '-n', '-u', 'aws-agent', '-H', '/usr/bin/env', '-i']
        argv += [key + '=' + value for key, value in runtime_env.items()]
        argv += [PYTHON, '-I', '-S', '-B', '-c', constants + COMMON + TARGET]
        # Keep the Terminal's controlling TTY for its already-authorized sudo
        # ticket, but create an independent process group for bounded cleanup.
        target = subprocess.Popen(argv, cwd='/', env=clean_environment(HUMAN_HOME, 'yournameisai'),
                                  stdin=handoff_read, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  close_fds=True, process_group=0)
        CHILDREN.append(target)
        os.close(handoff_read); handoff_read = None
        os.set_blocking(target.stdout.fileno(), False)
        with selectors.DefaultSelector() as selector:
            selector.register(target.stdout, selectors.EVENT_READ)
            preflight_deadline = min(deadline, time.monotonic() + 150)
            ready = False
            while selector.get_map():
                require(time.monotonic() < deadline, 'task_deadline_reached')
                require(ready or time.monotonic() < preflight_deadline, 'target_preflight_deadline_reached')
                if issuer is not None and issuer.poll() not in (None, 0):
                    raise RuntimeError('inventory_issuance_failed')
                for key, _ in selector.select(0.2):
                    block = os.read(key.fd, 16384)
                    if not block:
                        selector.unregister(key.fileobj)
                        break
                    output.extend(block)
                    require(len(output) <= RESULT_LIMIT + len(READY), 'runtime_output_limit')
                    if not ready:
                        require(READY.startswith(bytes(output)) or output.startswith(READY), 'unexpected_target_preflight_output')
                        if output.startswith(READY):
                            del output[:len(READY)]
                            ready = True
                            issuer = subprocess.Popen([PYTHON, '-I', '-S', '-B', '-c', constants + COMMON + ISSUER,
                                                       str(handoff_write)], cwd='/',
                                env=clean_environment(HUMAN_HOME, 'yournameisai'), stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                pass_fds=(handoff_write,), start_new_session=True)
                            CHILDREN.append(issuer)
                            os.close(handoff_write); handoff_write = None
            require(ready and issuer is not None, 'target_preflight_failed')
        for process in (issuer, target):
            require(process.wait(timeout=max(0.01, deadline - time.monotonic())) == 0, 'inventory_smoke_failed')
        require(len(output) <= RESULT_LIMIT, 'runtime_output_limit')
        value = json.loads(output)
        require(set(value) == {'task_id', 'account_id', 'principal_arn', 'principal_id', 'expires_at', 'result'}
                and value['task_id'] == 'inventory-smoke' and value['account_id'] == '034362054546'
                and isinstance(value['result'], str) and len(value['result']) <= 262144,
                'unexpected_redacted_result')
        require(isinstance(value['principal_id'], str) and value['principal_id'].startswith(ROLE['role_id'] + ':')
                and isinstance(value['principal_arn'], str) and value['principal_arn'].startswith(
                    'arn:aws:sts::034362054546:assumed-role/' + ROLE['role_arn'].rsplit('/', 1)[1] + '/'),
                'result_inventory_identity_mismatch')
        # ex.run has removed original/refreshed literal auth values before this
        # result reaches the parent. Re-serialize JSON to escape terminal controls.
        return json.dumps(value, ensure_ascii=True)
    finally:
        for descriptor in (handoff_read, handoff_write):
            if descriptor is not None:
                os.close(descriptor)
        if target is not None and target.stdout is not None:
            target.stdout.close()


if __name__ == '__main__':
    if sys.argv[1:] != ['--run']:
        if sys.argv[1:]:
            print('Only the fixed --run action is supported.', file=sys.stderr)
            raise SystemExit(1)
        print(json.dumps({'mode': 'offline_plan', 'tier': 'inventory', 'task_id': 'inventory-smoke',
                          'source_sha256': SOURCE_SHA, 'task_limit_seconds': TOTAL_SECONDS,
                          'credential_handoff': 'issuer FD>=3 directly to runtime stdin'}))
        raise SystemExit(0)
    for number in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(number, interrupt)
    try:
        result = live_task()
    except BaseException:
        # Repeated signals must not skip the one bounded cleanup attempt.
        for number in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            signal.signal(number, signal.SIG_IGN)
        clean = cleanup()
        print('Inventory smoke failed; no credential output was released. '
              + ('Check the dedicated runtime before retrying; a fresh model login may be required.' if clean
                 else 'Cleanup could not be confirmed; inspect the dedicated runtime before retrying.'), file=sys.stderr)
        raise SystemExit(1)
    print(result)
