#!/usr/bin/env python3
"""Fresh subscription login in the verified image. Offline unless --login."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import io
import json
import os
from pathlib import Path
import re
import secrets
import selectors
import signal
import stat
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import executor as ex

DEVICE_URL = "https://auth.openai.com/codex/device"
READY = "AWS_AGENT_SUBSCRIPTION_LOGIN_READY"
MAX_PROMPT = 32768
LOGIN_SECONDS = 930
WRAPPER = r'''
import os, pathlib, subprocess, sys, time
os.umask(0o077)
home = pathlib.Path('/home/agent/.codex')
home.mkdir(mode=0o700)
env = {'HOME':'/home/agent', 'CODEX_HOME':str(home), 'PATH':'/usr/local/bin:/usr/bin:/bin',
       'HTTP_PROXY':'http://egress:3128', 'HTTPS_PROXY':'http://egress:3128'}
command = ['codex', '-c', 'forced_login_method="chatgpt"', '-c', 'cli_auth_credentials_store="file"',
           'login', '--device-auth']
try:
    result = subprocess.run(command, env=env, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)
except subprocess.TimeoutExpired:
    sys.exit(1)
if result.returncode != 0:
    sys.exit(1)
print('AWS_AGENT_SUBSCRIPTION_LOGIN_READY', flush=True)
time.sleep(120)
'''

# Docker cp does not reliably read tmpfs-backed paths. Read this fixed file
# inside the existing container; only the private launcher pipe receives it.
READ_AUTH = r'''
import os, stat, sys
def private_auth_bytes(path, limit):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not (stat.S_ISREG(info.st_mode) and info.st_uid == info.st_gid == 10001
                and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600
                and 0 < info.st_size <= limit):
            raise ValueError('Invalid private authentication file')
        raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError('Authentication size limit exceeded')
        current = os.fstat(stream.fileno())
        if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (
                info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) or len(raw) != info.st_size:
            raise ValueError('Authentication file changed during read')
        return raw
if __name__ == '__main__':
    try:
        if os.getuid() != 10001 or os.getgid() != 10001:
            raise ValueError('Unexpected reader identity')
        sys.stdout.buffer.write(private_auth_bytes('/home/agent/.codex/auth.json', 65536))
        sys.stdout.buffer.flush()
    except BaseException:
        sys.exit(1)
'''


def verify_network_evidence(report, manifest, network_id, proxy_ip):
    ex.require(report.get("schema_version") == 1 and report.get("network_checks_status") == "passed"
               and report.get("activation_ready") is False and report.get("proxy_ipv4") == proxy_ip,
               "A successful credential-free network probe is required before login")
    evidence = report.get("launcher_evidence", {})
    ex.require(evidence == {"image": manifest["image"], "network_id": network_id,
                           "proxy_container_id": manifest["proxy_identity"]["container_id"],
                           "proxy_config_sha256": manifest["proxy_identity"]["config_sha256"]},
               "Network probe does not match the current runtime")
    finished = datetime.fromisoformat(report["finished_at"].replace("Z", "+00:00"))
    ex.require(finished.tzinfo is not None and 0 <= (datetime.now(timezone.utc) - finished).total_seconds() <= 1800,
               "Network probe must have completed within 30 minutes")


def prompt_line(line, state):
    """Emit only the expected URL and prompted uppercase code, never raw logs."""
    line = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
    if line == DEVICE_URL and not state.get("url"):
        state["url"] = True
        return DEVICE_URL
    if line.startswith("2. Enter this one-time code") and state.get("url"):
        state["expect_code"] = True
    elif state.get("expect_code") and re.fullmatch(r"[A-Z0-9]{4}-[A-Z0-9]{4,8}", line):
        state["expect_code"], state["code"] = False, True
        return "One-time device code: " + line
    return None


def parse_auth(raw):
    authentication = ex.read_json(io.BytesIO(raw), ex.MAX_MODEL_AUTH)
    ex.validate_model_auth(authentication)
    return authentication


@contextmanager
def new_auth_target(path):
    path = Path(path)
    ex.require(path.is_absolute() and path.parent.resolve() == path.parent,
               "Use a canonical absolute private runtime authentication path")
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    lock = reservation = None
    saved = False
    try:
        info = os.fstat(directory)
        ex.require(info.st_uid == os.getuid() and not info.st_mode & 0o077,
                   "Authentication directory must be private and runtime-owned")
        lock = os.open(".subscription-auth.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        info = os.fstat(lock)
        ex.require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1
                   and not info.st_mode & 0o077, "Authentication lock must be private and owned")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        reservation = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        original = os.fstat(reservation)

        def save(authentication):
            nonlocal saved
            ex.validate_model_auth(authentication)
            current = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
            ex.require((current.st_dev, current.st_ino, current.st_size) == (original.st_dev, original.st_ino, 0),
                       "Authentication destination changed during login")
            temporary = ".subscription-login-" + secrets.token_hex(16)
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(json.dumps(authentication).encode())
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
                os.fsync(directory)
                saved = True
            finally:
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass
        yield save
    finally:
        if reservation is not None:
            os.close(reservation)
            if not saved:
                try:
                    current = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
                    if (current.st_dev, current.st_ino, current.st_size) == (original.st_dev, original.st_ino, 0):
                        os.unlink(path.name, dir_fd=directory)
                except FileNotFoundError:
                    pass
        if lock is not None:
            os.close(lock)
        os.close(directory)


def _login(args, phase):
    ex.require_runtime_user()
    manifest = ex.operator_json(args.manifest)
    report = ex.operator_json(args.network_evidence)
    env = ex.base_environment()
    env["HOME"] = str(Path.home())
    network_id, proxy_ip = ex.inspect_network(manifest, env)
    verify_network_evidence(report, manifest, network_id, proxy_ip)
    name = "aws-agent-login-" + secrets.token_hex(16)
    command = ex.docker_command(manifest, name, network_id, proxy_ip)
    command.remove("--rm")
    command = command[:-2] + ["-c", WRAPPER]
    process = None
    with new_auth_target(args.output_auth) as save:
        try:
            process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
            deadline, received, pending, state = time.monotonic() + LOGIN_SECONDS, 0, b"", {}
            ready = False
            with selectors.DefaultSelector() as selector:
                os.set_blocking(process.stdout.fileno(), False)
                selector.register(process.stdout, selectors.EVENT_READ)
                while not ready:
                    ex.require(time.monotonic() < deadline and process.poll() is None,
                               "Subscription login did not complete; diagnostics suppressed")
                    for key, _ in selector.select(0.2):
                        chunk = os.read(key.fd, 4096)
                        ex.require(chunk, "Subscription login closed without success")
                        received += len(chunk)
                        ex.require(received <= MAX_PROMPT, "Subscription login output exceeded its bound")
                        pending += chunk
                        while b"\n" in pending:
                            line, pending = pending.split(b"\n", 1)
                            line = line.decode("utf-8", "replace")
                            if line == READY:
                                ex.require(state.get("url") and state.get("code"), "Expected device-code flow was not observed")
                                ready = True
                                phase("client-complete")
                                break
                            message = prompt_line(line, state)
                            if message:
                                print(message, flush=True)
            phase("read-auth")
            raw = ex.bounded_command(["docker", "exec", "--user", "10001:10001", name,
                                      "/usr/local/bin/python3", "-I", "-B", "-c", READ_AUTH],
                                     env, timeout=30, limit=ex.MAX_MODEL_AUTH)
            phase("validate-auth")
            authentication = parse_auth(raw)
            phase("save-auth")
            save(authentication)
        finally:
            cleaned = False
            try:
                cleanup = subprocess.run(["docker", "rm", "--force", name], env=env, stdin=subprocess.DEVNULL,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
                cleaned = cleanup.returncode == 0
            finally:
                if process is not None:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                    process.stdout.close()
                if not cleaned:
                    print(json.dumps({"status": "cleanup_unverified", "container": name}), file=sys.stderr)
            ex.require(cleaned, "Login container cleanup failed; inspect the reported container before continuing")
    print(json.dumps({"status": "subscription_login_saved", "auth_path": str(args.output_auth),
                      "authentication_printed": False, "aws_credentials_supplied": False, "activation_ready": False}))


def login(args):
    current_phase = "login"

    def phase(value):
        nonlocal current_phase
        current_phase = value
        print(json.dumps({"status": "subscription_login_phase", "phase": value}), file=sys.stderr, flush=True)

    phase("login")
    try:
        _login(args, phase)
    except BaseException as error:
        print(json.dumps({"status": "subscription_login_failed", "phase": current_phase,
                          "error_class": type(error).__name__}), file=sys.stderr, flush=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--login", action="store_true")
    parser.add_argument("--manifest")
    parser.add_argument("--network-evidence")
    parser.add_argument("--output-auth")
    args = parser.parse_args()
    if not args.login:
        print("Offline plan: fresh device login in the verified container; no credential access or runtime changes.")
        return 0
    if not all((args.manifest, args.network_evidence, args.output_auth)):
        parser.error("--login requires --manifest, --network-evidence and a new --output-auth path")
    try:
        login(args)
        return 0
    except BaseException:
        # login() already emitted only fixed phases and the exception class.
        pass
    return 1


if __name__ == "__main__":
    sys.exit(main())
