# AWS credentials and IAM review — 17 September 2026

**Later update, approximately 21:18 UTC:** both globally trusted Captioneer
roles were [quarantined](CAPTIONEER_CLEANUP.md) after the follow-up request to
handle them. The observations below preserve the earlier read-only review;
their wildcard trust has since been replaced and role-local denies added.

**The renewed login works, but it exposes administrator access to local agents.**
The most urgent finding is separate: two Captioneer roles trust tokens from any
GitHub repository, and one carries `AdministratorAccess`.

This is a read-only review of Cambridge TCG account `034362054546`, with local
observations starting at 16:52 UTC. No IAM grants, trust policies, keys, MFA,
runtime configuration or GitHub environment settings were changed. The policy
files in this repository are proposals, not deployed controls.

## Priorities

| Priority | Observed condition | Recommended next change |
| --- | --- | --- |
| **Critical** | `captioneer-staging-github-terraform` trusts GitHub `sub=repo:*:*`, has `AdministratorAccess`, and no boundary. | Restrict trust immediately to the intended repository/environment, then replace broad administration with a reviewed deployment scope or retire the unused role. |
| **High** | `captioneer-staging-github-deploy` has the same global GitHub trust, broad ECR/ECS grants, `iam:PassRole` and application secret reads. | Apply the same trust restriction and narrow its deployment permissions. |
| **High** | Local `default` authenticates as IAM user `YuCheung`, with `AdministratorAccess` and no boundary; unrestricted agents share access to that login. | Give agents separate temporary identities and isolate their runtime from the human administrator cache. |
| **High** | `YuCheung` has no attached IAM MFA device. Account summary reports a root access key present. | Establish MFA-backed human access; investigate and retire root keys after checking dependencies and recovery access. Root key activity was not established. |
| **High** | `openclaw-agent` retains an active long-lived key and EC2/network mutations on `Resource: "*"`, without region conditions or a boundary. | Identify the actual consumer, migrate to a scoped temporary role, verify its work, then deactivate the old key. |
| **Review** | `cardforum-dev-cicd-secrets` trusts `repo:*/cardforum:*`, allowing any repository owner with that repository name. | Confirm the owner and full attached permissions, then constrain owner/repository and environment. |

Severity describes exposure, not evidence of compromise. No hostile assumption,
secret read, instance change or other exploit was attempted.

## Account and human access

STS returned `arn:aws:iam::034362054546:user/YuCheung`. This user's managed
policies are `AdministratorAccess` and `RDSCardforum-IAMConnect`, with no inline
policies, groups or permissions boundary. The current default version of
`AdministratorAccess` allows `Action: "*"` on `Resource: "*"`.

The account is its AWS Organizations **management account**. Organization account
listing returned only this active account; the root had no enabled policy types.
RewardsPro `043509841549` was not in that organization and was not authenticated
or scanned. This does not prove RewardsPro no longer exists or is inaccessible
through a different login.

SCPs do not constrain management-account users/roles, and RCPs do not constrain
management-account resources. Enabling organization policies alone would not
contain this administrator or these local roles. See
[AWS SCP scope](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html)
and [AWS RCP scope](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_rcps.html).

IAM Identity Center is already active in `us-east-1`. Its permission sets have
current account assignments:

| Permission set | Configured session duration | Assignment types returned |
| --- | --- | --- |
| AdministratorAccess | 8 hours | User and group |
| PowerUserAccess | 12 hours | User |
| ReadOnlyAccess | 12 hours | User |

The generated IAM roles have a 12-hour maximum; this is distinct from each
permission set's session setting. Assigned people's identities, sign-in portal
details and Identity Center MFA enforcement were not inspected. Reuse this
existing setup rather than creating another directory. AWS managed
`ReadOnlyAccess` is broader than the proposed inventory policy.

The IAM account password policy requires 14 characters, all four character
classes, and prevents reuse of 24 passwords; periodic expiry is disabled.
`AccountMFAEnabled=1` and `AccountAccessKeysPresent=1` were observed. Reading an
existing credential report returned `ReportNotPresent`, so root key activity and last use
remain unknown. No attached MFA device was returned for any of the eight IAM
users. Registration metadata does not establish the MFA context of a particular
login or the Identity Center authentication policy.

## Agent and application IAM users

Key identifiers and credential values are omitted. Last-use metadata identifies
one recorded service use, not every consumer or the absence of other access.

