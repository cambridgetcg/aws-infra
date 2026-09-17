# Initial status — 17 September 2026

| Item | Observation |
| --- | --- |
| Scope | Private, shared AWS operations repository across projects. |
| Local tooling | AWS CLI 2.33.6 is installed; Python and Git are available. |
| Local profiles | Only `default` is currently configured, with a login session and default region `us-east-1`. Historical profile names are not current configuration. |
| Authentication | STS identity lookup failed because the existing OAuth authorization grant is invalid or expired. No successful AWS identity/resource observation was obtained. |
| Known accounts | Cambridge TCG and RewardsPro IDs come from historical account notes; their present workloads and permissions remain unverified. |
| Source map | Existing application Terraform/SAM/scripts and separate CashLoom/watchdog repositories identified. See [ownership](OWNERSHIP.md). |
| IaC state | No Terraform state or plan was read, copied or imported. Current backend ownership remains to be established before adoption. |
| Cloud changes | None as part of repository creation. |

Next useful operation: refresh the intended AWS profile, verify its STS account,
then run the collector for that account. A successful single-region scan remains
limited to its reported services and regions.

Account-to-project associations are provisional. Confirm both the deployed
resource and its actual Terraform state or CloudFormation stack before moving
ownership. Source names, current account identity and live resource ownership
are different observations.
