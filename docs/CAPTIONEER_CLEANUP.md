# Captioneer IAM cleanup — 17–18 September 2026

**Retirement authorized on 18 September: remove the five unused Captioneer IAM
roles, with no replacement roles.** The browser login expired overnight; final
dependency checks and deletion are pending renewed authentication. No roles have
been deleted. The two globally trusted GitHub roles were last verified in
quarantine on 17 September.

The earlier containment and dependency evidence is preserved below. The scope
is Captioneer's five IAM roles and their attachments/inline policies; it does
not include shared identity providers, other projects' roles, or application
storage, databases and other workload resources.

## Current state

The verified target is Cambridge TCG account `034362054546`. Exactly five
Captioneer-named roles were found:

| Role | Purpose | Current handling |
| --- | --- | --- |
| `captioneer-staging-github-terraform` | GitHub infrastructure deployment; AdministratorAccess attached | **Quarantined** at approximately 21:18 UTC. |
| `captioneer-staging-github-deploy` | GitHub application deployment; broad ECR/ECS and application-secret permissions | **Quarantined** at approximately 21:18 UTC. |
| `captioneer-staging-github-actions-role` | Separate GitHub role defined in Terraform; trusts the named Captioneer repository | Unchanged; candidate for retirement or replacement. |
| `captioneer-staging-ecs-execution-role` | ECS platform pulls/logging/application-secret injection | Unchanged; no observed consumers. |
| `captioneer-staging-ecs-task-role` | Application S3/logging operations | Unchanged; no observed consumers. |

The account-wide GitHub OIDC provider, shared AWS managed policies, other
projects' identities and AWS workload resources were not modified.

## What containment changed

Two exact changes were applied to each of the first two roles, after a fresh STS
account check, trust preconditions and private backups:

1. Added the inline permission policy `AWSInfraCaptioneerQuarantine20260917`,
   matching [captioneer-quarantine-permissions.json](../policies/captioneer-quarantine-permissions.json).
   Its unconditional explicit deny covers all actions/resources, including
   permissions that would otherwise be granted to existing role sessions.
2. Replaced the role's trust with
   [captioneer-quarantine-trust.json](../policies/captioneer-quarantine-trust.json).
   It contains an explicit deny for same-account `AssumeRole` and **no allow
   statements for any principal or assumption method**. The GitHub allow was
   removed from these roles; the shared provider itself remains intact.

The existing permission attachments were retained behind the deny. This is
quarantine, not least-privilege redeployment. Removing the deny would restore
the effect of those grants and must not be treated as routine cleanup.
The earlier [staging/main trust proposal](../policies/captioneer-staging-github-trust.json)
was **not** deployed; it remains a candidate for a reviewed future replacement.

Both quarantine documents passed AWS Access Analyzer validation without findings.
The live trust and inline permission documents were re-read and matched exactly.
`SimulatePrincipalPolicy` returned `explicitDeny` for six sampled actions on each
role: IAM user creation, role passing, EC2 describe, S3 account listing, secret
value retrieval and role assumption. None of those mutations or secret reads
was executed. Simulations verify policy decisions, not possession/testing of
old session credentials; IAM changes are eventually consistent.

Trust changes alone do not remove existing sessions' permissions. The role-local
deny addresses that gap, subject to IAM propagation. It does not revoke sessions
already obtained in **other** roles through role chaining. No assertion of
complete incident containment or absence of prior misuse is made.
[AWS temporary-session permission control](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp_control-access_disable-perms.html),
[AWS session revocation](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html).

## Dependency checks before deletion

Read-only inspection covered all 17 enabled regions: `ap-south-1`,
`ca-central-1`, `eu-central-1`, `us-west-1`, `us-west-2`, `eu-north-1`,
`eu-west-3`, `eu-west-2`, `eu-west-1`, `ap-northeast-3`, `ap-northeast-2`,
`ap-northeast-1`, `sa-east-1`, `ap-southeast-1`, `ap-southeast-2`, `us-east-1`
and `us-east-2`. All selected calls succeeded.

| Dependency | Result |
| --- | --- |
| ECS clusters | Zero across the enabled regions. |
| Active ECS task definitions | Six; all reference other roles. |
| Lambda execution-role references | 78 inspected; no Captioneer role references. |
| IAM instance profiles / EC2 attachments | Global profiles and two EC2 attachments inspected; no Captioneer roles. |
| CloudFormation | 33 service-role references and enumerated IAM-role, instance-profile and ECS task-definition resources; no Captioneer ownership/reference found. |
| EventBridge default-bus rules | 51 rules' targets inspected; no Captioneer role references. |
| Scheduler / Step Functions | Four schedule targets and three state-machine execution roles; no Captioneer references. |

These results make retiring the five roles appear low risk to observed workloads.
They do not cover external CI consumers, inactive task definitions, custom
EventBridge buses, every application/configuration reference, resource policies
or Terraform state. Empty IAM `RoleLastUsed` data does not establish non-use.
Bounded CloudTrail resource-name lookups for the three GitHub role names returned
no events in `us-east-1` over the previous seven days; that is not an all-region
assumption history or an incident investigation.

## Approved retirement process

On 18 September, the user explicitly chose retirement and removal of the five
unused roles. The five names above are the approved deletion scope; no further
deletion approval or replacement design is needed.
Do not interpret “all roles” as all 138 roles in the AWS account. Resolve outside
references and keep containment until affected sessions expire before removing
the inline deny for deletion. The current one-hour role maximum alone does not
establish every older session's expiry; removing the deny early can reopen access.
Programmatic role deletion requires removing instance-profile associations,
deleting inline policies and detaching managed policies before `DeleteRole`.
Delete neither shared managed-policy objects nor the shared OIDC provider.
Keep the quarantine deny until the final deletion stage; verify each targeted
role returns `NoSuchEntity` afterward.
[AWS DeleteRole requirements](https://docs.aws.amazon.com/IAM/latest/APIReference/API_DeleteRole.html).

If Captioneer is revived in a future task, define its intended runtime, deployment workflow,
resource scope and source/state owner first. Create only the required identities:
runtime roles for application needs, a narrowly trusted repository/environment/
branch deployment role, and a separately controlled infrastructure change role
only if needed. An administrator role open to GitHub is not a starting template.
The saved private snapshots retain the old definitions; retirement does not
authorize recreating either ECS role.

Recreating the same name creates a new IAM principal ID. Existing policies using
the former principal ID may stop working, while conditions matching an ARN string
can match a recreated name again. Deletion/recreation therefore neither preserves
every integration nor resets every possible grant. Verify both kinds of reference.
[AWS principal identity semantics](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_principal.html).

The archived [Captioneer bootstrap source](https://github.com/cambridgetcg/captioneer/blob/019d3619f76dc4fce58f38d997421ff3caf5c27a/infrastructure/scripts/bootstrap-aws.sh)
still contains the unsafe trust defaults. Do not rerun it unchanged. Source/state
reconciliation is necessary before a rebuild; this cleanup does not import old
Terraform state or restore the archived project's deployment workflow.

Private snapshots, mutation journals and dependency observations remain under
ignored `inventory/local/`. The final containment record ends
`20260917T211812.040204Z-captioneer-containment.json`; the regional and detailed
dependency reports end `20260917T211539.776395Z-captioneer-dependencies.json` and
`20260917T211746.959750Z-captioneer-dependency-details.json`. Credentials, secret
values, state and raw reports are not published.
