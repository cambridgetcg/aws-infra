# Current status — 18 September 2026

| Item | Observation |
| --- | --- |
| Scope | Private shared AWS operations repository across projects/accounts. |
| Local profiles | Existing `default` login preserved. `cambridge-human-admin`, `cambridge-agent-inventory` and `cambridge-iam-audit` are authenticated and usable. Routine inventory commands select the restricted inventory profile with no administrator fallback. |
| Authentication | CLI SSO device-code authorization succeeded, followed by exact account, existing user and immutable Admin role-ID verification. Human administrator access remains separate from the scoped task credentials. |
| Inventory | At 17:19:40 UTC the new inventory profile completed all eight permitted collections in `us-east-1`, including global S3 names; Lambda was excluded. The earlier Captioneer dependency refresh covered selected direct consumers across all 17 enabled regions: 268 checks passed, with no matches. The separate historical RewardsPro account remains unverified. |
| IAM review | Captioneer's exposed roles have been retired. Shared administrator login, active OpenClaw IAM key, MFA/root-key concerns and Cardforum trust scope remain outstanding. See [dated review](IAM_REVIEW_2026-09-17.md). |
| Existing foundation | Identity Center active in `us-east-1`; organization lists only Cambridge TCG as management account. Two multi-region CloudTrail trails logging; CashLoom Access Analyzer active. |
| Source map | Ten project/source records. RewardsPro legacy IAM/Lambda references verified in Cambridge TCG; the separate historical RewardsPro account remains unverified. Full workload/state ownership is distinct from these observations. |
| Remaining roles | The 14:26 UTC [map covers 133 preserved roles](IAM_ROLE_MAP_2026-09-18.md): 19 service-linked, 3 SSO, 50 CloudFormation-owned and 61 with unreconciled state ownership. At 17:17 UTC, two new SSO roles brought the total to 135; all 133 existing configurations and session ceilings were verified unchanged. No additional roles confirmed unused. |
| Access controls | [Inventory and IAM audit tiers](AGENT_ACCESS.md) are deployed with one-hour sessions and explicit denies outside their scope. The older standalone inventory policy remains unattached. Captioneer's quarantine documents and unused trust proposal are [historical](../policies/historical/captioneer-2026-09/README.md). |
| Cloud changes | [Five Captioneer roles deleted](CAPTIONEER_CLEANUP.md), verified at 12:52:50 UTC on 18 September. Four managed-policy attachments and eight inline policies removed. All 133 other role identities, the shared GitHub provider and shared policy objects were preserved. |
| Access rebuild | [Additive foundation](../infrastructure/agent-access/README.md) deployed and verified at 17:17:45 UTC: two permission sets and two assignments to the verified existing user. No directory user was created. User scope remains preserving applications, read-only default and temporary named-project access. |
| Profile checks | At 17:18:32 UTC, both profiles passed exact-role identity and temporary one-hour session checks. Inventory: EC2 VPC read allowed, IAM role listing denied. IAM audit: IAM role listing allowed, EC2 VPC read denied. Private verification receipt ends `171832.669636Z-agent-profile-verification.json`. |
| Executor | [Whole-agent runtime bundle](../infrastructure/agent-executor/README.md) has fixed access tiers, expiring credential handoff and credential-free network probes. User selected a [dedicated account and VM on this Mac](../infrastructure/agent-executor/setup-local.md) and [Codex subscription authentication](../infrastructure/agent-executor/subscription-auth.md). OS authentication, fresh runtime subscription login and live network/identity/expiry checks remain required; executor inactive. |

The successful identity checks, inventory and retirement verification are dated
observations. They do not establish an effective-permission audit of every resource or access
to all historical accounts. Private evidence remains under ignored
`inventory/local/`; reviewed summaries are committed.

The macOS administrator-dialog attempt timed out at approximately 17:46 UTC.
A fresh bootstrap preflight confirmed no `aws-agent` account or home existed.
Local runtime creation awaits OS authentication; no subscription login or
autonomous task has run in that runtime.

Captioneer IAM retirement is complete, with no replacement roles. This did not
delete application storage, databases or other workload resources, reconcile
archived Terraform state, or change keys, MFA, runtime configuration or GitHub
environments. Separating agent credentials from the human administrator session
remains outstanding.
