"""Offline classification tests. No sockets, Docker, AWS, or credential reads."""

import errno
import importlib.util
import io
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import MagicMock, patch


SPEC = importlib.util.spec_from_file_location("probe_network", Path(__file__).resolve().parents[1] / "infrastructure/agent-executor/probe_network.py")
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class ProbeNetworkTests(unittest.TestCase):
    def setUp(self):
        self.routes = {"ipv4_routes": ["172.30.0.0/24"], "ipv6_routes": [], "ipv6_disabled": True}
        self.config = {"proxy_ipv4": "172.30.0.2", "targets": [
            {"name": "host", "ip": "192.168.20.1", "port": 443},
            {"name": "private", "ip": "10.12.0.1", "port": 443},
            {"name": "metadata", "ip": "169.254.169.254", "port": 80},
            {"name": "public", "ip": "1.1.1.1", "port": 443},
            {"name": "ipv6", "ip": "2606:4700:4700::1111", "port": 443},
        ]}

    def test_subscription_hosts_are_exact_and_match_proxy_policy(self):
        policy = Path(SPEC.origin).with_name("egress.squid.conf").read_text()
        policy_hosts = {host for line in policy.splitlines()
                        if line.startswith("acl task_hosts dstdomain ") for host in line.split()[4:]}
        self.assertEqual(policy_hosts, set(probe.ALLOWED))
        self.assertEqual({host for host in policy_hosts if not host.endswith(".amazonaws.com")},
                         {"chatgpt.com", "auth.openai.com"})
        self.assertFalse(any(host.startswith(".") or "*" in host for host in policy_hosts))

    def test_proxy_rejects_unlisted_names_before_dns_dependent_acl(self):
        lines = Path(SPEC.origin).with_name("egress.squid.conf").read_text().splitlines()
        host_acls = [line.split() for line in lines if line.startswith("acl task_hosts ")]
        self.assertTrue(host_acls)
        self.assertTrue(all(parts[2:4] == ["dstdomain", "-n"] for parts in host_acls))
        rules = [line for line in lines if line.startswith("http_access ")]
        self.assertLess(rules.index("http_access deny !task_hosts"), rules.index("http_access deny private_dst"))
        self.assertLess(rules.index("http_access deny private_dst"), rules.index("http_access allow task_hosts"))
        self.assertEqual(rules[-1], "http_access deny all")

    def test_subscription_negative_probes_include_api_and_unreviewed_domains(self):
        with patch.object(probe, "route_snapshot", return_value=self.routes), \
                patch.object(probe, "proxy_probe", return_value=("passed", "fixture")) as proxy_call, \
                patch.object(probe, "direct_probe", return_value=("passed", "fixture")):
            probe.run_probes(self.config)
        negative = {call.args[1] for call in proxy_call.call_args_list if not call.kwargs.get("allowed")}
        self.assertTrue({"api.openai.com", "unreviewed.auth.openai.com", "chatgpt.com.example.com"} <= negative)

    def test_refusal_timeout_and_arp_failure_cannot_prove_isolation(self):
        for code in (errno.ECONNREFUSED, errno.ETIMEDOUT, errno.EHOSTUNREACH, errno.EAFNOSUPPORT):
            with self.subTest(code=code):
                self.assertEqual(probe.direct_result(code, "1.1.1.1", self.routes)[0], "inconclusive")

    def test_no_route_requires_both_kernel_error_and_route_evidence(self):
        self.assertEqual(probe.direct_result(errno.ENETUNREACH, "1.1.1.1", self.routes)[0], "passed")
        self.assertEqual(probe.direct_result(errno.ENETUNREACH, "172.30.0.3", self.routes)[0], "inconclusive")
        routes = dict(self.routes, ipv4_routes=["0.0.0.0/0"])
        self.assertEqual(probe.direct_result(errno.ENETUNREACH, "1.1.1.1", routes)[0], "inconclusive")

    def test_success_fails_and_explicit_permission_denial_passes(self):
        self.assertEqual(probe.direct_result(None, "1.1.1.1", self.routes)[0], "failed")
        self.assertEqual(probe.direct_result(errno.EACCES, "1.1.1.1", self.routes)[0], "passed")

    def test_timeout_without_errno_is_never_connection_success(self):
        client = MagicMock()
        client.__enter__.return_value.connect.side_effect = socket.timeout()
        with patch.object(probe.socket, "socket", return_value=client):
            self.assertEqual(probe.direct_probe(self.config["targets"][3], self.routes)[0], "inconclusive")

    def test_proxy_header_slow_stream_has_absolute_deadline(self):
        client = MagicMock()
        client.recv.return_value = b"H"
        with patch.object(probe.time, "monotonic", side_effect=[1, 2, 4]):
            with self.assertRaises(probe.InvalidSetup):
                probe.http_head(client, 3)
        self.assertEqual(client.recv.call_count, 2)

    def test_proxy_errors_and_generic_403_are_not_policy_evidence(self):
        for status in (403, 407, 500, 502, 503):
            self.assertEqual(probe.denied_result(status, {})[0], "inconclusive")
        self.assertEqual(probe.denied_result(403, {"x-squid-error": "ERR_ACCESS_DENIED 0"})[0], "passed")
        self.assertEqual(probe.denied_result(200, {})[0], "failed")

    def test_invalid_target_and_proxy_substitution_are_rejected(self):
        self.assertEqual(probe.validate_config(self.config), self.config)
        for bad in ("127.0.0.1", "192.0.2.1", "224.0.0.1", "172.30.0.2"):
            self.config["targets"][3]["ip"] = bad
            with self.subTest(ip=bad), self.assertRaises(probe.InvalidSetup):
                probe.validate_config(self.config)

    def test_missing_target_class_is_rejected(self):
        self.config["targets"] = self.config["targets"][:-1]
        with self.assertRaises(probe.InvalidSetup):
            probe.validate_config(self.config)

    def test_stdin_config_is_bounded_and_validated_without_host_mount(self):
        stream = MagicMock(buffer=io.BytesIO(json.dumps(self.config).encode()))
        with patch.object(probe.sys, "stdin", stream):
            self.assertEqual(probe.load_config("-"), self.config)
        stream = MagicMock(buffer=io.BytesIO(b" " * 16385))
        with patch.object(probe.sys, "stdin", stream), self.assertRaises(probe.InvalidSetup):
            probe.load_config("-")

    def test_kernel_routes_are_decoded_in_correct_byte_order(self):
        files = {
            "/proc/net/route": "Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT\neth0 00001EAC 00000000 0001 0 0 0 00FFFFFF 0 0 0\n",
            "/proc/net/ipv6_route": "",
            "/proc/sys/net/ipv6/conf/all/disable_ipv6": "1\n",
            "/proc/sys/net/ipv6/conf/default/disable_ipv6": "1\n",
        }
        with patch.object(probe, "read_kernel", side_effect=files.__getitem__):
            self.assertEqual(probe.route_snapshot(), self.routes)

    def test_route_drift_and_failed_positive_control_prevent_pass(self):
        passing = ("passed", "fixture")
        with patch.object(probe, "route_snapshot", side_effect=[self.routes, dict(self.routes, ipv4_routes=[])]), \
                patch.object(probe, "proxy_probe", return_value=passing), \
                patch.object(probe, "direct_probe", return_value=passing):
            report = probe.run_probes(self.config)
            self.assertEqual(report["network_checks_status"], "inconclusive")
            self.assertFalse(report["activation_ready"])
        with patch.object(probe, "route_snapshot", return_value=self.routes), \
                patch.object(probe, "proxy_probe", return_value=("inconclusive", "fixture")), \
                patch.object(probe, "direct_probe", return_value=passing):
            self.assertEqual(probe.run_probes(self.config)["network_checks_status"], "inconclusive")

    def test_network_pass_never_claims_activation_or_expiry_dns_verification(self):
        passing = ("passed", "fixture")
        with patch.object(probe, "route_snapshot", return_value=self.routes), \
                patch.object(probe, "proxy_probe", return_value=passing), \
                patch.object(probe, "direct_probe", return_value=passing):
            report = probe.run_probes(self.config)
        self.assertEqual(report["network_checks_status"], "passed")
        self.assertFalse(report["activation_ready"])
        self.assertEqual(len(report["remaining_activation_gates"]), 4)


if __name__ == "__main__":
    unittest.main()
