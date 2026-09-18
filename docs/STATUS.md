# Current status — 18 September 2026

| Item | Observation |
| --- | --- |
| Scope | Private shared AWS operations repository across projects/accounts. |
| Local profiles | Existing `default` login preserved. Named SSO profiles `cambridge-human-admin`, `cambridge-agent-inventory` and `cambridge-iam-audit` added with the owner-supplied portal URL; SSO authentication and restricted-role provisioning remain pending. |
| Authentication | Renewed login verified on 18 September as `YuCheung` in Cambridge TCG `034362054546`. The human identity still has AdministratorAccess. |
| Inventory | The 17 September general inventory covered nine selected collections in `us-east-1`, plus global S3 names. The 18 September Captioneer dependency refresh covered selected direct consumers across all 17 enabled regions: 268 checks passed, with no matches. RewardsPro remains unverified. |
| IAM review | Captioneer's exposed roles have been retired. Shared administrator login, active OpenClaw IAM key, MFA/root-key concerns and Cardforum trust scope remain outstanding. See [dated review](IAM_REVIEW_2026-09-17.md). |
| Existing foundation | Identity Center active in `us-east-1`; organization lists only Cambridge TCG as management account. Two multi-region CloudTrail trails logging; CashLoom Access Analyzer active. |
| Source map | Ten project/source records. RewardsPro legacy IAM/Lambda references verified in Cambridge TCG; the separate historical RewardsPro account remains unverified. Full workload/state ownership is distinct from these observations. |
| Remaining roles | Fresh IAM/Identity Center review at 14:24–14:26 UTC: 140 checks passed; [133 roles mapped](IAM_ROLE_MAP_2026-09-18.md). 19 service-linked, 3 SSO, 50 CloudFormation-owned and 61 with unreconciled state ownership. No additional roles confirmed unused. |
| Access controls | [Agent access model](AGENT_ACCESS.md) and inventory policy remain proposed. Captioneer's quarantine documents and unused trust proposal are [historical](../policies/historical/captioneer-2026-09/README.md). |
| Cloud changes | [Five Captioneer roles deleted](CAPTIONEER_CLEANUP.md), verified at 12:52:50 UTC on 18 September. Four managed-policy attachments and eight inline policies removed. All 133 other role identities, the shared GitHub provider and shared policy objects were preserved. |
| Access rebuild | User confirmed preserving applications, read-only default and temporary named-project access. [Additive foundation](../infrastructure/agent-access/README.md) validated by AWS; a four-Add CREATE change set is prepared but unexecuted. Portal URL supplied and local profiles configured. Browser SSO attempt timed out; logged-in identity verification and isolated executor activation remain pending. |

The successful identity checks, inventory and retirement verification are dated
observations. They do not establish an effective-permission audit of every resource or access
to all historical accounts. Private evidence remains under ignored
`inventory/local/`; reviewed summaries are committed.

Captioneer IAM retirement is complete, with no replacement roles. This did not
delete application storage, databases or other workload resources, reconcile
archived Terraform state, or change keys, MFA, runtime configuration or GitHub
environments. Separating agent credentials from the human administrator session
remains outstanding.
