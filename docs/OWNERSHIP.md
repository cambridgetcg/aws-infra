# AWS ownership map

**Source inspection: 17 September 2026.** This map identifies existing code and
its responsibilities. AWS authentication was unavailable, so it does not claim
that each defined resource is deployed or assign live state to a new owner.

## What this repository owns

`aws-infra` owns the shared account/project registry, local metadata collector,
cross-project map and operating runbooks. An AWS resource becomes managed here
only through a concrete stack addition or explicit state/ownership transfer.

| Area | Existing source owner | Definitions and scope | Source region / state boundary |
| --- | --- | --- | --- |
| **Commerce: storefront, wholesale, admin** | [Monorepo AWS roadmap](https://github.com/cambridgetcg/Cambridge-TCG-monorepo/blob/056d52fb1e51d1aa45e2e208f84034a92f1446e2/docs/operations/aws-roadmap.md), [wholesale deploy script](https://github.com/cambridgetcg/Cambridge-TCG-monorepo/blob/056d52fb1e51d1aa45e2e208f84034a92f1446e2/apps/wholesale/infra/deploy-scraper.sh) | Application S3/SES clients, referenced RDS databases; wholesale ECR, ECS Fargate, IAM, logs and scheduled scraper. | Scraper defaults to `us-east-1`. Current database provisioning/state owner needs confirmation; roadmap describes private-network work as deferred. |
| **RewardsPro legacy serverless stack** | [Monorepo Terraform](https://github.com/cambridgetcg/Cambridge-TCG-monorepo/tree/056d52fb1e51d1aa45e2e208f84034a92f1446e2/apps/rewardspro/infrastructure/terraform); [standalone provenance](https://github.com/cambridgetcg/rewardspro-production/tree/74924b48f84f71b0fbea7ec1262b4ae65fcb1e58/infrastructure/terraform) | Lambda, SQS/DLQs, DynamoDB, exports bucket, SNS, EventBridge, IAM and monitoring. The 11 Terraform files match across both copies. | Source default `eu-north-1` / `prod`; S3 backend declaration is commented out. Actual state owner/backend is unverified. |
| **RewardsPro API v2** | [Separate Terraform stack](https://github.com/cambridgetcg/Cambridge-TCG-monorepo/tree/056d52fb1e51d1aa45e2e208f84034a92f1446e2/apps/rewardspro-api/infrastructure/terraform), [state bootstrap](https://github.com/cambridgetcg/Cambridge-TCG-monorepo/tree/056d52fb1e51d1aa45e2e208f84034a92f1446e2/apps/rewardspro-api/infrastructure/bootstrap), [runbook](https://github.com/cambridgetcg/Cambridge-TCG-monorepo/blob/056d52fb1e51d1aa45e2e208f84034a92f1446e2/apps/rewardspro-api/docs/deployment-runbook.md) | VPC/subnets/NAT, PostgreSQL RDS, ALB, ECR, ECS API/worker/migration tasks, queues, Scheduler, scaling, alarms and GitHub OIDC. | Source default `eu-west-2` / `dev`; active partial S3 backend and separate CloudFormation bootstrap. Deployment and target account unverified. |
| **Pricing / Cardforum ingestion** | [Archived pricing repository](https://github.com/cambridgetcg/tcg-pricing-backend/tree/7331a85404bc3cbf6887bcce0c787b43060cfa28/infrastructure/deploy) | SAM/CloudFormation definitions for API Gateway/Lambda, scrapers, Step Functions, S3, DynamoDB, queues and auxiliary auth/network/cache templates. | Source default `us-east-1`. Repository is archived; identify the current deployment owner before making changes. Existing RDS/VPC inputs are not proof this stack provisions them. |
| **CashLoom account baseline** | [Phase 0 Terraform](https://github.com/cambridgetcg/cashloom-aws/tree/67be52f6cfa0493d9f77592d35196da4bf8d30c5/terraform/phase0-security-baseline), [architecture](https://github.com/cambridgetcg/cashloom-aws/blob/67be52f6cfa0493d9f77592d35196da4bf8d30c5/ARCHITECTURE.md) | GuardDuty, AWS Config, CloudTrail/S3, KMS, IAM Access Analyzer/password policy and alerts. Later treasury phases are design. | Source default `us-east-1`; target account/deployment unverified. Reconcile this baseline before adding competing account-wide infrastructure. |
| **Estate watchdog** | [Inspection/report handler](https://github.com/cambridgetcg/estate-watchdog/blob/c8dfd9a1e38e88574e23fc3a40e2046400e3ed98/index.mjs), [deployment source](https://github.com/cambridgetcg/estate-watchdog/blob/c8dfd9a1e38e88574e23fc3a40e2046400e3ed98/deploy.sh) | Reads EC2/RDS exposure and snapshots plus Cost Explorer, then publishes a report to SNS. | Deployment source uses `us-east-1`; handler lists six candidate inspection regions. Actual deployment/schedule/delivery unverified. Its handler sends notifications, so the local collector does not invoke it. |

The monorepo's current GitHub metadata describes it as a mirror of
`codeberg.org/zerone-dev/Cambridge-TCG` and a Vercel build source. Follow the
project's current contribution/deployment workflow before deciding which remote
is authoritative for a change. The links above pin the inspected GitHub bytes.

## Account and region reconciliation

[accounts.json](../config/accounts.json) retains two documented account IDs;
[projects.json](../config/projects.json) records provisional associations.
Confirm them through STS plus actual stack/resource evidence. Do not infer that
RewardsPro legacy and v2 use the same account because they share a product name.

Three RewardsPro region references coexist: old local account notes say
`us-east-1`; legacy Terraform defaults to `eu-north-1`; v2 defaults to
`eu-west-2`. Those are candidate places to inspect, not confirmed live placement.
Extra regions can be selected explicitly; the registry is not an all-region
coverage claim.

## How to add an owner

Record the account, region, application, resource/stack, source commit and
deployment mechanism. Identify the actual Terraform backend/state or
CloudFormation stack and its deployment identity. Confirm dependent resources,
backup/recovery and who verifies the application after a change.

Keep a dated source or observation for each assertion. A discovered resource
with no known owner remains **unassigned** until reconciled; inventory alone
does not transfer control or establish that a copied configuration is safe to apply.

## Relationship to Zerone and other providers

The [Zerone system map](https://github.com/cambridgetcg/zerone-core/blob/6e2437ded256b761baabef75a9cca98cbcfe079b/docs/ZERONE_MAP.md)
observed Fly.io and Cloudflare deployments. Its older AWS multi-provider plan is
not evidence of an active AWS stack. Add Zerone here when an actual AWS owner or
defined stack is identified. `agenttool-infra` is a separate provider/deployment
repository; its name alone does not make it the AWS control plane.
