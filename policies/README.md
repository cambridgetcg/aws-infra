# Proposed inventory permissions

For the two **applied** Captioneer quarantine documents, see the final section
and [containment record](../docs/CAPTIONEER_CLEANUP.md). The inventory and
staging/main allow policies below remain proposals.

[agent-inventory-read.json](agent-inventory-read.json) is a **proposed, unattached
identity permissions policy**, reviewed against the AWS documentation on
17 September 2026. Creating this file grants no access. AWS Access Analyzer
validation returned no findings; a custom-policy simulation allowed its nine
actions and implicitly denied nine sampled data/secret reads, role operations
and EC2 mutations. It has not been attached to an identity or verified through
service calls made with a restricted role. Simulation is not proof of a
principal's complete effective access.

The policy contains the nine service actions used by the current
[collector](../scripts/aws_inventory.py), with no action wildcards. It grants no
IAM administration or IAM listing, Secrets Manager/Parameter Store/KMS calls,
object or database data reads, queue message reads, writes, `iam:PassRole`, or
`sts:AssumeRole`. Lambda listing has a material configuration-read limitation
described below.

This is not a trust policy, session policy, permissions boundary, SCP, or a
complete ceiling on an identity's effective permissions. Attaching it to a
principal that already has broader grants does not remove those grants. IAM
evaluates the other applicable policies and explicit denies as well. Choose a
dedicated identity and review its effective access separately.
[AWS policy evaluation](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html)
explains how these policy types combine.

## Actions and resource scope

The following resource and condition support is from each service's current
Service Authorization Reference. A blank resource-type entry means an action
cannot be restricted using individual resource ARNs; its allow statement needs
`"Resource": "*"`. This does not turn it into an action wildcard. Applicable
global IAM condition keys are separate from the service-specific keys below.

| Collector command | Permission | Resource and condition support |
| --- | --- | --- |
| `ec2 describe-instances`, `ec2 describe-vpcs` | `ec2:DescribeInstances`, `ec2:DescribeVpcs` | No resource ARN support. Both support `ec2:Region`. [EC2 reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ec2.html). |
| `lambda list-functions` | `lambda:ListFunctions` | No resource ARN or action-specific condition keys listed. [Lambda reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_lambda.html). |
| `rds describe-db-instances` | `rds:DescribeDBInstances` | Supports optional `db` resources and RDS resource/tag condition keys; see the discovery tradeoff below. [RDS reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_rds.html). |
| `ecs list-clusters` | `ecs:ListClusters` | No resource ARN or action-specific condition keys listed. [ECS reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ecs.html). |
| `dynamodb list-tables` | `dynamodb:ListTables` | No resource ARN or action-specific condition keys listed. [DynamoDB reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_dynamodb.html). |
| `sqs list-queues` | `sqs:ListQueues` | No resource ARN or action-specific condition keys listed. [SQS reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_sqs.html). |
| `cloudformation list-stacks` | `cloudformation:ListStacks` | No resource ARN or action-specific condition keys listed. [CloudFormation reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_cloudformation.html). |
| `s3api list-buckets` | `s3:ListAllMyBuckets` | No resource ARN support. Lists account, authentication, signature and TLS condition keys; no per-bucket list filter through resource ARNs. [S3 reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_s3.html). |

