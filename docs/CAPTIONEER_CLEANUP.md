# Captioneer IAM retirement — 18 September 2026

**Complete: all five Captioneer IAM roles were deleted and verified absent at
12:52:50 UTC on 18 September 2026.** The user explicitly chose retirement with
no replacement roles. Renewed login verified Cambridge TCG account
`034362054546` and principal `arn:aws:iam::034362054546:user/YuCheung` before
the change.

This retired Captioneer's IAM access. Application storage, databases, other
workload resources and archived Terraform state were outside the change.

## What was removed

| Deleted role | Former purpose | Managed attachments removed | Inline policies removed |
| --- | --- | --- | --- |
| `captioneer-staging-github-terraform` | GitHub infrastructure deployment | `AdministratorAccess` | Quarantine deny |
| `captioneer-staging-github-deploy` | GitHub application deployment | `AmazonEC2ContainerRegistryPowerUser`, `AmazonECS_FullAccess` | Deployment policy and quarantine deny |
| `captioneer-staging-github-actions-role` | Separate GitHub role defined in Terraform | None | ECR and ECS deployment policies |
| `captioneer-staging-ecs-execution-role` | ECS image pulls, logging and secret injection | `AmazonECSTaskExecutionRolePolicy` | Execution secrets policy |
| `captioneer-staging-ecs-task-role` | Application S3 and logging access | None | Task logs and S3 policies |

All **17 mutation calls succeeded** between 12:50:49 and 12:52:28 UTC: four
managed-policy detachments, eight inline-policy removals and five role deletions.
The shared managed-policy objects themselves were retained.

`GetRole` returned `NoSuchEntity` for each role immediately after deletion and
again during final verification. The account's role count fell from **138 to
133**, with no Captioneer-named roles remaining. Every other role's name and
principal ID matched the pre-change inventory. The shared GitHub OIDC provider's
metadata matched exactly, and all four detached AWS managed policies retained
their original policy IDs. No replacement identities were created.

## Dependency check before deletion

A fresh read-only check completed at **12:49:00 UTC**, before any deletion.
All **268 checks passed across the 17 enabled regions**, with no failures or
direct references to any of the five role identities. Their current role IDs,
trust, attached and inline policies were checked against the saved baseline;
none had instance-profile associations or a permissions boundary.

| Dependency | Result |
| --- | --- |
| ECS clusters | Zero across the enabled regions. |
| Active ECS task definitions | Six; all reference other roles. |
| Lambda execution-role references | 81 rows with all function versions requested; no Captioneer role references. |
| IAM instance profiles / EC2 attachments | Global profiles and two EC2 attachment rows inspected; no Captioneer roles. |
| CloudFormation | 33 stack service-role rows plus enumerated IAM-role, instance-profile and ECS task-definition resources; no Captioneer ownership/reference found. |
| EventBridge | Rules and targets across all 19 listed buses, including custom buses; no Captioneer role references. |
| Scheduler / Step Functions | Four schedule targets and three state-machine execution roles; no Captioneer references. |

The regions were `ap-south-1`, `ca-central-1`, `eu-central-1`, `us-west-1`,
`us-west-2`, `eu-north-1`, `eu-west-3`, `eu-west-2`, `eu-west-1`,
`ap-northeast-3`, `ap-northeast-2`, `ap-northeast-1`, `sa-east-1`,
`ap-southeast-1`, `ap-southeast-2`, `us-east-1` and `us-east-2`.

This check covered selected direct consumers. It did not establish the absence
of historical/inactive references, resource-policy grants, application/static
configuration, external CI, cross-account dependencies or Terraform-state
references. It provided no atomic lock against concurrent deployments. Empty
IAM `RoleLastUsed` data was not used as proof of non-use.

## How the exposed roles were contained first

On 17 September at approximately **21:18 UTC**, the Terraform and deployment
bootstrap roles were quarantined after their global GitHub trust was discovered:

1. Each received the inline policy `AWSInfraCaptioneerQuarantine20260917`, an
   unconditional deny of all actions/resources. The
   [permission document](../policies/historical/captioneer-2026-09/captioneer-quarantine-permissions.json)
   is preserved unchanged.
2. Each trust was replaced with a document containing an explicit deny for
   same-account `AssumeRole` and no allow statements. The
   [trust document](../policies/historical/captioneer-2026-09/captioneer-quarantine-trust.json)
   is preserved unchanged. The shared GitHub provider was retained.

Both documents passed AWS Access Analyzer validation without findings. Live
documents matched exactly, and all 12 sampled principal-policy decisions were
explicit denies. Those simulations did not perform secret reads or mutations,
or exercise previously issued session credentials.

More than 15 hours elapsed between quarantine and retirement, exceeding the
12-hour maximum duration of direct web-identity sessions. Before deletion, the
executor confirmed quarantine remained intact. It removed original permission
grants first, retaining the quarantine deny until immediately before `DeleteRole`.
The former wildcard trust was never restored.
[AWS web-identity session duration](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRoleWithWebIdentity.html),
[role deletion requirements](https://docs.aws.amazon.com/IAM/latest/APIReference/API_DeleteRole.html).

Trust changes alone do not remove existing sessions' permissions. The role-local
deny addressed that gap, subject to IAM propagation. Neither those simulations
nor this retirement investigated sessions previously obtained in other roles
through role chaining. No claim of complete incident containment or absence of
prior misuse is made.
[AWS temporary-session permission control](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp_control-access_disable-perms.html),
[AWS session revocation](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html).

## Historical source and evidence

The earlier
[staging/main trust proposal](../policies/historical/captioneer-2026-09/captioneer-staging-github-trust.json)
was **never deployed** and is superseded by retirement. These historical policy
documents are audit records, not instructions to recreate the roles.

The archived
[Captioneer bootstrap source](https://github.com/cambridgetcg/captioneer/blob/019d3619f76dc4fce58f38d997421ff3caf5c27a/infrastructure/scripts/bootstrap-aws.sh)
still contains unsafe trust defaults. Do not rerun it unchanged. Any future
revival needs a separate design, source/state reconciliation and only the
identities required by the intended workload. This cleanup did not import old
Terraform state or restore the archived deployment workflow.

Recreating a role name creates a new IAM principal ID. Policies tied to the old
principal ID and conditions matching the ARN string behave differently after
recreation; neither preservation of old integrations nor removal of every
possible grant can be assumed.
[AWS principal identity semantics](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_principal.html).

Private metadata backups, dependency evidence and durable mutation journals are
retained under ignored `inventory/local/`, with private filesystem permissions:

- Original role snapshot: `20260917T211309.978927Z-cambridge-tcg.json`.
- Verified quarantine: `20260917T211812.040204Z-captioneer-containment.json`.
- Fresh dependency gate: `20260918T124900.893682Z-captioneer-dependency-refresh.json`.
- Verified retirement: `20260918T125250.602591Z-captioneer-retirement.json`.

The retirement journal includes pre-change role definitions, operation outcomes,
final verification and hashes of the historical evidence. Credentials, secret
values, raw reports and Terraform state are not published.
