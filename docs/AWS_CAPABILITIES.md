# What the AWS agent can access

The isolated agent has **selected read access, not access to every AWS resource**.
It defaults to inventory in Cambridge TCG (`034362054546`). IAM review is a
separate explicit tier. Neither tier can configure, deploy or delete resources.

**19 September 2026: inventory and targeted agent-role checks completed.**
The inventory task completed at 10:26:00 UTC, and a targeted IAM task completed
at 10:37:56 UTC. Their model-returned reports supplied the counts, policy
comparisons and sampled permission denials below; the wrapper verified each
tier's identity and cleanup. Later policy reads inspected the human SSO
administrator role, human IAM user and legacy OpenClaw user. These identities
were not used to perform operations. All times here are UTC.

## Read scope

Use [the shared `kingdom-aws` command](MAC_AGENT_FLOW.md). Inventory is the default;
an explicitly requested IAM review selects `--tier iam-audit`.

| Resource group | Configured inventory access | Model-reported count | Outside that grant |
| --- | --- | --- | --- |
| EC2 instances | `ec2:DescribeInstances`: instance metadata | 1 instance | Instance changes, user data and console output |
| VPCs | `ec2:DescribeVpcs`: VPC metadata | 4 VPCs | Subnet/security-group enumeration and network changes |
| RDS | `rds:DescribeDBInstances`: database-instance metadata | 3 instances | Database contents, SQL access and configuration changes |
| ECS | `ecs:ListClusters`: cluster identifiers | 0 clusters | Services, task definitions, task contents and deployments |
| DynamoDB | `dynamodb:ListTables`: table names | 17 tables | Table items, queries, scans and writes |
| SQS | `sqs:ListQueues`: queue URLs | 12 queues | Receiving messages, queue attributes and changes |
| CloudFormation | `cloudformation:ListStacks`: stack summaries | 32 summaries; may include retained deleted stacks | Templates, parameters, outputs and stack changes |
| S3 | `s3:ListAllMyBuckets`: account bucket listing | 63 buckets | Object listings, object contents and bucket/object changes |

These are eight named API actions, plus identity verification with
`sts:GetCallerIdentity`. Selected metadata can include names, tags and network
properties; “read-only” does not mean every returned field is public.
Regional counts cover `us-east-1`; the S3 count is account-wide. Zero ECS
clusters does not establish that task definitions or other ECS resources are
absent. The CloudFormation count is not a count of currently deployed stacks.

| IAM audit group | Configured reads |
| --- | --- |
| Account | Summary, password policy and authorization details |
| Roles and instance profiles | Names, role/trust documents, inline policies, attached-policy references and profiles |
| Managed policies | Policy documents, versions and attached entities |
| Users and groups | Identity metadata, membership and policy details |
| MFA and access keys | Device/key identifiers and last-use metadata; no secret access-key values |
| Federation | OIDC and SAML provider metadata/documents |

The audit tier contains **34 named IAM Get/List actions**, plus identity
verification. Its exact action list is in the
[deployed template](../infrastructure/agent-access/template.json). Inventory does
not include these IAM reads; IAM audit does not include inventory's resource reads.
Identity Center assignments, Organizations, CloudTrail, billing and other AWS
services are outside both tiers.

The targeted IAM report covered 12 calls, with no reported failures and identity
checks before and after. Account summary reported **135 roles and 8 users**.
Both agent roles matched their pinned IDs and expected inline policies; each
had one inline policy, no attached managed policies and no permissions boundary.
The IAM-audit role was denied `ec2:DescribeVpcs` with `UnauthorizedOperation`.
This samples the audit tier; it does not exercise all 34 permitted actions.

## Configure scope and application data

**Configured project-write access: none.** Both policies explicitly deny every
action outside their named read list and `sts:GetCallerIdentity`. That includes
resource creation/deletion, tag changes, deployments, IAM changes, `iam:PassRole`
and `sts:AssumeRole`. An explicit deny overrides an applicable allow while the
deny remains in effect; a privileged administrator can still change the policy.
This is an identity-policy restriction, not an IAM permissions-boundary object.
[AWS policy evaluation](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html).

Application-data APIs are outside the allowed lists: for example S3 object reads,
DynamoDB item reads, SQS message reads, Secrets Manager secret values, SSM
parameters and CloudWatch log contents. Lambda listing/configuration is also
excluded. Those contents/configurations are outside this capability check;
their exclusion does not establish that resources are absent. The earlier
[inventory-policy proposal](../policies/agent-inventory-read.json), which includes
Lambda, remains unattached and is not the source of deployed permissions.

Configuring a named project needs a separately reviewed, scoped write identity
and the owning repository's deployment workflow. No broader profile is selected
automatically when a read is denied.

## Account, region and network limits

