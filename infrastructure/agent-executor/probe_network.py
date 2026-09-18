#!/usr/bin/env python3
"""Credential-free probes, run INSIDE the reviewed executor container before handoff.

Usage: python3 -I -B /opt/probe_network.py --config - < private-probe.json
Package this script in the same reviewed image; use the executor's exact runtime
flags with this Python target and stream the config on stdin. No host bind is
needed. A protected regular config file is also accepted instead of '-'.
This script never invokes Docker, AWS CLI, or a model. It sends unauthenticated
HTTPS HEAD requests through Squid and TCP connection attempts to selected IPs.
Do not give its container credentials, host mounts, or a Docker socket.

The operator-owned JSON config has exactly two keys:
  proxy_ipv4: the independently inspected proxy IPv4 address
  targets: five {name, ip, port} objects named host, private, metadata, public,
           and ipv6. Use the actual host/VM address and reviewed test targets.
           host/private must be RFC1918, metadata IPv4 link-local, public and
           ipv6 globally routable. Targets must differ from the proxy.

A successful connection FAILS isolation. Only an explicit kernel permission
denial, ENETUNREACH with no route, or IPv6 EADDRNOTAVAIL with every interface
disabled and no IPv6 addresses/routes, passes a direct-path check.
Timeout, refusal and EHOSTUNREACH stay INCONCLUSIVE: they can
mean a nonexistent/stopped target. Use known-live before/after canaries to
investigate those results; this harness does not certify such external evidence.

Proxy negatives pass only on Squid's explicit ERR_ACCESS_DENIED HTTP 403, never
on connection failure, DNS failure, TLS failure or 502/503. Positive checks must
complete certificate-verified TLS and receive HTTP from every allowed endpoint.

This is a partial network gate, NOT an activation certificate. Separately test
UDP/TCP DNS to 127.0.0.11, 127.0.0.1 and an external resolver using an authoritative
canary or packet capture: no reply alone does not prove no DNS query escaped.
Also exercise the real external expiry watchdog with a credential-free dummy
workload that ignores termination, and verify forced container removal. A local
sleep timeout cannot attest the production container lifecycle or AWS expiry.
"""

import argparse
from datetime import datetime, timezone
import errno
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
import stat
import sys
import time