| IAM user | Long-lived keys | Permission observations / recorded last use |
| --- | --- | --- |
| `openclaw-agent` | 1 active, 1 inactive | Active key created 17 March; last recorded use 21 August 2026, STS in `us-east-1`. Inline policy allows EC2 start/stop/reboot, security-group ingress changes and allocate/associate Elastic IPs on `*`; self IAM reads and STS identity. No region conditions. |
| `alpha-agent` | 2 inactive | Ten managed policies include EC2 full access, Secrets Manager read/write, SES/SNS full access and logs full access. Inline policies grant selected S3 object operations plus RDS describe/connect on `*`. Keys being inactive does not remove the policies. |
| `cambridgetcg-storefront-app` | 1 active | Inline `storefront-ses-s3`; last recorded use 24 August, SES. |
| `cambridgetcg-storefront-prod` | 1 active | Inline `CambridgeTcgStorefrontRuntime`; last recorded use 14 September, SES. |
| `wholesale-media-writer` | 1 active | Inline `s3-media-buckets`; last recorded use 13 July, S3. |
| `cardforum-vercel-secrets-reader` | 2 inactive | Inline `SecretsReadOnly`; no recorded key use returned. |
| `github-actions-axiepro` | 1 inactive | ECR PowerUser and App Runner FullAccess managed policies; last recorded use 2 February, App Runner. |
| `YuCheung` | 1 inactive | Long-lived key inactive; the working CLI uses the renewed temporary login. |

`GetUser` confirmed no permissions boundary for all eight users. Group membership
was empty for each. The local configuration contains none of these users' static
keys; their presence in IAM does not mean this machine is using them.

## GitHub federation: concrete trust repair

The four GitHub-trusting roles discovered were:

| Role | Current `sub` condition | Observed scope |
| --- | --- | --- |
| `captioneer-staging-github-terraform` | `repo:*:*` | AdministratorAccess; no inline policy or boundary. |
| `captioneer-staging-github-deploy` | `repo:*:*` | ECR PowerUser, ECS FullAccess, plus inline ECR/ECS, scoped PassRole and Captioneer secrets/parameters. No boundary. |
| `captioneer-staging-github-actions-role` | `repo:cambridgetcg/captioneer:*` | ECR repository access, ECS deployment actions and two specific PassRole targets. No boundary. |
| `cardforum-dev-cicd-secrets` | `repo:*/cardforum:*` | Trust reviewed; full permissions were outside the targeted role-policy review. |

All four require `aud=sts.amazonaws.com`; that audience does not restrict the
repository. Current live trust and attached policy documents establish the
Captioneer exposure. Empty `RoleLastUsed` responses are not proof of no misuse.

