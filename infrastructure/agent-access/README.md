# Deployed agent access foundation

**Deployed and verified on 18 September 2026 at 17:17:45 UTC.** This stack owns
two dedicated IAM Identity Center permission sets and two explicit assignments
in Cambridge TCG. Both assignments use the same verified existing `USER`;
principal IDs stay private. Both named SSO profiles passed live checks by
17:18:32 UTC. The two generated roles bring the account to 135 IAM roles, with
all 133 preexisting role configurations and session ceilings preserved. The
[role map](../../docs/IAM_ROLE_MAP_2026-09-18.md) records that historical baseline.

| Component | Deployed behavior |
| --- | --- |
| `AWSInfraInventory` | Eight named resource-discovery actions; one-hour sessions. Lambda listing is deliberately excluded because it can return environment values. |
| `AWSInfraIAMAudit` | Named IAM metadata/policy reads; one-hour sessions. Access-key IDs and last-use metadata are included, never secret access-key values. No application data access. |
| Both tiers | Explicit deny of every other action, except `sts:GetCallerIdentity`. No role assumption, role passing, deployments, data reads or IAM writes. |
| Assignments | Both tiers assigned to the same existing USER after matching the signed-in SSO administrator. Parameters remain private; no directory users or groups were created. |
| Human admin | Existing `AdministratorAccess` permission set, unchanged. Select explicitly in a trusted human context. |

The account-wide metadata allows use `Resource: "*"`. Inventory has no region
condition because the estate has resources across multiple regions. These
choices are stated scope, not evidence of resource-level isolation. The audit
tier exposes IAM policy/trust details and identity metadata and is therefore a
separate selection from ordinary discovery. Explicit deny prevents additional
grants from expanding these tiers while this policy remains attached; an
administrator can still change it. This is an identity policy, not a permissions
boundary object. [IAM NotAction semantics](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_notaction.html).

## Ownership and deployment boundary

- Source and stack owner: `cambridgetcg/aws-infra`.
- Deployed stack: `aws-infra-agent-access`, account `034362054546`, region `us-east-1`.
- Existing Identity Center instance: `arn:aws:sso:::instance/ssoins-72237658457aa79e`.
- [template.json](template.json) maps only this verified account/region to that
  instance. A different account/region has no mapping entry. Every resource
  resolves through that mapping; deployment must also verify STS first.
- State owner: this named CloudFormation stack. No application
  Terraform or CloudFormation resource is imported or adopted.
- Deployment identity: an explicitly selected human administrator. The inventory
  and audit tiers cannot deploy this stack or change their own permissions.
- Verified access effect: two generated SSO roles after assignment provisioning;
  existing service, workload, deployment and recovery roles remain unchanged.
- No billable compute, storage, scheduled tasks or notifications are added by
  this template. An isolated executor would have separate runtime costs.

