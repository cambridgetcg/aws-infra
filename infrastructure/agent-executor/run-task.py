#!/usr/bin/env python3
"""Validate reviewed task inputs; --run explicitly submits to the separate Mac runtime.

The parent handles task inputs and redacted results, never AWS or model credentials.
Executor source, account, two role identities, runtime paths and deadlines are fixed.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import stat
import struct
import subprocess
import sys
import time
import types

HUMAN_HOME = '/Users/yournameisai'
RUNTIME_HOME = '/Users/aws-agent'
SOURCE = HUMAN_HOME + '/Desktop/aws-infra/infrastructure/agent-executor/executor.py'
RUNTIME_SOURCE = RUNTIME_HOME + '/agent-runtime/bundle/executor.py'
SOURCE_SHA = 'c75abdcc3b02e403850ad7d88f56fab6c0d2cf6c5ef3e115532fd1fcd18e537b'
OPERATOR_MANIFEST = HUMAN_HOME + '/.aws/agent-runtime/manifest.json'
RUNTIME_MANIFEST = RUNTIME_HOME + '/agent-runtime/tasks/manifest.json'
TASKS = RUNTIME_HOME + '/agent-runtime/tasks'
MODEL_AUTH = RUNTIME_HOME + '/agent-runtime/model-auth/auth.json'
ROLES = {
    'inventory': {
        'role_arn': 'arn:aws:iam::034362054546:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_AWSInfraInventory_8e46b293825d7d57',
        'role_id': 'AROAQQABDK6JNUAHMXKMZ'},
    'iam-audit': {
        'role_arn': 'arn:aws:iam::034362054546:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_AWSInfraIAMAudit_d48977c79b403072',
        'role_id': 'AROAQQABDK6JD52OWMPGB'},
}
PROFILES = {'inventory': 'cambridge-agent-inventory', 'iam-audit': 'cambridge-iam-audit'}
PYTHON = '/opt/homebrew/bin/python3.13'
READY = b'AWS_AGENT_TASK_READY\n'
MAX_TASK = 65536
MAX_ARCHIVE = 8 * 1024 * 1024
RESULT_LIMIT = 524288
TOTAL_SECONDS = 600
GRACE_SECONDS = 35
CHILDREN = []
PHASE = 'input_validation'


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def owned_bytes(path, owner, limit, private=False):
    path = Path(os.path.abspath(os.path.expanduser(str(path))))
    require(path.resolve() == path, 'noncanonical_input_path')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == owner and info.st_nlink == 1
                and not info.st_mode & (0o077 if private else 0o022), 'unsafe_input_file')
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, 'input_too_large')
    return raw


def executor_module():
    raw = owned_bytes(SOURCE, 501, 131072)
    require(hashlib.sha256(raw).hexdigest() == SOURCE_SHA, 'executor_source_pin_mismatch')
    module = types.ModuleType('pinned_executor')
    module.__file__ = SOURCE
    exec(compile(raw, SOURCE, 'exec'), module.__dict__)
    require(module.PROFILES == PROFILES and module.MAX_ARCHIVE == MAX_ARCHIVE, 'executor_contract_changed')
    return module


def validate_inputs(task_path, archive_path, tier):
    require(tier in ROLES, 'unsupported_tier')
    require(os.getuid() == os.geteuid() == 501, 'run_as_human_uid501')
    ex = executor_module()
    task_raw = owned_bytes(task_path, 501, MAX_TASK)
    task = json.loads(task_raw)
    require(isinstance(task, dict) and set(task) == {'task_id', 'model', 'prompt'}, 'unexpected_task_schema')
    ex.validate_task(task)
    archive = owned_bytes(archive_path, 501, MAX_ARCHIVE)
    ex.unpack(archive)
    frame = struct.pack('!IQ', len(task_raw), len(archive)) + task_raw + archive
    return task, frame, {'task_sha256': hashlib.sha256(task_raw).hexdigest(),
                         'archive_sha256': hashlib.sha256(archive).hexdigest(),
                         'task_bytes': len(task_raw), 'archive_bytes': len(archive)}


COMMON = r'''
import argparse,hashlib,json,os,stat,sys,signal,types
from pathlib import Path
def checked(ok):
 if not ok: raise RuntimeError('Fixed child preflight failed')
def stop(signum,frame):
 for number in (signal.SIGTERM,signal.SIGHUP,signal.SIGINT,signal.SIGALRM):signal.signal(number,signal.SIG_IGN)
 signal.setitimer(signal.ITIMER_REAL,0)
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
 checked(value.PROFILES==PROFILES)
 return value
'''


# The frame reader never touches sys.stdin's buffering. After exact input bytes
# have been consumed, that stream remains available exclusively for ex.run's
# subsequent issuer credential envelope. No task data appears in child argv.
STAGING = r'''
import struct,tempfile
def read_exact(size):
 output=bytearray()
 while len(output)<size:
  block=os.read(0,min(65536,size-len(output)))
  checked(bool(block));output.extend(block)
 return bytes(output)
def receive_inputs(ex):
 task_size,archive_size=struct.unpack('!IQ',read_exact(12))
 checked(0<task_size<=65536 and 0<archive_size<=ex.MAX_ARCHIVE)
 task_raw=read_exact(task_size);archive=read_exact(archive_size)
 checked(hashlib.sha256(task_raw).hexdigest()==INPUT['task_sha256'] and hashlib.sha256(archive).hexdigest()==INPUT['archive_sha256'])
 task=json.loads(task_raw)
 checked(isinstance(task,dict) and set(task)=={'task_id','model','prompt'} and task['task_id']==TASK_ID)
 ex.validate_task(task);ex.unpack(archive)
 return task_raw,archive
def stage_file(directory,name,raw,files):
 with os.fdopen(os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory),'wb') as stream:
  identity=os.fstat(stream.fileno())
  files[name]=(identity.st_dev,identity.st_ino)
  stream.write(raw);stream.flush()
def remove_staging(path,directory,identity,files):
 # Remove only our recorded file inodes, never recurse through runtime content.
 if directory is None:return
 try:
  for name,expected in files.items():
   info=os.stat(name,dir_fd=directory,follow_symlinks=False)
   checked(stat.S_ISREG(info.st_mode) and (info.st_dev,info.st_ino)==expected)
   os.unlink(name,dir_fd=directory)
  info=os.lstat(path)
  checked(stat.S_ISDIR(info.st_mode) and (info.st_dev,info.st_ino)==identity)
  os.rmdir(path)
 finally:os.close(directory)
'''

PROOFS = r'''
import re
from datetime import datetime,timezone
def finished(report):
 value=datetime.fromisoformat(report['finished_at'].replace('Z','+00:00'))
 checked(value.tzinfo is not None and value<=datetime.now(timezone.utc))
 return value
def receipt_proofs(manifest,raw_manifest,network_id,proxy_ip,engine_id,outbound,reports,dns):
 checked(bool(reports))
 reports.sort(key=finished)
 report=reports[-1]
 latest=finished(report)
 # A newer failure (or a tied failure) never falls back to an older pass.
 checked(all(item.get('network_checks_status')=='passed' for item in reports if finished(item)==latest))
 checked(report.get('schema_version')==1 and report.get('activation_ready') is False
  and report.get('scope')=='credential-free-network-paths' and report.get('proxy_ipv4')==proxy_ip
  and len(report.get('checks',[]))==28 and all(item.get('status')=='passed' for item in report['checks']))
 checked(report.get('launcher_evidence')=={'image':manifest['image'],'network_id':network_id,
  'proxy_container_id':manifest['proxy_identity']['container_id'],
  'proxy_config_sha256':manifest['proxy_identity']['config_sha256']})
 finished(dns)
 checked(dns.get('schema')==1 and dns.get('success') is True and dns.get('activation_ready') is False
  and not dns.get('cleanup_failures'))
 expected={'engine_id':engine_id,'manifest_sha256':hashlib.sha256(raw_manifest).hexdigest(),
  'network_id':network_id,'outbound_id':outbound['Id'],'image_id':manifest['image'],
  'proxy_id':manifest['proxy_identity']['container_id'],'proxy_image_id':manifest['proxy_identity']['image_id'],
  'proxy_ipv4':proxy_ip,'proxy_config_sha256':manifest['proxy_identity']['config_sha256'],'resolver':'1.1.1.1'}
 evidence=dns.get('evidence',{})
 checked(isinstance(engine_id,str) and bool(engine_id) and all(evidence.get(key)==value for key,value in expected.items())
  and evidence.get('dns_passed') is True and evidence.get('deadline_cleanup',{}).get('passed') is True
  and set(outbound.get('Containers',{}))=={manifest['proxy_identity']['container_id']})
def check_receipts(ex,manifest,raw_manifest,network_id,proxy_ip,env):
 reports=[];count=0
 with os.scandir(TASKS) as entries:
  for entry in entries:
   count+=1;checked(count<=256)
   if re.fullmatch(r'network-probe-report[0-9A-Za-z-]*\.json',entry.name):
    reports.append(json.loads(file_bytes(TASKS+'/'+entry.name,502,1048576)))
    checked(len(reports)<=32)
 dns=json.loads(file_bytes(TASKS+'/dns-cleanup-report.json',502,1048576))
 call=lambda args:json.loads(ex.bounded_command(['docker',*args],env,timeout=30,limit=65536))
 checked(call(['context','inspect','colima-aws-agent','--format','{{json .Endpoints.docker.Host}}'])=='unix:///Users/aws-agent/.colima/aws-agent/docker.sock')
 engine_id=call(['info','--format','{{json .ID}}'])
 outbound=call(['network','inspect','aws-agent-outbound','--format','{{json .}}'])
 receipt_proofs(manifest,raw_manifest,network_id,proxy_ip,engine_id,outbound,reports,dns)
'''

ISSUER = r'''
try:
 checked(os.getuid()==os.geteuid()==501)
 private_parent(OPERATOR_MANIFEST,501)
 manifest=json.loads(file_bytes(OPERATOR_MANIFEST,501,65536))
 ex=module(SOURCE,501)
 checked(ex.validate_manifest(manifest,TIER)==ROLE)
 checked(len(sys.argv)==2 and int(sys.argv[1])>=3)
 ex.issue(argparse.Namespace(manifest=OPERATOR_MANIFEST,tier=TIER,handoff_fd=int(sys.argv[1])))
except BaseException:sys.exit(1)
'''

TARGET = r'''
stage=None;directory=None;identity=None;files={}
try:
 signal.signal(signal.SIGALRM,stop);signal.setitimer(signal.ITIMER_REAL,600)
 os.umask(0o077)
 checked(os.getuid()==os.geteuid()==502 and os.getgid()==20 and 80 not in os.getgroups())
 checked(not os.access('/Users/yournameisai',os.X_OK))
 for path in (RUNTIME_SOURCE,RUNTIME_MANIFEST,MODEL_AUTH):private_parent(path,502)
 ex=module(RUNTIME_SOURCE,502)
 raw_manifest=file_bytes(RUNTIME_MANIFEST,502,65536);manifest=json.loads(raw_manifest)
 checked(ex.validate_manifest(manifest,TIER)==ROLE)
 task_raw,archive=receive_inputs(ex)
 stage=tempfile.mkdtemp(prefix='submitted-',dir=TASKS)
 directory=os.open(stage,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 info=os.fstat(directory);identity=(info.st_dev,info.st_ino)
 checked(info.st_uid==502 and not info.st_mode & 0o077)
 stage_file(directory,'task.json',task_raw,files)
 stage_file(directory,'input.tar',archive,files)
 checked(str(Path(MODEL_AUTH).resolve())==MODEL_AUTH)
 info=os.lstat(MODEL_AUTH)
 checked(stat.S_ISREG(info.st_mode) and info.st_uid==502 and info.st_nlink==1 and not info.st_mode & 0o077)
 env=ex.base_environment();env['HOME']='/Users/aws-agent'
 context=ex.bounded_command(['docker','context','show'],env,timeout=15,limit=4096)
 checked(context.strip()==b'colima-aws-agent')
 network_id,proxy_ip=ex.inspect_network(manifest,env)
 check_receipts(ex,manifest,raw_manifest,network_id,proxy_ip,env)
 sys.stdout.write('AWS_AGENT_TASK_READY\n');sys.stdout.flush()
 ex.run(argparse.Namespace(manifest=RUNTIME_MANIFEST,tier=TIER,model_auth=MODEL_AUTH,task=stage+'/task.json',archive=stage+'/input.tar'))
except BaseException:sys.exit(1)
finally:
 try:remove_staging(stage,directory,identity,files)
 except BaseException:sys.exit(1)
 signal.setitimer(signal.ITIMER_REAL,0)
'''


def bootstraps(tier, task_id, metadata):
    values = {'SOURCE_SHA': SOURCE_SHA, 'SOURCE': SOURCE, 'RUNTIME_SOURCE': RUNTIME_SOURCE,
              'OPERATOR_MANIFEST': OPERATOR_MANIFEST, 'RUNTIME_MANIFEST': RUNTIME_MANIFEST,
              'MODEL_AUTH': MODEL_AUTH, 'TASKS': TASKS, 'ROLE': ROLES[tier], 'PROFILES': PROFILES,
              'TIER': tier, 'TASK_ID': task_id, 'INPUT': metadata}
    constants = '\n'.join(name + '=' + repr(value) for name, value in values.items()) + '\n'
    issuer, target = constants + COMMON + ISSUER, constants + COMMON + STAGING + PROOFS + TARGET
    ast.parse(issuer); ast.parse(target)
    return issuer, target


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


def live_task(task, frame, metadata, tier):
    global PHASE
    PHASE = 'human_preflight'
    require(os.getuid() == os.geteuid() == 501, 'run_as_human_uid501')
    require(os.environ.get('HOME') == HUMAN_HOME, 'wrong_human_home')
    require(all(os.environ.get(key) in (None, PROFILES[tier]) for key in ('AWS_PROFILE', 'AWS_DEFAULT_PROFILE')),
            'wrong_aws_profile')
    require(not any(key in os.environ for key in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY',
                'AWS_SESSION_TOKEN', 'AWS_SECURITY_TOKEN', 'AWS_CONFIG_FILE', 'AWS_SHARED_CREDENTIALS_FILE',
                'AWS_WEB_IDENTITY_TOKEN_FILE', 'AWS_ROLE_ARN', 'AWS_CONTAINER_CREDENTIALS_RELATIVE_URI',
                'AWS_CONTAINER_CREDENTIALS_FULL_URI')), 'inherited_aws_provider_override')
    tty = os.open('/dev/tty', os.O_RDONLY | os.O_NOCTTY)
    try:
        require(os.isatty(tty), 'terminal_required_for_existing_sudo_ticket')
    finally:
        os.close(tty)
    parent = Path(OPERATOR_MANIFEST).parent
    info = parent.lstat()
    require(parent.resolve() == parent and stat.S_ISDIR(info.st_mode) and info.st_uid == 501
            and not info.st_mode & 0o077, 'unsafe_manifest_directory')
    manifest = json.loads(owned_bytes(OPERATOR_MANIFEST, 501, MAX_TASK, private=True))
    require(executor_module().validate_manifest(manifest, tier) == ROLES[tier], 'operator_identity_pin_mismatch')
    issuer_code, target_code = bootstraps(tier, task['task_id'], metadata)
    deadline = time.monotonic() + TOTAL_SECONDS
    handoff_read, handoff_write = os.pipe()
    target = issuer = None
    output = bytearray()
    try:
        require(handoff_write >= 3, 'private_handoff_descriptor_required')
        runtime_env = clean_environment(RUNTIME_HOME, 'aws-agent')
        argv = ['/usr/bin/sudo', '-n', '-u', 'aws-agent', '-H', '/usr/bin/env', '-i']
        argv += [key + '=' + value for key, value in runtime_env.items()]
        argv += [PYTHON, '-I', '-S', '-B', '-c', target_code]
        PHASE = 'runtime_preflight'
        target = subprocess.Popen(argv, cwd='/', env=clean_environment(HUMAN_HOME, 'yournameisai'),
                                  stdin=handoff_read, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  close_fds=True, process_group=0)
        CHILDREN.append(target)
        os.close(handoff_read); handoff_read = None
        os.set_blocking(target.stdout.fileno(), False)
        os.set_blocking(handoff_write, False)
        sent = 0
        with selectors.DefaultSelector() as selector:
            selector.register(target.stdout, selectors.EVENT_READ, 'output')
            selector.register(handoff_write, selectors.EVENT_WRITE, 'input')
            preflight_deadline = min(deadline, time.monotonic() + 150)
            ready = False
            while selector.get_map():
                require(time.monotonic() < deadline, 'task_deadline_reached')
                require(ready or time.monotonic() < preflight_deadline, 'runtime_preflight_deadline_reached')
                if issuer is not None and issuer.poll() not in (None, 0):
                    raise RuntimeError('issuance_failed')
                for key, _ in selector.select(0.2):
                    if key.data == 'input':
                        try:
                            written = os.write(handoff_write, memoryview(frame)[sent:sent + 65536])
                        except BlockingIOError:
                            continue
                        require(written > 0, 'input_transport_failed')
                        sent += written
                        if sent == len(frame):
                            selector.unregister(handoff_write)
                            os.set_blocking(handoff_write, True)
                        continue
                    block = os.read(key.fd, 16384)
                    if not block:
                        require(ready, 'runtime_preflight_failed')
                        selector.unregister(key.fileobj)
                        break
                    output.extend(block)
                    require(len(output) <= RESULT_LIMIT + len(READY), 'runtime_output_limit')
                    if not ready:
                        require(READY.startswith(bytes(output)) or output.startswith(READY), 'unexpected_runtime_preflight_output')
                        if output.startswith(READY):
                            require(sent == len(frame), 'ready_before_inputs_transferred')
                            del output[:len(READY)]
                            ready = True
                            PHASE = 'issuing_and_running'
                            issuer = subprocess.Popen([PYTHON, '-I', '-S', '-B', '-c', issuer_code, str(handoff_write)],
                                cwd='/', env=clean_environment(HUMAN_HOME, 'yournameisai'), stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                pass_fds=(handoff_write,), start_new_session=True)
                            CHILDREN.append(issuer)
                            os.close(handoff_write); handoff_write = None
            require(ready and issuer is not None, 'runtime_preflight_failed')
        for process in (issuer, target):
            require(process.wait(timeout=max(0.01, deadline - time.monotonic())) == 0, 'task_failed')
        PHASE = 'result_validation'
        require(len(output) <= RESULT_LIMIT, 'runtime_output_limit')
        value = json.loads(output)
        require(set(value) == {'task_id', 'account_id', 'principal_arn', 'principal_id', 'expires_at', 'result'}
                and value['task_id'] == task['task_id'] and value['account_id'] == '034362054546'
                and isinstance(value['result'], str) and len(value['result']) <= 262144,
                'unexpected_redacted_result')
        role = ROLES[tier]
        require(isinstance(value['principal_id'], str) and value['principal_id'].startswith(role['role_id'] + ':')
                and isinstance(value['principal_arn'], str) and value['principal_arn'].startswith(
                    'arn:aws:sts::034362054546:assumed-role/' + role['role_arn'].rsplit('/', 1)[1] + '/'),
                'result_identity_mismatch')
        return json.dumps(value, ensure_ascii=True)
    finally:
        for descriptor in (handoff_read, handoff_write):
            if descriptor is not None:
                os.close(descriptor)
        if target is not None and target.stdout is not None:
            target.stdout.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', required=True, help='Reviewed JSON with task_id, model and prompt')
    parser.add_argument('--archive', required=True, help='Reviewed uncompressed TAR, at most 8 MiB')
    parser.add_argument('--tier', choices=tuple(ROLES), default='inventory')
    parser.add_argument('--run', action='store_true', help='Submit after existing Terminal sudo and scoped SSO login')
    args = parser.parse_args(argv)
    for number in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(number, interrupt)
    try:
        task, frame, metadata = validate_inputs(args.task, args.archive, args.tier)
        if not args.run:
            print(json.dumps({'mode': 'offline_validated', 'tier': args.tier, 'profile': PROFILES[args.tier],
                              'task_id': task['task_id'], 'model': task['model'], 'source_sha256': SOURCE_SHA,
                              'inputs': metadata, 'task_limit_seconds': TOTAL_SECONDS}))
            return 0
        result = live_task(task, frame, metadata, args.tier)
    except BaseException:
        for number in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            signal.signal(number, signal.SIG_IGN)
        clean = cleanup()
        print('Task failed during ' + PHASE + '; no credential output was released. '
              + ('Inspect the dedicated runtime before retrying; a fresh model login may be required.' if clean
                 else 'Cleanup could not be confirmed; inspect the dedicated runtime before retrying.'), file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
