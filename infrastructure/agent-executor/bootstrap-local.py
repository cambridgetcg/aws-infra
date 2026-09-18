#!/usr/bin/env python3
"""Plan a locked local runtime identity; --apply (root only) creates/stages, never starts it.

Native references: dscl(1), createhomedir(1), DirectoryServiceAttributes(7),
Apple SDK DirServicesConst.h (kDSValueAuthAuthorityDisabledUser), and CFODNode.h
(ODNodeCreateRecord). Native record creation avoids dscl's property-upsert behavior.
No passwords, login tokens, sudo rules, VM starts, or network setup are performed.
"""

import argparse
import ctypes
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import plistlib
import pwd
import stat
import subprocess
import sys
import uuid

HUMAN = "yournameisai"
HUMAN_UID = 501
HUMAN_HOME = Path("/Users/yournameisai")
ACCOUNT = "aws-agent"
ACCOUNT_HOME = Path("/Users/aws-agent")
SOURCE = HUMAN_HOME / "Desktop/aws-infra/infrastructure/agent-executor"
LOCK = Path("/private/var/run/aws-infra-agent-bootstrap.lock")
ACCESS_PROBE = Path("/bin/test")
FILES = {
    "Dockerfile": "agent-runtime/bundle/Dockerfile",
    "proxy.Dockerfile": "agent-runtime/bundle/proxy.Dockerfile",
    ".dockerignore": "agent-runtime/bundle/.dockerignore",
    "executor.py": "agent-runtime/bundle/executor.py",
    "login-subscription.py": "agent-runtime/bundle/login-subscription.py",
    "probe_network.py": "agent-runtime/bundle/probe_network.py",
    "README.md": "agent-runtime/bundle/README.md",
    "setup-local.md": "agent-runtime/bundle/setup-local.md",
    "proxy-runtime.md": "agent-runtime/bundle/proxy-runtime.md",
    "subscription-auth.md": "agent-runtime/bundle/subscription-auth.md",
    "manifest.example.json": "agent-runtime/bundle/manifest.example.json",
    "task.example.json": "agent-runtime/bundle/task.example.json",
    "egress.squid.conf": "agent-runtime/proxy/egress.squid.conf",
    "setup-local.example.yaml": ".colima/aws-agent/colima.yaml",
}
FILE_MODES = {"egress.squid.conf": 0o644}  # Nonsecret policy must be readable by Squid's container UID.


class Rejected(Exception):
    pass


def require(condition, message):
    if not condition:
        raise Rejected(message)


