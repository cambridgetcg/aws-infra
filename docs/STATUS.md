# Current status — 17 September 2026

| Item | Observation |
| --- | --- |
| Scope | Private shared AWS operations repository across projects/accounts. |
| Local profile | Only `default`, using an AWS CLI login session in `us-east-1`; no local SSO or dedicated agent profile. |
| Authentication | Renewed login verified `YuCheung` in Cambridge TCG `034362054546`. AdministratorAccess attached; not an inventory-only identity. |
| Inventory | All nine selected collections succeeded in `us-east-1`, plus global general-purpose S3 bucket names. Other regions/services and RewardsPro remain unscanned. |
| IAM review | Critical Captioneer GitHub trust exposure; shared administrator login; active OpenClaw IAM key; MFA/root-key concerns. See [dated review](IAM_REVIEW_2026-09-17.md). |
| Existing foundation | Identity Center active in `us-east-1`; organization lists only Cambridge TCG as management account. Two multi-region CloudTrail trails logging; CashLoom Access Analyzer active. |
| Source map | Seven project/source records. Account identity is verified separately from workload/state ownership. |
| Proposed controls | [Agent access model](AGENT_ACCESS.md), [inventory permissions and trust repair](../policies/README.md). Files are not deployed. |
| Cloud changes | None. IAM permissions, trust, keys, MFA, runtime config and GitHub environments remain unchanged. |

The initial repository setup observed an expired login. The later successful
identity check and selected scan supersede that authentication limitation.
They do not establish an effective-permission audit of every resource or access
to all historical accounts. Private evidence remains under ignored
`inventory/local/`; reviewed summaries are committed.

Prioritize the Captioneer trust repair, then separate agent credentials from the
human administrator session. Preserve verified recovery access and application
continuity when migrating active keys or changing grants.