| Layer | Current configured boundary |
| --- | --- |
| Identity | Cambridge account and the two exact SSO role identities are pinned; a mismatch stops execution. No other-account role is configured. |
| IAM policy | Account-wide named reads use `Resource: "*"`. Inventory has no IAM region condition. Both permission sets issue one-hour sessions. |
| Isolated network | Exact AWS endpoints for STS, EC2, RDS, ECS, DynamoDB, SQS and CloudFormation in `us-east-1`; global IAM and global/`us-east-1` S3 endpoints. |
| Other endpoints | Other regional/service endpoints are not on the proxy allowlist. Endpoint reachability does not itself grant any AWS API permission. |

The fresh role report showed each IAM role's `MaxSessionDuration` as 43,200
seconds (12 hours). That role ceiling is separate from the one-hour Identity
Center permission-set setting and issued task sessions. The latest IAM probe
did not recheck Identity Center session settings or assignments.

Consequently, the isolated runtime can use the listed regional inventory APIs
in `us-east-1`; IAM metadata and S3 bucket listing are account-wide. This is not
an all-region estate scan. The source is the
[proxy policy](../infrastructure/agent-executor/egress.squid.conf); runtime checks
also verify the actual proxy, network and configuration identities.

The current host Codex/OpenClaw processes remain outside this boundary. Separate
policy reports completed at 10:45:16 and 10:51:51 UTC with these findings:

| Separate identity | Model-reported policy scope | What this does not establish |
| --- | --- | --- |
| Human SSO administrator role | One matching role with managed `AdministratorAccess`: unconditional `Allow`, `Action: "*"`, `Resource: "*"`; no permissions boundary observed | Identity Center assignment, a fresh administrator login or effective access to every resource/account |
| Legacy `openclaw-agent` IAM user | Inline `OpenClawAgentPolicy` permits EC2 start/stop/reboot, security-group ingress authorization/revocation and Elastic IP allocation/association, plus describe/self-IAM/STS reads. EC2 grants use `Resource: "*"` without conditions; no groups, boundary or explicit deny reported | Current key status, credential possession/use, MFA or a live write test |
| Human IAM user `YuCheung` | Managed `AdministratorAccess` grants unconditional `Action: "*"`, `Resource: "*"`; no explicit identity-policy deny, boundary or groups reported. Additional `RDSCardforum-IAMConnect` grants `rds-db:connect` to one limited resource; it does not narrow the administrator grant | A fresh login, current keys/MFA, effective access to every resource/account or a successful database connection |

The human administrator and legacy policies are broader than the isolated agent
tiers; none of these identities is selected by those tiers or used as a fallback. These are
policy inspections under the audit role, not operations performed using the
broader identities. Key/MFA observations in the
[earlier IAM review](IAM_REVIEW_2026-09-17.md) remain dated to that review.

## What has been checked

| Evidence | Status and limits |
| --- | --- |
| Policy source and current role comparison | Eight inventory actions and 34 IAM audit actions, with explicit deny outside each tier. The targeted IAM report matched both current role inline policies to the expected source and found no extra inline/managed policies or boundary. One-hour permission-set settings come from the earlier deployment verification. |
| Earlier host profile tests | On 18 September, inventory VPC reads passed and IAM role listing was denied; IAM audit role listing passed and VPC reads were denied. All eight selected inventory collections also passed in `us-east-1`/global S3. |
| Isolated inventory workflow | On 19 September, the runner and shared queue passed inventory tasks with pinned identity and successful cleanup. The model reported four VPCs and expected IAM denial. |
| Fresh inventory capability probe | Completed at 10:26:00.426433. The model reported all eight reads allowed, `iam:ListRoles` denied with `AccessDenied`, and `ec2:DescribeSecurityGroups` plus `ec2:CreateTags --dry-run` denied with `UnauthorizedOperation`. The wrapper confirmed the pinned inventory identity and post-task checks. No actual resource write was requested. |
| Fresh targeted IAM capability/policy probe | Completed at 10:37:56.219221 with pinned IAM-audit identity and cleanup. Its report covered 12 calls, the two agent-role policy comparisons, account summary and expected VPC denial. Earlier empty/unusable reports provided no policy evidence; see [status](STATUS.md). |
| Separate human/legacy policy inspection | The 10:45:16.494257 report supplied SSO administrator-role and legacy-user findings. A focused human IAM-user follow-up completed at 10:51:51.911421, reporting 10 calls, no failures and valid identity before/after. It resolved the earlier response-parser failure. Assignments, keys, MFA, database connectivity and broader-identity use were not tested. |
| Other services, regions, accounts and application data | Not scanned by this capability check. Denied or untested access is not evidence that resources are absent. |

EC2 `CreateTags --dry-run` checks permission without creating tags. The reported
denial supports the sampled write restriction; no real configuration change was
performed or tested.
[AWS dry-run behavior](https://docs.aws.amazon.com/cli/latest/reference/ec2/create-tags.html).

The executor verifies the task's AWS identity and bounds/redacts its result.
Per-command outcomes returned by the model are reported observations, not raw
API attestation. Policy inspection and sampled reads are useful evidence, but
neither proves every possible effective permission. Dated results and private
evidence references belong in [current status](STATUS.md). The reviewed private
summary is `inventory/local/20260919-access-capability-verification.json`.