def command(arguments):
    result = subprocess.run(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, timeout=30,
                            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C"})
    require(result.returncode == 0 and len(result.stdout) <= 1024 * 1024, "Local metadata command failed")
    return result.stdout


def record(name, keys):
    value = plistlib.loads(command(["/usr/bin/dscl", "-plist", ".", "-read", "/Users/" + name, *keys]))
    return {key.rsplit(":", 1)[-1]: item for key, item in value.items()}


def validate_human(value, metadata):
    require(value.get("UniqueID") == [str(HUMAN_UID)] and value.get("RecordName") == [HUMAN]
            and value.get("NFSHomeDirectory") == [str(HUMAN_HOME)], "Known human identity does not match")
    require(stat.S_ISDIR(metadata.st_mode) and metadata.st_uid == HUMAN_UID
            and stat.S_IMODE(metadata.st_mode) == 0o700, "Human home must remain private and owned by UID 501")


def choose_uid(users):
    require(ACCOUNT not in users, "Runtime account already exists; it will not be changed")
    used = set(users.values())
    for candidate in range(502, 60000):
        if candidate not in used:
            try:
                pwd.getpwuid(candidate)
            except KeyError:
                return candidate
    raise Rejected("No unused UID in the permitted range")


def reviewed_bytes(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        require(stat.S_ISREG(metadata.st_mode) and metadata.st_uid in (0, HUMAN_UID)
                and not metadata.st_mode & 0o022, "Source must be a regular operator-controlled file")
        data = stream.read(1024 * 1024 + 1)
        require(len(data) <= 1024 * 1024, "Source file exceeds staging limit")
        return data


def preflight():
    require(sys.platform == "darwin", "This bootstrap is only for the reviewed Mac")
    require(ACCESS_PROBE.is_file() and os.access(ACCESS_PROBE, os.X_OK), "Required macOS access probe is unavailable")
    validate_human(record(HUMAN, ["UniqueID", "NFSHomeDirectory", "RecordName"]), HUMAN_HOME.lstat())
    users = {}
    for line in command(["/usr/bin/dscl", ".", "-list", "/Users", "UniqueID"]).decode().splitlines():
        name, uid = line.rsplit(None, 1)
        users[name] = int(uid)
    try:
        pwd.getpwnam(ACCOUNT)
    except KeyError:
        pass
    else:
        raise Rejected("Runtime identity resolves already; it will not be changed")
    require(not os.path.lexists(ACCOUNT_HOME), "Runtime home already exists; it will not be changed")
    parent = ACCOUNT_HOME.parent.lstat()
    require(stat.S_ISDIR(parent.st_mode) and parent.st_uid == 0 and not parent.st_mode & 0o022,
            "The Users parent must be a root-owned directory")
    require(grp.getgrnam("staff").gr_gid == 20 and grp.getgrnam("admin").gr_gid == 80,
            "Unexpected macOS group IDs")
    # Reject symlinked or shared-writable source ancestry before any privileged copy.
    for directory in (SOURCE, *SOURCE.parents):
        metadata = directory.lstat()
        require(stat.S_ISDIR(metadata.st_mode) and metadata.st_uid in (0, HUMAN_UID)
                and not metadata.st_mode & 0o022, "Source ancestry must be operator controlled")
    content = {name: reviewed_bytes(SOURCE / name) for name in FILES}
    return choose_uid(users), content


def attributes(uid, guid):
    values = {"UniqueID": str(uid), "PrimaryGroupID": "20", "NFSHomeDirectory": str(ACCOUNT_HOME),
              "UserShell": "/usr/bin/false", "RealName": "Isolated AWS Agent Runtime",
              "GeneratedUID": guid, "AuthenticationAuthority": ";DisabledUser;"}
    result = {"dsAttrTypeStandard:" + key: [value] for key, value in values.items()}
    result["dsAttrTypeNative:IsHidden"] = ["1"]
    return result


class NativeDirectory:
    """Small binding to Apple's create-only API; never updates existing records."""
    def __init__(self):
        pointer = ctypes.c_void_p
        self.cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self.od = ctypes.CDLL("/System/Library/Frameworks/OpenDirectory.framework/Versions/A/Frameworks/CFOpenDirectory.framework/CFOpenDirectory")
        self.owned = []
        signatures = (
            (self.cf.CFDataCreate, [pointer, ctypes.c_char_p, ctypes.c_long], pointer),
            (self.cf.CFPropertyListCreateWithData, [pointer, pointer, ctypes.c_ulong, pointer, ctypes.POINTER(pointer)], pointer),
            (self.cf.CFRelease, [pointer], None),
            (self.od.ODNodeCreateWithName, [pointer, pointer, pointer, ctypes.POINTER(pointer)], pointer),
            (self.od.ODNodeCreateRecord, [pointer, pointer, pointer, pointer, ctypes.POINTER(pointer)], pointer),
        )
        for function, arguments, result in signatures:
            function.argtypes, function.restype = arguments, result

    def value(self, value):
        raw = plistlib.dumps(value)
        data = self.cf.CFDataCreate(None, raw, len(raw))
        require(data, "Native property-list allocation failed")
        error = ctypes.c_void_p()
        try:
            result = self.cf.CFPropertyListCreateWithData(None, data, 0, None, ctypes.byref(error))
        finally:
            self.cf.CFRelease(data)
            if error.value:
                self.cf.CFRelease(error)
        require(result, "Native property-list conversion failed")
        self.owned.append(result)
        return result

    def open_local(self):
        error = ctypes.c_void_p()
        session = ctypes.c_void_p.in_dll(self.od, "kODSessionDefault")
        node = self.od.ODNodeCreateWithName(None, session, self.value("/Local/Default"), ctypes.byref(error))
        if error.value:
            self.cf.CFRelease(error)
        require(node, "Could not open the local directory node")
        self.owned.append(node)
        return node

    def create(self, uid, guid):
        require(os.geteuid() == 0, "Account creation requires root")
        node = self.open_local()
        error = ctypes.c_void_p()
        result = self.od.ODNodeCreateRecord(node, self.value("dsRecTypeStandard:Users"), self.value(ACCOUNT),
                                            self.value(attributes(uid, guid)), ctypes.byref(error))
        if error.value:
            self.cf.CFRelease(error)
        require(result, "Native record creation failed; existing records are never updated")
        self.owned.append(result)

    def close(self):
        for value in reversed(self.owned):
            self.cf.CFRelease(value)
        self.owned.clear()


def plan(uid, content):
    return {"mode": "plan", "account": ACCOUNT, "uid": uid, "gid": 20, "home": str(ACCOUNT_HOME),
            "authentication": "disabled; no password, login token, or administrator membership",
            "creation": "OpenDirectory create-only API; existing account/home always refused",
            "home_mode": "0700", "default_file_mode": "0600", "starts_runtime": False,
            "files": [{"source": name, "destination": str(ACCOUNT_HOME / destination),
                       "mode": format(FILE_MODES.get(name, 0o600), "04o"),
                       "sha256": hashlib.sha256(content[name]).hexdigest()} for name, destination in FILES.items()]}


def verify_account(uid, guid):
    full_attributes = attributes(uid, guid)
    expected = {key.rsplit(":", 1)[-1]: value for key, value in full_attributes.items()}
    current = record(ACCOUNT, list(full_attributes))
    require(all(current.get(key) == value for key, value in expected.items()), "Created identity verification failed")
    require(80 not in os.getgrouplist(ACCOUNT, 20), "Runtime unexpectedly has administrator membership")
    require(pwd.getpwnam(ACCOUNT).pw_uid == uid, "Runtime identity did not resolve to the selected UID")
    matching = []
    for line in command(["/usr/bin/dscl", ".", "-list", "/Users", "UniqueID"]).decode().splitlines():
        name, value = line.rsplit(None, 1)
        if int(value) == uid:
            matching.append(name)
    require(matching == [ACCOUNT], "Selected UID is no longer unique; stop before runtime activation")


def stage(uid, content):
    # The new home stays root-owned until all exclusive writes finish.
    for directory in (".colima", ".colima/aws-agent", "agent-runtime", "agent-runtime/bundle",
                      "agent-runtime/proxy", "agent-runtime/tasks"):
        (ACCOUNT_HOME / directory).mkdir(mode=0o700)
    for name, relative in FILES.items():
        descriptor = os.open(ACCOUNT_HOME / relative, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(content[name])
            os.fchmod(output.fileno(), FILE_MODES.get(name, 0o600))
    for base, directories, files in os.walk(ACCOUNT_HOME, topdown=False, followlinks=False):
        for name in files:
            os.chown(Path(base) / name, uid, 20, follow_symlinks=False)
        os.chown(base, uid, 20, follow_symlinks=False)


def apply():
    require(os.geteuid() == 0, "--apply requires human-authorized root execution")
    descriptor = os.open(LOCK, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as lock:
        metadata = os.fstat(lock.fileno())
        require(stat.S_ISREG(metadata.st_mode) and metadata.st_uid == 0
                and stat.S_IMODE(metadata.st_mode) == 0o600, "Unexpected bootstrap lock")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        uid, content = preflight()
        guid = str(uuid.uuid4()).upper()
        native = NativeDirectory()
        os.umask(0o077)
        phase = "home creation"
        try:
            # mkdir is exclusive: another account's existing home is never reused.
            ACCOUNT_HOME.mkdir(mode=0o700)
            phase = "identity creation"
            native.create(uid, guid)
            phase = "initial identity verification"
            verify_account(uid, guid)
            phase = "file staging"
            stage(uid, content)
            phase = "staged identity verification"
            verify_account(uid, guid)
            phase = "human-home access check"
            result = subprocess.run([str(ACCESS_PROBE), "-x", str(HUMAN_HOME)], user=uid, group=20,
                                    extra_groups=os.getgrouplist(ACCOUNT, 20), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, env={}, timeout=10)
            require(result.returncode == 1, "Runtime must not be able to traverse the human home")
        except Exception as error:
            # Do not delete records or homes on failure; never turn this into a broad cleanup tool.
            raise Rejected(f"Bootstrap incomplete during {phase} ({type(error).__name__}); inspect the locked identity/private home before any retry. No runtime was started.") from None
        finally:
            native.close()
    output = plan(uid, content)
    output["mode"] = "created-and-staged"
    print(json.dumps(output, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--plan", action="store_true", help="default; read-only metadata and file-hash review")
    modes.add_argument("--apply", action="store_true", help="root only; create locked account/private home and stage files")
    args = parser.parse_args()
    try:
        if args.apply:
            apply()
        else:
            uid, content = preflight()
            print(json.dumps(plan(uid, content), indent=2))
        return 0
    except Rejected as error:
        print(str(error), file=sys.stderr)
    except Exception:
        print("Bootstrap failed; diagnostics suppressed. No automatic cleanup or runtime start.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