**RDS is the exception to the no-resource-ARN rule.** This proposal uses `*`
for its current unfiltered regional discovery call because the inventory of
target DBs is not yet established. That is a deliberate discovery scope, not a
claim that RDS lacks resource permissions. AWS documents `db` ARN and tag
scoping; evaluate a narrower policy with the intended request shape before
deploying access for a known set of DBs. No live test here establishes whether
a proposed narrower policy covers this collector's unfiltered call.
[RDS IAM support](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/security_iam_service-with-iam.html),
[DescribeDBInstances request parameters](https://docs.aws.amazon.com/AmazonRDS/latest/APIReference/API_DescribeDBInstances.html).

The collector also calls `sts:GetCallerIdentity`. AWS requires no permission
grant for that operation, so this policy omits an unnecessary allow statement.
It still needs usable credentials. See
[GetCallerIdentity](https://docs.aws.amazon.com/STS/latest/APIReference/API_GetCallerIdentity.html).

## Lambda listing can return environment values

`lambda:ListFunctions` permits an API response whose schema includes
`Environment.Variables`. The CLI's `--query` filters the complete response
**locally after receipt**. The collector then applies a second field projection
before retaining resources. These projections limit saved inventory; they do
not prevent the CLI process from receiving configuration or secret-bearing
environment values, and are not a field-level IAM permission boundary.
[Lambda ListFunctions response](https://docs.aws.amazon.com/lambda/latest/api/API_ListFunctions.html),
[AWS CLI client-side filtering](https://docs.aws.amazon.com/cli/latest/userguide/cli-usage-filter.html).

The separate Lambda statement makes that grant easy to review or remove. If
environment values must never reach the CLI, omit Lambda from collection and
remove this grant before attaching the policy. Omitting Lambda from one command
alone does not revoke an identity's existing Lambda permission.

## Account and region selection

The proposal includes no region condition. A collector run selects an account
and region set explicitly or uses the candidate defaults in
[accounts.json](../config/accounts.json). It verifies the selected account with
STS before resource collection. Those software choices do not restrict where a
holder of the same AWS credentials can use the allowed actions independently.
This policy does not grant cross-account role assumption or create an identity
in either documented account; each identity's actual account and existing
access mechanism still matter.

For a later region restriction, use a reviewed condition on the regional
statement and the Lambda statement, matched to the approved regions. The global
S3 listing needs separate treatment: its endpoint region does not limit bucket
names to that region. `aws:RequestedRegion` controls the endpoint invoked, not
necessarily every region affected or represented by the operation. No such
restriction is deployed or implied by this proposal.
[AWS requested-region condition](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html#condition-keys-requestedregion).

Profiles, credential helpers, configured endpoints and the local AWS CLI remain
trusted components. Offline tests verify collector decisions and retained
output. They do not prove effective IAM restrictions or server-side response
redaction. Follow [access setup](../docs/ACCESS.md) and
[operations](../docs/OPERATIONS.md) when reviewing an actual identity and scope.

## Proposed Captioneer staging trust repair

[captioneer-staging-github-trust.json](captioneer-staging-github-trust.json) is
a proposed complete trust policy for the existing
`captioneer-staging-github-terraform` and `captioneer-staging-github-deploy`
roles in Cambridge TCG. It replaces globally matching repository subjects with
the exact Captioneer staging-environment subject, `aud=sts.amazonaws.com`, and
`ref=refs/heads/main`. It grants only web-identity assumption through the existing
GitHub provider; it does not change either role's attached permission policies.

The [dated IAM review](../docs/IAM_REVIEW_2026-09-17.md) records live evidence,
the archived source owner, current environment-protection gaps and the change's
compatibility limits. Current AWS documentation supports the
[GitHub ref condition](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_iam-condition-keys.html).
Keep this restriction paired with a protected main-only GitHub staging environment.
PR planning and other environments need their own reviewed access. No trust,
role, GitHub environment or original source file has been changed.

AWS Access Analyzer validated the final trust document with **zero errors and
zero warnings**. It returned one `CONFIRM_AUDIENCE_CLAIM_TYPE` suggestion: audience
is single-valued and must not use a set qualifier. The proposal uses plain
`StringEquals`, with no set qualifier. Adding the explicit `ref` condition
resolved the earlier repository/branch warning. This validation does not assume
the role, test a real GitHub token, or prove that a workflow can deploy.

## Applied Captioneer quarantine

[captioneer-quarantine-permissions.json](captioneer-quarantine-permissions.json)
and [captioneer-quarantine-trust.json](captioneer-quarantine-trust.json) were
applied to exactly `captioneer-staging-github-terraform` and
`captioneer-staging-github-deploy` on 17 September 2026 at approximately 21:18 UTC.
The inline permission policy is named `AWSInfraCaptioneerQuarantine20260917`.
It unconditionally denies all actions/resources. The trust document has a deny
and no allow statements, blocking new assumptions without deleting the roles.

Both documents passed AWS validation without findings; their live copies matched
exactly, and all 12 sampled principal-policy decisions were explicit denies.
The [cleanup record](../docs/CAPTIONEER_CLEANUP.md) explains session/verification
limits, dependency checks, and the pending retirement/rebuild choice. Do not
remove quarantine or restore the former wildcard trust as a rollback.
