# Current status — 18 September 2026

| Item | Observation |
| --- | --- |
| Scope | Private shared AWS operations repository across projects/accounts. |
| Local profile | Only `default`, using an AWS CLI login session in `us-east-1`; no local SSO or dedicated agent profile. |
| Authentication | Renewed login verified on 18 September as `YuCheung` in Cambridge TCG `034362054546`. The human identity still has AdministratorAccess. |
| Inventory | The 17 September general inventory covered nine selected collections in `us-east-1`, plus global S3 names. The 18 September Captioneer dependency refresh covered selected direct consumers across all 17 enabled regions: 268 checks passed, with no matches. RewardsPro remains unverified. |
| IAM review | Captioneer's exposed roles have been retired. Shared administrator login, active OpenClaw IAM key, MFA/root-key concerns and Cardforum trust scope remain outstanding. See [dated review](IAM_REVIEW_2026-09-17.md). |
| Existing foundation | Identity Center active in `us-east-1`; organization lists only Cambridge TCG as management account. Two multi-region CloudTrail trails logging; CashLoom Access Analyzer active. |
| Source map | Seven project/source records. Account identity is verified separately from workload/state ownership. |
| Access controls | [Agent access model](AGENT_ACCESS.md) and inventory policy remain proposed. Captioneer's quarantine documents and unused trust proposal are [historical](../policies/historical/captioneer-2026-09/README.md). |
| Cloud changes | [Five Captioneer roles deleted](CAPTIONEER_CLEANUP.md), verified at 12:52:50 UTC on 18 September. Four managed-policy attachments and eight inline policies removed. All 133 other role identities, the shared GitHub provider and shared policy objects were preserved. |

The successful identity checks, inventory and retirement verification are dated
observations. They do not establish an effective-permission audit of every resource or access
to all historical accounts. Private evidence remains under ignored
`inventory/local/`; reviewed summaries are committed.

Captioneer IAM retirement is complete, with no replacement roles. This did not
delete application storage, databases or other workload resources, reconcile
archived Terraform state, or change keys, MFA, runtime configuration or GitHub
environments. Separating agent credentials from the human administrator session
remains outstanding.
