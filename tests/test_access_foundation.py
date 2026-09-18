"""Security invariants for the proposed access foundation; no AWS credentials."""

import configparser
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_ACTIONS = {
    "ec2:DescribeInstances", "ec2:DescribeVpcs", "rds:DescribeDBInstances",
    "ecs:ListClusters", "dynamodb:ListTables", "sqs:ListQueues",
    "cloudformation:ListStacks", "s3:ListAllMyBuckets",
}
FORBIDDEN = {
    "iam:CreateUser", "iam:PassRole", "iam:DeleteRole",
    "sso:CreateAccountAssignment", "sts:AssumeRole",
    "sts:AssumeRoleWithWebIdentity", "secretsmanager:GetSecretValue",
    "ssm:GetParameter", "s3:GetObject", "s3:PutObject",
    "ec2:TerminateInstances", "lambda:ListFunctions", "kms:Decrypt",
}


class AccessFoundationTests(unittest.TestCase):
    def setUp(self):
        self.template = json.loads((ROOT / "infrastructure/agent-access/template.json").read_text())

    def test_foundation_only_adds_explicit_sso_access(self):
        resources = self.template["Resources"]
        self.assertEqual(len(resources), 4)
        for tier in ("Inventory", "IAMAudit"):
            permission_set = resources[tier + "PermissionSet"]
            self.assertEqual(permission_set["Type"], "AWS::SSO::PermissionSet")
            properties = permission_set["Properties"]
            self.assertEqual(properties["SessionDuration"], "PT1H")
            self.assertFalse(properties.get("ManagedPolicies"))
            self.assertFalse(properties.get("CustomerManagedPolicyReferences"))
            assignment = resources[tier + "Assignment"]
            self.assertEqual(assignment["Type"], "AWS::SSO::Assignment")
            self.assertEqual(assignment["Properties"]["TargetId"], {"Ref": "AWS::AccountId"})
            for suffix in ("PrincipalId", "PrincipalType"):
                parameter = tier + suffix
                self.assertNotIn("Default", self.template["Parameters"][parameter])
                self.assertEqual(assignment["Properties"][suffix], {"Ref": parameter})

    def test_unapproved_account_and_region_have_no_fallback_mapping(self):
        mappings = self.template["Mappings"]
        self.assertEqual(set(mappings["ApprovedControlPlane"]), {"034362054546"})
        self.assertEqual(set(mappings["ApprovedRegions"]), {"us-east-1"})
        instance = {"Fn::FindInMap": [
            "ApprovedControlPlane", {"Ref": "AWS::AccountId"},
            {"Fn::FindInMap": ["ApprovedRegions", {"Ref": "AWS::Region"}, "InstanceAttribute"]},
        ]}
        for resource in self.template["Resources"].values():
            self.assertEqual(resource["Properties"]["InstanceArn"], instance)

    def test_named_reads_have_an_explicit_deny_ceiling(self):
        for tier in ("Inventory", "IAMAudit"):
            policy = self.template["Resources"][tier + "PermissionSet"]["Properties"]["InlinePolicy"]
            self.assertEqual(policy["Version"], "2012-10-17")
            self.assertEqual(len(policy["Statement"]), 2)
            allow, deny = policy["Statement"]
            self.assertEqual(allow["Effect"], "Allow")
            self.assertEqual(deny["Effect"], "Deny")
            self.assertEqual(deny["Resource"], "*")
            actions = set(allow["Action"])
            exceptions = set(deny["NotAction"])
            self.assertEqual(exceptions, actions | {"sts:GetCallerIdentity"})
            self.assertTrue(all("*" not in action and "?" not in action for action in exceptions))
            self.assertTrue(exceptions.isdisjoint(FORBIDDEN))
            if tier == "Inventory":
                self.assertEqual(actions, INVENTORY_ACTIONS)
            else:
                self.assertTrue(all(action.startswith(("iam:Get", "iam:List")) for action in actions))

    def test_profile_example_keeps_broker_and_executor_separate(self):
        config = configparser.ConfigParser()
        config.read(ROOT / "infrastructure/agent-access/aws-config.example")
        self.assertNotIn("default", config.sections())
        self.assertNotIn("profile task", config.sections())
        self.assertEqual(config["sso-session cambridge-human"]["sso_start_url"],
                         "https://ssoins-72237658457aa79e.portal.us-east-1.app.aws")
        for name, permission_set in (("cambridge-agent-inventory", "AWSInfraInventory"),
                                     ("cambridge-iam-audit", "AWSInfraIAMAudit")):
            profile = config["profile " + name]
            self.assertEqual(profile["sso_account_id"], "034362054546")
            self.assertEqual(profile["sso_role_name"], permission_set)
            self.assertEqual(profile["sso_session"], "cambridge-human")
            self.assertTrue(set(profile).isdisjoint({"credential_process", "source_profile",
                                                   "aws_access_key_id", "aws_secret_access_key"}))


if __name__ == "__main__":
    unittest.main()
