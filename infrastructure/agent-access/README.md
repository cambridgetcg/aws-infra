# Proposed agent access foundation

**Change set prepared; not executed.** The named local profiles are configured,
but their SSO authentication and restricted roles remain pending. This stack adds two dedicated
IAM Identity Center permission sets and two explicit assignments in Cambridge
TCG. It does not replace the 133 existing roles. The [role map](../../docs/IAM_ROLE_MAP_2026-09-18.md)
shows why workload migration must precede any further retirement.

| Component | Proposed behavior |
| --- | --- |
| `AWSInfraInventory` | Eight named resource-discovery actions; one-hour sessions. Lambda listing is deliberately excluded because it can return environment values. |
| `AWSInfraIAMAudit` | Named IAM metadata/policy reads; one-hour sessions. Access-key IDs and last-use metadata are included, never secret access-key values. No application data access. |
| Both tiers | Explicit deny of every other action, except `sts:GetCallerIdentity`. No role assumption, role passing, deployments, data reads or IAM writes. |
| Assignments | Separate required principal ID/type parameters for each tier. No default user/group and no directory changes. |
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

- Source and future stack owner: `cambridgetcg/aws-infra`.
- Proposed stack: `aws-infra-agent-access`, account `034362054546`, region `us-east-1`.
- Existing Identity Center instance: `arn:aws:sso:::instance/ssoins-72237658457aa79e`.
- [template.json](template.json) maps only this verified account/region to that
  instance. A different account/region has no mapping entry. Every resource
  resolves through that mapping; deployment must also verify STS first.
- State owner after deployment: this named CloudFormation stack. No application
  Terraform or CloudFormation resource is imported or adopted.
- Deployment identity: an explicitly selected human administrator. The inventory
  and audit tiers cannot deploy this stack or change their own permissions.
- Expected access effect: two generated SSO roles after assignment provisioning;
  existing service, workload, deployment and recovery roles remain.
- No billable compute, storage, scheduled tasks or notifications are added by
  this template. An isolated executor would have separate runtime costs.

AWS manages the generated `AWSReservedSSO_*` roles. Modify permission sets and
assignments through Identity Center, not the generated IAM roles directly.
[SSO role ownership](https://docs.aws.amazon.com/singlesignon/latest/userguide/identity-center-and-iam-roles.html),
[permission-set resource](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-sso-permissionset.html),
[assignment resource](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-sso-assignment.html).

## Inputs still needed

The current login uses IAM user `YuCheung`; it is not proof of the identity of an
SSO directory user. The existing Admin permission set has one user and one group
assignment. Select the intended existing principal for each new tier; do not
infer its identity from an opaque ID or silently grant a whole group.

The owner supplied the dual-stack SSO portal URL, now used in
[aws-config.example](aws-config.example) and the three named local profiles.
The original `default` profile was preserved and its configuration backed up
privately before the addition. SSO sign-in is pending; no credential cache was
copied or exported.

## Activation and verification

The prepared CREATE change set is
`agent-access-create-20260918T144352157383Z` on `aws-infra-agent-access` in
`us-east-1`. At 14:44 UTC it was `CREATE_COMPLETE` / `AVAILABLE`; the stack was
`REVIEW_IN_PROGRESS`, with no resources provisioned. Exactly four Add actions,
the template hash and the private candidate parameter hash were verified.
The candidate is the single existing USER common to Admin, PowerUser and
ReadOnly assignments; its identity remains unconfirmed until the SSO sign-in
is matched. Do not execute this preview merely because it exists.

Private review evidence:
`inventory/local/20260918T144405.768780Z-agent-access-changeset.json`.
The exact change-set ARN and parameter IDs are retained there, outside Git.

1. Confirm the intended SSO principal(s), portal URL, default agent tier and
   isolated runtime. Save exact parameter values privately outside Git.
2. Verify STS against Cambridge TCG and check the two proposed permission-set
   names are still unused. Review a CloudFormation change set showing only the
   two new permission sets and two new assignments, then execute that change.
3. Check provisioning/assignments and the generated roles. Their only grants
   should be the intended inline policy, with a one-hour session duration.
4. Merge the named entries from [aws-config.example](aws-config.example) into the
   **human launcher's** configuration, preserving its current login. Complete
   `aws sso login --profile cambridge-agent-inventory` and verify the actual
   assumed-role ARN/account. The local profile names alone do not prove scope.
5. Give the isolated executor only one resolved temporary role session. No SSO
   refresh token, human profile file, admin cache or general credential helper.
   Follow [the agent flow](../../docs/ACCESS_REBUILD.md).
6. Run a permitted discovery call with the new credentials; verify restrictions,
   runtime isolation and expiry. Cloud policy simulation alone does not establish
   the actual role's complete effective permissions or runtime isolation.

The collector's default scan includes Lambda. With the proposed inventory tier,
select its supported services explicitly:

```sh
python3 scripts/aws_inventory.py scan --account cambridge-tcg --profile task \
  --service ec2 --service vpc --service rds --service ecs \
  --service dynamodb --service sqs --service cloudformation --service s3
```

`task` is the proposed single-profile configuration inside the isolated executor,
not a profile currently installed on this host. The earlier
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

## Validation of this proposal

On 18 September at 14:30 UTC, AWS `ValidateTemplate` accepted the template and
Access Analyzer returned no findings for either inline policy. Custom-policy
simulations allowed all eight inventory and 34 IAM audit actions. Each policy
explicitly denied 13 sampled out-of-scope actions, including role assumption,
role passing, deployments, secret/object reads and IAM changes. No such actions
were executed, and no permission sets were created. The private validation
record is `inventory/local/20260918T143002.853265Z-agent-access-proposal.json`.

Offline tests guard the account/region mapping, required explicit assignments,
session duration, absence of broad managed-policy attachments, deny exceptions
and profile separation. These checks do not substitute for the live activation
and isolation checks above.