The owning [Captioneer bootstrap source](https://github.com/cambridgetcg/captioneer/blob/019d3619f76dc4fce58f38d997421ff3caf5c27a/infrastructure/scripts/bootstrap-aws.sh#L160)
creates the wildcard trust and reuses it for the administrator Terraform role.
The repository is private and archived. Archiving source does not revoke AWS
trust. Its [deploy workflow](https://github.com/cambridgetcg/captioneer/blob/019d3619f76dc4fce58f38d997421ff3caf5c27a/.github/workflows/deploy.yml)
and [Terraform workflow](https://github.com/cambridgetcg/captioneer/blob/019d3619f76dc4fce58f38d997421ff3caf5c27a/.github/workflows/terraform.yml)
use the `staging` GitHub environment for the main branch path.

[captioneer-staging-github-trust.json](../policies/captioneer-staging-github-trust.json)
is the proposed complete trust document for the two broadly trusted staging
roles. It permits only the exact subject
`repo:cambridgetcg/captioneer:environment:staging`, the existing provider/audience,
and `ref=refs/heads/main`. GitHub's repository OIDC metadata confirmed that subject
format; AWS documents support for the GitHub `ref` condition. It preserves the
intended staging main-branch path and intentionally excludes production,
other repositories, other refs and non-environment subjects. Actual token-based
workflow verification remains part of a future deployment of the repair.

The current GitHub `staging` environment has **no protection rules or deployment
branch restriction**. Pair the IAM repair with a main-only environment deployment
policy. The proposed IAM `ref` condition and main-only environment policy block
the existing privileged PR-plan path; if restored, PR plans need separate limited
access. Environment subject matching alone does not check the branch, which is
why the proposal also tests `ref`. Review the separate `github-actions-role` before changing it, because
its actual workflow linkage is unverified.

Repository and staging-environment secret name inventories were empty;
organization-inherited configuration was not checked. The workflow role reference
values and deployment readiness remain unverified. Repair the bootstrap source
before reusing it; it skips existing roles, so a source edit alone does not repair
live trust. Follow [AWS OIDC guidance](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-idp_oidc.html)
and [GitHub environment guidance](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws).
Supported claim conditions are listed in the [AWS condition-key reference](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_iam-condition-keys.html).

An authorized execution should first save the current role policies locally,
apply the exact reviewed trust document, re-read both trusts, and verify the
intended workflow under its protected environment. A failure should lead to a
corrected restrictive trust or disabled access, not automatic restoration of
the globally trusted administrator role. Historical CloudTrail review is a
separate necessary follow-up for potential prior use.

## Local credentials and proposed access model

`~/.aws/config` has only `default`, using `login_session` and `us-east-1`.
It and the one login-cache file are `0600`; AWS directories are `0755`.
`~/.aws/credentials` is absent, and no AWS credential environment variables or
credential-process configuration were found in the inspected agent process.
Credential/cache contents were not read. Both agent runtimes share the owning
OS user and allow unrestricted command execution in the inspected configuration.

File permissions separate OS users, not agents sharing one user. A read-only
script and a narrower profile cannot restrict an agent that can also access the
administrator login. [AGENT_ACCESS.md](AGENT_ACCESS.md) explains the proposed
temporary-role and runtime-isolation model, including inventory, IAM audit,
deployment, administration, CI and application identities.

## Existing controls, validation and limits

Two multi-region, global-event CloudTrail trails were logging with recent
deliveries and no returned latest delivery error: `cardforum-dev-secrets-audit`
and `cashloom-sec-trail`. Both capture management events. This verifies logging
status, not complete event retention, alerting or incident history.
`cashloom-sec-analyzer` is active in `us-east-1`; its existing findings include
the four GitHub-trusting roles. Their `isPublic=false` flags do not negate the
actual wildcard subjects above; inspect trust conditions rather than using that
flag as a safety verdict.

The account reported eight IAM users and 138 roles. All role trust documents were
enumerated; detailed policy/last-use checks covered the three Captioneer roles,
three Identity Center roles, and two Cardforum administrative roles. The latter
includes an actual `cardforum-dev-secrets-boundary` on `cardforum-SecurityAdmin`.
Do not infer missing boundaries from `ListRoles`; `GetRole` was used for the
targeted roles. This was not an effective-permission audit of all 138 roles or
every resource policy, endpoint policy, identity provider or possible escalation.

The [proposed inventory permissions](../policies/README.md) contain nine explicit
service actions. AWS Access Analyzer validation returned no findings. A custom
policy simulation allowed all nine inventory actions and implicitly denied nine
sample data-read, secret-read, role-passing/assumption and EC2 mutation actions.
This evaluates the policy in isolation, not the current user's effective access;
no tested service mutation or secret read was executed. Its
Lambda action can return environment configuration to the CLI before local
filtering; it is not a guarantee that secret-bearing data never reaches the
process. The policy remains unattached and does not reduce current admin access.

AWS validation of the final Captioneer trust proposal returned no errors or
warnings and one audience-type suggestion; the document uses unqualified
`StringEquals` as that suggestion requires. The explicit main-branch `ref`
condition resolved the initial branch-scope warning. No live GitHub token or
role-assumption test was performed. Repository checks and all 24 offline
collector tests passed.

The existing inventory collector completed all nine selected collections in
`us-east-1`, plus global S3 names: 1 EC2 instance, 4 VPCs, 55 Lambda functions,
3 RDS instances, 0 ECS clusters, 17 DynamoDB tables, 12 queues, 31 CloudFormation
stack summaries and 63 S3 buckets. Stack summaries include retained deleted
stacks; bucket listing excludes directory buckets. Other regions/accounts and
services remain unscanned. Resource/state ownership is not established by counts.

Evidence is retained only under ignored, private `inventory/local/`: dated
identity, IAM metadata/policies, key status/last-use metadata, logging checks,
inventory and policy-validation reports. No key IDs, credential values, secret
values, raw reports or Terraform state are committed with this review.
