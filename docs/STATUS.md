# Current status — 19 September 2026

All times are UTC. Account, role and foundation observations below are dated
18 September unless a later date is stated; runtime completion is dated 19 September.

| Item | Observation |
| --- | --- |
| Scope | Private shared AWS operations repository across projects/accounts. |
| Local profiles | Existing `default` login preserved. `cambridge-human-admin`, `cambridge-agent-inventory` and `cambridge-iam-audit` passed the 18 September profile checks. Routine inventory commands select the restricted inventory profile with no administrator fallback; expired sessions require renewal. |
| Authentication | Native AWS SSO login completed on 19 September at 08:52:57; Mac Terminal authentication was ready at 08:53:06. The separate runtime Codex subscription login completed at 08:55:07. Human administrator access remains separate from scoped task credentials. |
| Inventory | At 17:19:40 UTC the new inventory profile completed all eight permitted collections in `us-east-1`, including global S3 names; Lambda was excluded. The earlier Captioneer dependency refresh covered selected direct consumers across all 17 enabled regions: 268 checks passed, with no matches. The separate historical RewardsPro account remains unverified. |
| IAM review | Captioneer's exposed roles have been retired. Shared administrator login, active OpenClaw IAM key, MFA/root-key concerns and Cardforum trust scope remain outstanding. See [dated review](IAM_REVIEW_2026-09-17.md). |
| Existing foundation | Identity Center active in `us-east-1`; organization lists only Cambridge TCG as management account. Two multi-region CloudTrail trails logging; CashLoom Access Analyzer active. |
| Source map | Ten project/source records. RewardsPro legacy IAM/Lambda references verified in Cambridge TCG; the separate historical RewardsPro account remains unverified. Full workload/state ownership is distinct from these observations. |
| Remaining roles | The 14:26 UTC [map covers 133 preserved roles](IAM_ROLE_MAP_2026-09-18.md): 19 service-linked, 3 SSO, 50 CloudFormation-owned and 61 with unreconciled state ownership. At 17:17 UTC, two new SSO roles brought the total to 135; all 133 existing configurations and session ceilings were verified unchanged. No additional roles confirmed unused. |
| Access controls | [Inventory and IAM audit tiers](AGENT_ACCESS.md) are deployed with one-hour sessions and explicit denies outside their scope. The older standalone inventory policy remains unattached. Captioneer's quarantine documents and unused trust proposal are [historical](../policies/historical/captioneer-2026-09/README.md). |
| Cloud changes | [Five Captioneer roles deleted](CAPTIONEER_CLEANUP.md), verified at 12:52:50 UTC on 18 September. Four managed-policy attachments and eight inline policies removed. All 133 other role identities, the shared GitHub provider and shared policy objects were preserved. |
| Access rebuild | [Additive foundation](../infrastructure/agent-access/README.md) deployed and verified at 17:17:45 UTC: two permission sets and two assignments to the verified existing user. No directory user was created. User scope remains preserving applications, read-only default and temporary named-project access. |
| Profile checks | At 17:18:32 UTC, both profiles passed exact-role identity and temporary one-hour session checks. Inventory: EC2 VPC read allowed, IAM role listing denied. IAM audit: IAM role listing allowed, EC2 VPC read denied. Private verification receipt ends `171832.669636Z-agent-profile-verification.json`. |
| Executor | [Dedicated Mac runtime](MAC_AGENT_FLOW.md) and Squid proxy use Docker Engine 28.4.0. On 19 September, refreshed 28-check network and DNS/cleanup verification passed at 08:53:42 against the same pinned runtime. The maintained `run-task.py` completed its first inventory task at 08:55:47.967; post-task inspection passed at 08:55:48. |

The trusted task result matched Cambridge account `034362054546` and the pinned
inventory role ID. The model reported `vpc_count: 4`, `iam_list_roles: AccessDenied`
and `overall: passed`; that summary is not independent attestation of each
command. The issued AWS session had expiry `2026-09-19T09:55:08+00:00`.
The CLI waited for successful target exit, including staging cleanup. Post-task
inspection found valid local authentication schema, only the pinned proxy,
no submitted task directories and no other containers. Returned authentication
was privately persisted for the same account; token rotation was not independently
observed. The separate fixed smoke helper and an isolated IAM-audit task were
not live-tested.

The temporary foreground controller closed at 08:56:42.783 UTC on 19 September.
Its Terminal window can be closed. The reviewed private summary is
`inventory/local/20260919T085548Z-isolated-inventory-verification.json`;
it records source pins, timestamps, scoped results, cleanup and limits without
authentication values or session identifiers.

The successful identity checks, inventory and retirement verification are dated
observations. They do not establish an effective-permission audit of every resource or access
to all historical accounts. Private evidence remains under ignored
`inventory/local/`; reviewed summaries are committed.

The locked `aws-agent` account (UID 502), human-home access denial, dedicated VM
mounts and forwarding configuration passed live checks. Both Python scripts are
readable by container UID 10001; the final image contains the reviewed repository
probe bytes. IPv6 evidence included disabled `all`, `default`, `eth0` and `lo`
settings, no IPv6 addresses and no active IPv6 routes.

DNS observation captured real UDP queries and synthetic, checksummed TCP DNS
canaries on `eth0` before and after six negative socket-query attempts, with zero
capture drops/errors and no negative nonce observed. The synthetic controls
calibrate capture; they do not establish a successful TCP DNS transaction or
universal future escape prevention. On 18 September, a termination-resistant
dummy was removed in 10.174 seconds by the external deadline/cleanup path;
the refreshed checks passed again on 19 September. These did not test AWS
credential expiration or abrupt launcher death. Detailed build, network and
cleanup receipts remain private in the dedicated runtime.

Captioneer IAM retirement is complete, with no replacement roles. This did not
delete application storage, databases or other workload resources, reconcile
archived Terraform state, or change keys, MFA, runtime configuration or GitHub
environments. The isolated credential handoff and first model-driven inventory
task are now verified. Existing host Codex/OpenClaw processes remain outside
this runtime; named-project write access and their migration remain separate work.