TIMEOUT = 3
# Codex rust-v0.154.0 / 6b9826e3aa83b1a5947db50f4332cb9c65f1b340:
# model-provider-info/src/lib.rs selects chatgpt.com for ChatGPT auth;
# login/src/server.rs and login/src/auth/manager.rs use auth.openai.com.
# Kept identical to the exact hosts in egress.squid.conf; these unauthenticated
# HTTPS probes establish transport reachability, not login or entitlement.
ALLOWED = (
    "chatgpt.com", "auth.openai.com", "sts.us-east-1.amazonaws.com", "ec2.us-east-1.amazonaws.com",
    "rds.us-east-1.amazonaws.com", "ecs.us-east-1.amazonaws.com",
    "dynamodb.us-east-1.amazonaws.com", "sqs.us-east-1.amazonaws.com",
    "cloudformation.us-east-1.amazonaws.com", "s3.us-east-1.amazonaws.com",
    "s3.amazonaws.com", "iam.amazonaws.com",
)
KINDS = {"host", "private", "metadata", "public", "ipv6"}
PRIVATE = tuple(ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
BLOCK_ERRNOS = {errno.EACCES, errno.EPERM}


class InvalidSetup(Exception):
    """Only fixed, nonsensitive diagnostics are emitted."""


def require(condition):
    if not condition:
        raise InvalidSetup("Invalid or incomplete probe setup")


def load_config(path):
    if path == "-":
        raw = sys.stdin.buffer.read(16385)
    else:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            require(stat.S_ISREG(metadata.st_mode) and metadata.st_uid == os.getuid()
                    and not metadata.st_mode & 0o022)
            raw = stream.read(16385)
    require(len(raw) <= 16384)
    return validate_config(json.loads(raw))


def validate_config(config):
    require(isinstance(config, dict) and set(config) == {"proxy_ipv4", "targets"})
    proxy = ipaddress.IPv4Address(config["proxy_ipv4"])
    require(any(proxy in network for network in PRIVATE))
    targets = config["targets"]
    require(isinstance(targets, list) and len(targets) == len(KINDS))
    names, addresses = set(), {proxy}
    for target in targets:
        require(isinstance(target, dict) and set(target) == {"name", "ip", "port"})
        name, address, port = target["name"], ipaddress.ip_address(target["ip"]), target["port"]
        require(name in KINDS and name not in names and address not in addresses)
        require(type(port) is int and 1 <= port <= 65535)
        if name in {"host", "private"}:
            require(address.version == 4 and any(address in network for network in PRIVATE))
        elif name == "metadata":
            require(address.version == 4 and address.is_link_local)
        else:
            require(address.version == (6 if name == "ipv6" else 4) and address.is_global
                    and not address.is_multicast)
        names.add(name)
        addresses.add(address)
    return config


def read_kernel(path):
    with open(path, "r", encoding="ascii") as stream:
        value = stream.read(65537)
    require(len(value) <= 65536)
    return value


def route_snapshot():
    """Read this Linux network namespace; never use host commands or host mounts."""
    v4, v6 = [], []
    rows = read_kernel("/proc/net/route").splitlines()
    require(rows and rows[0].split()[:3] == ["Iface", "Destination", "Gateway"])
    for line in rows[1:]:
        fields = line.split()
        require(len(fields) >= 11)
        if int(fields[3], 16) & 1:
            address = ipaddress.IPv4Address(int.from_bytes(bytes.fromhex(fields[1]), "little"))
            mask = ipaddress.IPv4Address(int.from_bytes(bytes.fromhex(fields[7]), "little"))
            v4.append(str(ipaddress.IPv4Network(f"{address}/{mask}")))
    for line in read_kernel("/proc/net/ipv6_route").splitlines():
        fields = line.split()
        require(len(fields) == 10)
        if int(fields[8], 16) & 1:
            v6.append(str(ipaddress.IPv6Network((int(fields[0], 16), int(fields[1], 16)))))
    # Reading conf/all alone does not establish the state of each interface.
    # https://kernel.org/doc/html/latest/networking/ip-sysctl.html
    interfaces = sorted(path.name for path in Path("/proc/sys/net/ipv6/conf").iterdir())
    require(3 <= len(interfaces) <= 128 and {"all", "default", "lo"} <= set(interfaces))
    settings = {name: read_kernel(f"/proc/sys/net/ipv6/conf/{name}/disable_ipv6").strip()
                for name in interfaces}
    require(all(value in ("0", "1") for value in settings.values()))
    addresses = read_kernel("/proc/net/if_inet6").splitlines()
    disabled = all(value == "1" for value in settings.values()) and not addresses
    return {"ipv4_routes": sorted(v4), "ipv6_routes": sorted(v6), "ipv6_disabled": disabled,
            "ipv6_disable_settings": settings, "ipv6_addresses": addresses}


def no_route(address, routes):
    networks = routes["ipv4_routes" if address.version == 4 else "ipv6_routes"]
    return not any(address in ipaddress.ip_network(network) for network in networks)


def direct_result(error_number, address, routes):
    if error_number is None:
        return "failed", "direct_connection_succeeded"
    if error_number in BLOCK_ERRNOS:
        return "passed", "kernel_permission_denial"
    if error_number == errno.ENETUNREACH and no_route(ipaddress.ip_address(address), routes):
        return "passed", "kernel_network_unreachable_and_no_route"
    settings = routes.get("ipv6_disable_settings")
    if (error_number == errno.EADDRNOTAVAIL and ipaddress.ip_address(address).version == 6
            and routes.get("ipv6_disabled") is True and routes.get("ipv6_addresses") == []
            and routes.get("ipv6_routes") == [] and isinstance(settings, dict)
            and {"all", "default", "lo"} <= set(settings)
            and all(value == "1" for value in settings.values())):
        return "passed", "ipv6_disabled_on_every_interface_without_addresses_or_routes"
    return "inconclusive", "failure_does_not_establish_isolation"


def direct_probe(target, routes):
    address = ipaddress.ip_address(target["ip"])
    try:
        with socket.socket(socket.AF_INET if address.version == 4 else socket.AF_INET6, socket.SOCK_STREAM) as client:
            client.settimeout(TIMEOUT)
            client.connect((str(address), target["port"]))
        error = None
    except OSError as failure:
        error = failure.errno
        # TimeoutError may have errno=None, which must never mean success.
        if error is None:
            error = errno.ETIMEDOUT
    return direct_result(error, str(address), routes)


def http_head(client, deadline):
    data = bytearray()
    while not data.endswith(b"\r\n\r\n"):
        remaining = deadline - time.monotonic()
        require(len(data) < 8192 and remaining > 0)
        client.settimeout(remaining)
        chunk = client.recv(1)
        require(bool(chunk))
        data.extend(chunk)
    lines = bytes(data).decode("ascii").split("\r\n")
    require(re.fullmatch(r"HTTP/1\.[01] [1-5][0-9]{2}(?: .*)?", lines[0]) is not None)
    headers = {}
    for line in lines[1:]:
        if line:
            key, separator, value = line.partition(":")
            require(bool(separator))
            key = key.lower()
            # Repeated ordinary HTTP headers are valid; a duplicate policy-error
            # header is ambiguous and cannot establish the proxy denial.
            require(key != "x-squid-error" or key not in headers)
            headers[key] = value.strip()
    return int(lines[0].split()[1]), headers


def denied_result(status, headers):
    if status == 403 and headers.get("x-squid-error", "").split()[:1] == ["ERR_ACCESS_DENIED"]:
        return "passed", "explicit_proxy_policy_denial"
    if 200 <= status < 300:
        return "failed", "proxy_allowed_forbidden_request"
    return "inconclusive", "no_explicit_proxy_policy_denial"


def proxy_probe(proxy_ip, host, port=443, *, allowed=False, plain_http=False):
    try:
        deadline = time.monotonic() + TIMEOUT
        with socket.create_connection((proxy_ip, 3128), timeout=TIMEOUT) as client:
            method = f"GET http://{host}/ HTTP/1.1" if plain_http else f"CONNECT {host}:{port} HTTP/1.1"
            client.sendall((method + f"\r\nHost: {host}\r\n\r\n").encode("ascii"))
            status, headers = http_head(client, deadline)
            if not allowed:
                return denied_result(status, headers)
            if status != 200:
                return "inconclusive", "approved_tunnel_unavailable"
            require(deadline > time.monotonic())
            client.settimeout(deadline - time.monotonic())
            with ssl.create_default_context().wrap_socket(client, server_hostname=host) as secure:
                secure.sendall(f"HEAD / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode("ascii"))
                status, _ = http_head(secure, deadline)
                require(200 <= status <= 599)
            return "passed", "verified_tls_and_http_without_credentials"
    except (OSError, ValueError, InvalidSetup):
        return "inconclusive", "transport_tls_or_protocol_failure"


def overall(checks):
    if any(check["status"] == "failed" for check in checks):
        return "failed"
    return "passed" if all(check["status"] == "passed" for check in checks) else "inconclusive"


def run_probes(config):
    started = datetime.now(timezone.utc).isoformat()
    routes = route_snapshot()
    checks = []

    def add(name, result):
        checks.append({"name": name, "status": result[0], "detail": result[1]})

    valid_routes = "0.0.0.0/0" not in routes["ipv4_routes"] and "::/0" not in routes["ipv6_routes"] and routes["ipv6_disabled"]
    add("namespace_routes", ("passed" if valid_routes else "failed", "no_default_route_and_ipv6_disabled" if valid_routes else "namespace_configuration_mismatch"))
    for host in ALLOWED:
        add("proxy_allow/" + host, proxy_probe(config["proxy_ipv4"], host, allowed=True))
    for name, host, port, plain in (
        ("unlisted_host", "example.com", 443, False),
        ("other_region", "sts.us-west-2.amazonaws.com", 443, False),
        ("api_key_endpoint", "api.openai.com", 443, False),
        ("unreviewed_auth_subdomain", "unreviewed.auth.openai.com", 443, False),
        ("lookalike_subscription_host", "chatgpt.com.example.com", 443, False),
        ("non_tls_port", "chatgpt.com", 80, False),
        ("plain_http", "chatgpt.com", 80, True),
        ("private_ip", config["proxy_ipv4"], 443, False),
        ("metadata_ip", "169.254.169.254", 443, False),
    ):
        add("proxy_deny/" + name, proxy_probe(config["proxy_ipv4"], host, port, plain_http=plain))
    for target in config["targets"]:
        add("direct/" + target["name"], direct_probe(target, routes))
    add("stable_namespace_routes", ("passed", "route_snapshot_unchanged") if route_snapshot() == routes
        else ("inconclusive", "routes_changed_during_probes"))
    return {"schema_version": 1, "scope": "credential-free-network-paths", "started_at": started,
            "finished_at": datetime.now(timezone.utc).isoformat(), "network_checks_status": overall(checks),
            "activation_ready": False, "proxy_ipv4": config["proxy_ipv4"], "targets": config["targets"],
            "routes": routes, "checks": checks,
            "remaining_activation_gates": [
                "Verify this exact image, namespace, proxy identity/config and launch flags match production.",
                "Prove no arbitrary DNS query escaped via UDP/TCP resolvers using authoritative observation or capture.",
                "Prove external expiry watchdog kills a resistant dummy workload and removes its container; verify cleanup after launcher interruption.",
                "Separately verify AWS role identity, intended read successes and forbidden-read failures after authorized credential handoff."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    try:
        require(sys.platform == "linux" and os.getuid() == 10001)
        forbidden = {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN",
                     "CODEX_API_KEY", "OPENAI_API_KEY", "AWS_WEB_IDENTITY_TOKEN_FILE", "AWS_CONTAINER_CREDENTIALS_FULL_URI",
                     "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"}
        require(not forbidden.intersection(os.environ))
        require(not any(path.exists() for path in (Path("/run/session/credentials"), Path.home() / ".aws", Path.home() / ".codex/auth.json")))
        report = run_probes(load_config(args.config))
        print(json.dumps(report, sort_keys=True))
        return 0 if report["network_checks_status"] == "passed" else 1
    except (OSError, ValueError, TypeError, KeyError, InvalidSetup):
        print(json.dumps({"schema_version": 1, "network_checks_status": "inconclusive", "activation_ready": False,
                          "error": "Invalid setup or unavailable runtime evidence; diagnostics suppressed"}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
