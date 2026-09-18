# Current status — 18 September 2026

| Item | Observation |
| --- | --- |
| Scope | Private shared AWS operations repository across projects/accounts. |
| Local profile | Only `default`, using an AWS CLI login session in `us-east-1`; no local SSO or dedicated agent profile. |
| Authentication | Last successful identity verification on 17 September: `YuCheung` in Cambridge TCG `034362054546`, with AdministratorAccess. The session expired overnight; browser renewal is pending. |
| Inventory | All nine selected collections succeeded in `us-east-1`, plus global general-purpose S3 bucket names. Other regions/services and RewardsPro remain unscanned. |
| IAM review | Critical Captioneer GitHub trust exposure; shared administrator login; active OpenClaw IAM key; MFA/root-key concerns. See [dated review](IAM_REVIEW_2026-09-17.md). |
| Existing foundation | Identity Center active in `us-east-1`; organization lists only Cambridge TCG as management account. Two multi-region CloudTrail trails logging; CashLoom Access Analyzer active. |
| Source map | Seven project/source records. Account identity is verified separately from workload/state ownership. |
| Access controls | [Agent access model](AGENT_ACCESS.md) and inventory/staging-main policies remain proposed. [Captioneer quarantine](CAPTIONEER_CLEANUP.md) is applied to two roles. |
| Cloud changes | Two Captioneer GitHub roles quarantined with no-allow trust and explicit-deny inline permissions. No roles deleted; other IAM access, keys, MFA, runtime config and GitHub environments unchanged. |

The 17 September successful identity check and selected scan are dated observations;
18 September's session renewal is still required before additional AWS work.
Those observations do not establish an effective-permission audit of every resource or access
to all historical accounts. Private evidence remains under ignored
`inventory/local/`; reviewed summaries are committed.

Captioneer retirement and removal of all five unused IAM roles are authorized.
Yesterday's verified quarantine is the last observed state; deletion awaits
renewed authentication and refreshed dependencies. No replacement roles will be
created. Separating agent credentials from the human administrator session
remains outstanding.