AWS manages the generated `AWSReservedSSO_*` roles. Modify permission sets and
assignments through Identity Center, not the generated IAM roles directly.
[SSO role ownership](https://docs.aws.amazon.com/singlesignon/latest/userguide/identity-center-and-iam-roles.html),
[permission-set resource](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-sso-permissionset.html),
[assignment resource](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-sso-assignment.html).

The template's original `PROPOSED` description and `proposed-not-deployed`
metadata are historical preparation markers. The reviewed template bytes were
deployed unchanged; this README records the current live state. Its SHA-256 is
`3732163f9dc714b8299072f5279be42d7b6c1b2f0b0cd185a568650984efc832`.

## Identity and profile setup

The signed-in SSO administrator was matched to the existing directory USER
already common to the Admin, PowerUser and ReadOnly assignments. That USER
received both new tiers. The existing Admin group assignment was not extended
to these tiers. The separate IAM `default` login was not used as proof of SSO
directory identity.

The owner supplied the dual-stack SSO portal URL, now used in
[aws-config.example](aws-config.example) and the three named local profiles.
The original `default` profile was preserved and its configuration backed up
privately before the addition. CLI device-code authorization succeeded; the
human refresh cache remains on the trusted launcher. Verification exported
only the scoped temporary role sessions into memory and did not write or print
their credentials.

## Completed activation and verification

The reviewed CREATE change set
`agent-access-create-20260918T144352157383Z` was executed on
`aws-infra-agent-access` in `us-east-1`. Fresh account and SSO identity checks,
the original template/parameter hashes and exactly four Add actions were
verified first. The resulting stack completed successfully, and its four
resources, assignments, permission documents and generated role identities
were checked against the reviewed inputs.

Both permission sets have `SessionDuration: PT1H`, only the reviewed inline
policy, and no managed-policy attachments. IAM's generated role session ceiling
is a separate setting; the one-hour claim is based on the permission sets and
the exported sessions, not an assumed 3,600-second IAM ceiling.

| Profile | Allowed live read | Denied live read | Session checked |
| --- | --- | --- | --- |
| `cambridge-agent-inventory` | `ec2:DescribeVpcs`: four VPCs in `us-east-1` | `iam:ListRoles` | Temporary `ASIA` credentials; 3,598 seconds remaining; recorded expiry 18:18:15 UTC. |
| `cambridge-iam-audit` | `iam:ListRoles`: 135 roles | `ec2:DescribeVpcs` | Temporary `ASIA` credentials; 3,598 seconds remaining; recorded expiry 18:18:24 UTC. |

Each session matched account `034362054546`, its generated assumed-role ARN and
immutable role ID. Repeated STS checks confirmed the same identity after the
probes. Credential-provider overrides were cleared and each exported session
was pinned for its tests; no broader fallback was used. These were sampled
metadata reads, with no mutation or secret/data-read probes.

At **17:19:40 UTC**, `make inventory-scan` also succeeded under
`cambridge-agent-inventory` for all eight selected collections. Its scope was
seven regional collections in `us-east-1` and global S3 bucket names, with
Lambda explicitly excluded. This establishes the selected collector workflow;
it is not an all-region or all-service inventory.

Private evidence under ignored `inventory/local/`:

- Change-set review: `20260918T144405.768780Z-agent-access-changeset.json`.
- Deployment and preservation checks: `20260918T171745.172227Z-agent-access-execution.json`.
- Profile checks: `20260918T171832.669636Z-agent-profile-verification.json`.
- Restricted collector run: `20260918T171940.627853Z-cambridge-tcg.json`.

The exact principal IDs and raw cloud responses remain outside Git.

## Runtime verification and remaining scope

The dedicated Mac [executor](../agent-executor/README.md) passed its first
isolated inventory task on 19 September. Network/DNS checks, separate subscription
login and cleanup passed; the shared `kingdom-aws` queue subsequently verified
existing-login and worker reuse. See [dated evidence and limits](../../docs/STATUS.md).
Automatic browser-renewal branches have offline tests; actual AWS credential
expiry and abrupt launcher death remain untested. A targeted isolated IAM-audit
task completed at 10:37:56 UTC, reporting matching policies for both agent roles,
account summary and the expected VPC denial, with pinned identity and cleanup.
This samples IAM access; it does not test every permitted action or recheck
Identity Center session settings and assignments.

The runtime receives only one resolved temporary role session. The SSO refresh
token, human profile file, administrator cache and general credential helpers
remain on the trusted launcher. Existing host Codex/OpenClaw processes remain
outside this runtime boundary. Named-project write access remains a separate
scoped addition. Follow [the Mac agent flow](../../docs/MAC_AGENT_FLOW.md) and
[capability map](../../docs/AWS_CAPABILITIES.md).

The repository's `make inventory-plan` and `make inventory-scan` select the
restricted host profile and its eight supported services. A direct collector
scan still defaults to all services, including Lambda, so select the deployed
inventory scope explicitly:

```sh
python3 scripts/aws_inventory.py scan --account cambridge-tcg --profile cambridge-agent-inventory \
  --service ec2 --service vpc --service rds --service ecs \
  --service dynamodb --service sqs --service cloudformation --service s3
```

The isolated executor receives its separate single `task` profile, not the
host's SSO configuration. The earlier
[agent-inventory-read.json](../../policies/agent-inventory-read.json) proposal
includes Lambda and remains unattached; it is not used by this template.

## Recovery

Keep human recovery/admin access throughout migration. If the new tiers are
misconfigured, stop issuing their credentials, correct this stack and verify
again. Removing assignments alone must not be treated as immediate revocation
of already-issued sessions; keep explicit containment until expiry when needed.
Retiring this new stack would remove only its new assignments/permission sets,
never the preserved application or recovery roles. Do not delete the existing
Identity Center instance as a rollback.

Historical role deletion/recreation changes principal IDs and can break existing
trust/resource policies. Rebuilding local profiles does not require deleting
workload roles. [AWS deletion guidance](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_manage_delete.html).

## Validation before deployment

On 18 September at 14:30 UTC, AWS `ValidateTemplate` accepted the template and
Access Analyzer returned no findings for either inline policy. Custom-policy
simulations allowed all eight inventory and 34 IAM audit actions. Each policy
explicitly denied 13 sampled out-of-scope actions, including role assumption,
role passing, deployments, secret/object reads and IAM changes. No such actions
were executed during that simulation; provisioning occurred in the later
reviewed deployment above. The private validation
record is `inventory/local/20260918T143002.853265Z-agent-access-proposal.json`.

Offline tests guard the account/region mapping, required explicit assignments,
session duration, absence of broad managed-policy attachments, deny exceptions
and profile separation. Live activation, sampled profile checks and the isolated
inventory flow are verified. Their dated scope and remaining limits are recorded
in [current status](../../docs/STATUS.md).
