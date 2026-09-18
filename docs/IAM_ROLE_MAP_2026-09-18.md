# IAM role map — 18 September 2026

**The 133-role baseline at 14:26 UTC is mapped below. None is confirmed unused, and this is not a deletion manifest.** Rebuilding agent profiles is a separate migration from replacing workload, deployment, service-linked or Identity Center roles. No AWS changes were made for this map. The later [access foundation](../infrastructure/agent-access/README.md) added two scoped SSO roles, bringing the total to 135 while preserving this baseline.

The role inventory was refreshed on 18 September at **14:24–14:26 UTC**, with 140 successful checks. Configured-consumer evidence is the separate **12:49 UTC** scan of all 17 enabled regions. The role-name and principal-identity sets match the 12:52 retirement verification; individual principal IDs and assigned-person identifiers are intentionally omitted.

## What must be preserved while access is redesigned

| Exclusive management class | Roles | Evidence / handling |
| --- | ---: | --- |
| AWS service-linked | 19 | Reserved service paths and trust; preserve service-managed control. |
| IAM Identity Center | 3 | Reserved SSO paths; preserve the existing permission-set/assignment owner. |
| Direct CloudFormation ownership | 50 | Physical-role resources returned by live stack metadata; change through their stacks. |
| State owner unreconciled | 61 | No owner established by the selected stack evidence; some have matching Terraform source or configured consumers. |
| **Total** | **133** | Categories are mutually exclusive. |

**55 roles have configured consumer, deployment or instance-profile references.** They overlap 22 of the 50 CloudFormation-owned roles, so their union is **83 roles**. Adding the 19 service-linked and three Identity Center roles gives **105 roles with one or more of these concrete preservation reasons**. The other **28 are unresolved**, not approved for deletion.

“Configured” does not mean recently invoked or currently running. The scan found zero ECS clusters, but active task definitions still reference roles. Lambda references include published versions. IAM last-use fields and missing matches are not proofs of inactivity.

## Project groups

Project grouping is separate from the management classes above. Labels marked provisional identify review buckets, not newly assigned ownership. The [project registry](../config/projects.json) contains ten source/project records; the groups below also include shared infrastructure and unresolved ownership buckets.

| Project / review group | Roles | CloudFormation-owned | With configured references |
| --- | ---: | ---: | ---: |
| AWS service-linked roles | 19 | 0 | 0 |
| IAM Identity Center | 3 | 0 | 0 |
| Shared CDK bootstrap | 10 | 10 | 1 |
| AxiePro | 16 | 13 | 9 |
| Cardforum security | 9 | 9 | 3 |
| Pricing / Cardforum SAM | 11 | 11 | 7 |
| CashLoom | 5 | 4 | 3 |
| Business ecosystem | 15 | 0 | 2 |
| SaaS marketing / AI visibility | 14 | 0 | 13 |
| RewardsPro legacy | 1 | 0 | 1 |
| Wholesale scraper | 2 | 0 | 1 |
| TradingCardPricerStack | 3 | 3 | 0 |
| Seigei | 2 | 0 | 2 |
| Kingdom status | 1 | 0 | 1 |
| YouSpeak | 1 | 0 | 1 |
| Database / shared infrastructure — owner unconfirmed | 7 | 0 | 2 |
| TCG data pipelines — provisional grouping | 14 | 0 | 9 |

## Full role inventory

Each role appears exactly once. `CFN` means a direct physical-resource ownership match; `state unverified` means the deployment/state owner is unresolved. Reference numbers count distinct configurations per kind (Lambda counts function/version rows). `—` means no match in the selected data, **not unused**.

### AWS service-linked roles (19)

Control owner: the named AWS service, established by `/aws-service-role/` paths and trust. Preserve in this migration; service-specific retirement and dependency checks would be separate work.

| Role | Type | Control owner | Configured references |
| --- | --- | --- | --- |
| `AWSServiceRoleForAccessAnalyzer` | Service-linked | AWS service | — |
| `AWSServiceRoleForAmazonGuardDuty` | Service-linked | AWS service | — |
| `AWSServiceRoleForAmazonGuardDutyMalwareProtection` | Service-linked | AWS service | — |
| `AWSServiceRoleForAmazonMQ` | Service-linked | AWS service | — |
| `AWSServiceRoleForAPIGateway` | Service-linked | AWS service | — |
| `AWSServiceRoleForAppRunner` | Service-linked | AWS service | — |
| `AWSServiceRoleForAppRunnerNetworking` | Service-linked | AWS service | — |
| `AWSServiceRoleForCostOptimizationHub` | Service-linked | AWS service | — |
| `AWSServiceRoleForDevOpsGuru` | Service-linked | AWS service | — |
| `AWSServiceRoleForEC2Spot` | Service-linked | AWS service | — |
| `AWSServiceRoleForECS` | Service-linked | AWS service | — |
| `AWSServiceRoleForElastiCache` | Service-linked | AWS service | — |
| `AWSServiceRoleForOrganizations` | Service-linked | AWS service | — |
| `AWSServiceRoleForRDS` | Service-linked | AWS service | — |
| `AWSServiceRoleForResourceExplorer` | Service-linked | AWS service | — |
| `AWSServiceRoleForServiceQuotas` | Service-linked | AWS service | — |
| `AWSServiceRoleForSSO` | Service-linked | AWS service | — |
| `AWSServiceRoleForSupport` | Service-linked | AWS service | — |
| `AWSServiceRoleForTrustedAdvisor` | Service-linked | AWS service | — |

### IAM Identity Center (3)

Control owner: the existing Identity Center instance and its permission sets. Preserve the generated identities; profile/agent redesign should use reviewed assignments and session policies through that owner, not delete these backing roles.

| Role | Type | Control owner | Configured references |
| --- | --- | --- | --- |
| `AWSReservedSSO_AdministratorAccess_70f799f553f3b581` | Human/agent federation | Identity Center | — |
| `AWSReservedSSO_PowerUserAccess_d0dd51f181850c2d` | Human/agent federation | Identity Center | — |
| `AWSReservedSSO_ReadOnlyAccess_beb7ac670481533e` | Human/agent federation | Identity Center | — |

### Shared CDK bootstrap (10)

All ten are directly owned by `CDKToolkit` stacks in `us-east-1` and `us-west-2`. They are shared deployment dependencies. The east-region CloudFormation execution role is referenced by 18 stack records. Do not replace them as if they were agent-login profiles.

| Role | Type | Control owner | Configured references |
| --- | --- | --- | --- |
| `cdk-hnb659fds-cfn-exec-role-034362054546-us-east-1` | CFN deployment execution | CFN `CDKToolkit` (us-east-1) | CFN execution: 18 |
| `cdk-hnb659fds-cfn-exec-role-034362054546-us-west-2` | CFN deployment execution | CFN `CDKToolkit` (us-west-2) | — |
| `cdk-hnb659fds-deploy-role-034362054546-us-east-1` | CDK deployment | CFN `CDKToolkit` (us-east-1) | — |
| `cdk-hnb659fds-deploy-role-034362054546-us-west-2` | CDK deployment | CFN `CDKToolkit` (us-west-2) | — |
| `cdk-hnb659fds-file-publishing-role-034362054546-us-east-1` | CDK asset publishing | CFN `CDKToolkit` (us-east-1) | — |
| `cdk-hnb659fds-file-publishing-role-034362054546-us-west-2` | CDK asset publishing | CFN `CDKToolkit` (us-west-2) | — |
| `cdk-hnb659fds-image-publishing-role-034362054546-us-east-1` | CDK asset publishing | CFN `CDKToolkit` (us-east-1) | — |
| `cdk-hnb659fds-image-publishing-role-034362054546-us-west-2` | CDK asset publishing | CFN `CDKToolkit` (us-west-2) | — |
| `cdk-hnb659fds-lookup-role-034362054546-us-east-1` | CDK lookup | CFN `CDKToolkit` (us-east-1) | — |
| `cdk-hnb659fds-lookup-role-034362054546-us-west-2` | CDK lookup | CFN `CDKToolkit` (us-west-2) | — |

### AxiePro (16)

Thirteen roles have direct CloudFormation ownership in the named AxiePro stacks; three do not. The current [AxiePro source](https://github.com/cambridgetcg/AxiePro/tree/d00bbe19d6f35a5c490b2987277d4de6024682f9/backend/infra) contains a different small CloudFormation definition (`axie-lambda-role-${Environment}`), so it does not establish the current source owner of these historical CDK stacks. Reconcile that source before changing the stack-owned roles.

| Role | Type | Control owner | Configured references |
| --- | --- | --- | --- |
| `axie-fetch-orchestrator-role` | Lambda | State unverified | Lambda: 1 |
| `axiepro-apprunner-access-role-dev` | App Runner image access | CFN `AxiePro-Security-dev` (us-east-1) | — |
| `axiepro-apprunner-ecr-access-role` | App Runner image access | State unverified | — |
| `axiepro-apprunner-instance-role` | App Runner runtime | State unverified | — |
| `axiepro-apprunner-instance-role-dev` | App Runner runtime | CFN `AxiePro-Security-dev` (us-east-1) | — |
| `axiepro-compute-ecs-execution-role-dev` | ECS task/execution | CFN `AxiePro-Compute-dev` (us-east-1) | ECS definition: 1 |
| `axiepro-compute-lambda-role-dev` | Lambda | CFN `AxiePro-Compute-dev` (us-east-1) | Lambda: 14 |
| `AxiePro-Database-dev-LogRetentionaae0aa3c5b4d4f87b0-FD4CiCLvbK8Z` | Lambda | CFN `AxiePro-Database-dev` (us-east-1) | Lambda: 1 |
| `axiepro-ecs-execution-role-dev` | ECS task/execution | CFN `AxiePro-Security-dev` (us-east-1) | — |
| `axiepro-ecs-task-role-dev` | ECS task/execution | CFN `AxiePro-Security-dev` (us-east-1) | ECS definition: 1 |
| `axiepro-lambda-execution-role-dev` | Lambda | CFN `AxiePro-Security-dev` (us-east-1) | — |
| `AxiePro-Networking-dev-CustomVpcRestrictDefaultSGCu-9PpwsxCMcaEC` | Lambda | CFN `AxiePro-Networking-dev` (us-east-1) | Lambda: 1 |
| `AxiePro-Networking-dev-VPCcloudwatchIAMRole2ED37212-TIPABDSputif` | VPC flow logs | CFN `AxiePro-Networking-dev` (us-east-1) | — |
| `AxiePro-Storage-dev-CustomS3AutoDeleteObjectsCustom-86Cd2JCgS8D7` | Lambda | CFN `AxiePro-Storage-dev` (us-east-1) | Lambda: 1 |
| `axiepro-streaming-execution-role-dev` | ECS task/execution | CFN `AxiePro-Streaming-dev` (us-east-1) | ECS definition: 1 |
| `axiepro-streaming-task-role-dev` | ECS task/execution | CFN `AxiePro-Streaming-dev` (us-east-1) | ECS definition: 1 |

### Cardforum security (9)

Live stacks `cardforum-dev-iam`, `cardforum-dev-leak-detection`, and `cardforum-dev-monitoring` own these nine roles. Matching source exists in archived [cardforum_io infrastructure](https://github.com/cambridgetcg/cardforum_io/tree/c588f9510958c518b3b1f4859d581ad27b5be238/infrastructure/lib/stacks); the three inspected stack files match the local bytes. Keep incident-response, audit and emergency access intact. The surviving CI role trusts `repo:*/cardforum:*`; confirm the actual CI owner before narrowing it, since the source repository name differs from the trust subject.

| Role | Type | Control owner | Configured references |
| --- | --- | --- | --- |
| `cardforum-BreakGlass-Emergency` | Emergency administration | CFN `cardforum-dev-iam` (us-east-1) | — |
| `cardforum-dev-app-secrets` | Lambda | CFN `cardforum-dev-iam` (us-east-1) | — |
| `cardforum-dev-cicd-secrets` | GitHub OIDC deployment | CFN `cardforum-dev-iam` (us-east-1) | — |
| `cardforum-dev-leak-detect-LeakResponseStateMachineE-NYl8ygQrl323` | EventBridge invocation | CFN `cardforum-dev-leak-detection` (us-east-1) | EventBridge: 3 |
| `cardforum-dev-leak-detect-LeakResponseStateMachineR-ocOTsRlGW8tl` | Step Functions | CFN `cardforum-dev-leak-detection` (us-east-1) | Step Functions: 1 |
| `cardforum-dev-leak-response-lambda` | Lambda | CFN `cardforum-dev-leak-detection` (us-east-1) | Lambda: 3 |
| `cardforum-dev-monitoring-SecretsAuditTrailLogsRoleF-WXXWuTn2gJuT` | CloudTrail logging | CFN `cardforum-dev-monitoring` (us-east-1) | — |
| `cardforum-dev-rotation-lambda` | Lambda | CFN `cardforum-dev-iam` (us-east-1) | — |
| `cardforum-SecurityAdmin` | Security administration | CFN `cardforum-dev-iam` (us-east-1) | — |

### Pricing / Cardforum SAM (11)

All eleven are owned by the named SAM/CloudFormation stacks. Matching resource families are defined in archived [tcg-pricing-backend deployment templates](https://github.com/cambridgetcg/tcg-pricing-backend/tree/7331a85404bc3cbf6887bcce0c787b43060cfa28/infrastructure/deploy). The current deployment maintainer needs confirmation; archival does not remove live stack ownership.

| Role | Type | Control owner | Configured references |
| --- | --- | --- | --- |
| `cardforum-migration-MigrationFunctionRole-Q5UwjkC6Hskq` | Lambda | CFN `cardforum-migration` (us-east-1) | Lambda: 1 |
| `tcg-jobs-AlertMonitorFunctionRole-W3zTbKKBcFkA` | Lambda | CFN `tcg-jobs` (us-east-1) | Lambda: 1 |
| `tcg-jobs-AnalyticsRefreshFunctionRole-rfqwxkHUxk3A` | Lambda | CFN `tcg-jobs` (us-east-1) | Lambda: 1 |
| `tcg-jobs-NotificationProcessorFunctionRole-wv8Zr80CaZbq` | Lambda | CFN `tcg-jobs` (us-east-1) | Lambda: 1 |
| `tcg-price-api-TCGPriceFunctionRole-f9wnVeZCIRDy` | Lambda | CFN `tcg-price-api` (us-east-1) | Lambda: 1 |
| `tcg-scraper-eventbridge-role-dev` | EventBridge invocation | CFN `tcg-scraper-dev` (us-east-1) | — |
| `tcg-scraper-eventbridge-role-prod` | EventBridge invocation | CFN `tcg-scraper-prod` (us-east-1) | — |
| `tcg-scraper-lambda-role-dev` | Lambda | CFN `tcg-scraper-dev` (us-east-1) | — |
| `tcg-scraper-lambda-role-prod` | Lambda | CFN `tcg-scraper-prod` (us-east-1) | — |
| `tcg-scraper-stepfunctions-role-dev` | Step Functions | CFN `tcg-scraper-dev` (us-east-1) | Step Functions: 1 |
| `tcg-scraper-stepfunctions-role-prod` | Step Functions | CFN `tcg-scraper-prod` (us-east-1) | Step Functions: 1 |

### CashLoom (5)

Four roles belong to the live `CashLoom-production` CloudFormation stack; its current source owner is unresolved here. The separate `cashloom-sec-config-role` matches [cashloom-aws Phase 0 Terraform](https://github.com/cambridgetcg/cashloom-aws/blob/67be52f6cfa0493d9f77592d35196da4bf8d30c5/terraform/phase0-security-baseline/config.tf). That Terraform state remains unreconciled. Do not collapse the application stack and account-security baseline into one owner.

| Role | Type | Control owner | Configured references |
| --- | --- | --- | --- |
| `CashLoom-production-APIHandlerServiceRole41BB65E0-Sgd3JYPZnxOO` | Lambda | CFN `CashLoom-production` (us-east-1) | Lambda: 1 |
| `CashLoom-production-DatabaseMonitoringRole576991DA-xKbZ2vNWS47M` | RDS monitoring | CFN `CashLoom-production` (us-east-1) | — |
| `CashLoom-production-LogRetentionaae0aa3c5b4d4f87b02-LudWHMphbeHI` | Lambda | CFN `CashLoom-production` (us-east-1) | Lambda: 1 |
| `CashLoom-production-SQSProcessorServiceRole2F45F2DA-z0rUYlc6YPcU` | Lambda | CFN `CashLoom-production` (us-east-1) | Lambda: 1 |
| `cashloom-sec-config-role` | AWS Config | State unverified | — |

### Business ecosystem (15)

All fifteen names match the current [business-ecosystem IAM module](https://github.com/cambridgetcg/business-ecosystem/blob/5bb0bf02149d99717adaf0ce67ea16ee7fad3ab9/infrastructure/terraform/modules/security/iam/main.tf), [VPC module](https://github.com/cambridgetcg/business-ecosystem/blob/5bb0bf02149d99717adaf0ce67ea16ee7fad3ab9/infrastructure/terraform/modules/vpc/main.tf), or [progress-tracking IAM](https://github.com/cambridgetcg/business-ecosystem/blob/5bb0bf02149d99717adaf0ce67ea16ee7fad3ab9/infrastructure/terraform/modules/progress-tracking/iam.tf). The progress roles have Lambda and Scheduler configuration references in `us-east-1`. The twelve ECS roles have no ECS-cluster consumer in this scan, but the Terraform definitions and unverified state prevent an unused verdict. VPC flow-log associations were not scanned.

| Role | Type | Control owner | Configured references |
| --- | --- | --- | --- |
| `ecosystem-dev-accounting-task` | ECS task/execution | State unverified | — |
| `ecosystem-dev-banking-treasury-task` | ECS task/execution | State unverified | — |
| `ecosystem-dev-compliance-task` | ECS task/execution | State unverified | — |
| `ecosystem-dev-contracts-legal-task` | ECS task/execution | State unverified | — |
| `ecosystem-dev-corporate-security-task` | ECS task/execution | State unverified | — |
| `ecosystem-dev-data-privacy-task` | ECS task/execution | State unverified | — |
| `ecosystem-dev-ecs-execution` | ECS task/execution | State unverified | — |
| `ecosystem-dev-entity-governance-task` | ECS task/execution | State unverified | — |
| `ecosystem-dev-insurance-task` | ECS task/execution | State unverified | — |
| `ecosystem-dev-intellectual-property-task` | ECS task/execution | State unverified | — |
| `ecosystem-dev-kyc-identity-task` | ECS task/execution | State unverified | — |
| `ecosystem-dev-tax-task` | ECS task/execution | State unverified | — |
| `ecosystem-dev-vpc-flow-logs-role` | VPC flow logs | State unverified | — |
| `ecosystem-progress-dev-lambda-role` | Lambda | State unverified | Lambda: 5 |
| `ecosystem-progress-dev-scheduler-role` | Scheduler invocation | State unverified | Scheduler: 4 |

### SaaS marketing / AI visibility (14)

Fourteen roles match archived [saas-marketing-suite Terraform](https://github.com/cambridgetcg/saas-marketing-suite/tree/d12c53bf21b9de78059aa38743377c85c797d1d5/infrastructure/terraform) and its [AI visibility modules](https://github.com/cambridgetcg/saas-marketing-suite/tree/d12c53bf21b9de78059aa38743377c85c797d1d5/ai-visibility/infrastructure/terraform). Sixty inspected local module/stack files match that remote commit. Thirteen roles have Lambda configuration references: marketing in `us-west-2`, AI visibility in `us-east-1`. Glue consumer/state ownership is unscanned. Keep marketing runtime roles separate from general agent credentials.

| Role | Type | Control owner | Configured references |
| --- | --- | --- | --- |
| `ai-vis-dev-citation-role` | Lambda | State unverified | Lambda: 1 |
| `ai-vis-dev-knowledge-role` | Lambda | State unverified | Lambda: 1 |
| `ai-vis-dev-monitor-role` | Lambda | State unverified | Lambda: 2 |
| `saas-marketing-dev-ads-ingester-role` | Lambda | State unverified | Lambda: 4 |
| `saas-marketing-dev-attribution-role` | Lambda | State unverified | Lambda: 3 |
| `saas-marketing-dev-coordination-api-role` | Lambda | State unverified | Lambda: 1 |
| `saas-marketing-dev-email-webhook-role` | Lambda | State unverified | Lambda: 4 |
| `saas-marketing-dev-fomo-ad-executor-role` | Lambda | State unverified | Lambda: 1 |
| `saas-marketing-dev-fomo-email-executor-role` | Lambda | State unverified | Lambda: 1 |
| `saas-marketing-dev-fomo-orchestrator-role` | Lambda | State unverified | Lambda: 1 |
| `saas-marketing-dev-fomo-sms-executor-role` | Lambda | State unverified | Lambda: 1 |
| `saas-marketing-dev-glue-role` | Glue | State unverified | — |
| `saas-marketing-dev-seo-alert-processor-role` | Lambda | State unverified | Lambda: 1 |
| `saas-marketing-dev-seo-rank-checker-role` | Lambda | State unverified | Lambda: 1 |

### RewardsPro legacy (1)

The role matches the [legacy Terraform declaration](https://github.com/cambridgetcg/Cambridge-TCG-monorepo/blob/056d52fb1e51d1aa45e2e208f84034a92f1446e2/apps/rewardspro/infrastructure/terraform/iam.tf). It is directly referenced by eight Lambda function/version rows in `eu-north-1` in the authenticated Cambridge TCG account. The project registry now records this observed account association. The full legacy stack and Terraform state remain unreconciled; the separate historical RewardsPro account remains unverified.

| Role | Type | Control owner | Configured references |
| --- | --- | --- | --- |
| `rewardspro-prod-lambda-execution` | Lambda | State unverified | Lambda: 8 |

### Wholesale scraper (2)

Both role names are defined by the [monorepo deployment script](https://github.com/cambridgetcg/Cambridge-TCG-monorepo/blob/056d52fb1e51d1aa45e2e208f84034a92f1446e2/apps/wholesale/infra/deploy-scraper.sh). The execution role remains referenced by active ECS task definitions, although no cluster was found. Preserve pending a deliberate scraper retirement or migration; absence of a scheduled target in the selected data is not a source/state transfer.

| Role | Type | Control owner | Configured references |
| --- | --- | --- | --- |
| `tcg-wholesale-eventbridge-ecs` | EventBridge invocation | State unverified | — |
| `tcg-wholesale-scraper-exec` | ECS task/execution | State unverified | ECS definition: 2 |

### TradingCardPricerStack (3)

All three roles are owned by the observed `TradingCardPricerStack` CloudFormation stack. The current repository/source owner was not established. No configured consumer matches in the selected scope does not make stack-owned roles safe to delete independently.

| Role | Type | Control owner | Configured references |
| --- | --- | --- | --- |
| `TradingCardPricerStack-LimitlessScraperServiceRoleD-mzGNiJCbsO64` | Lambda | CFN `TradingCardPricerStack` (us-east-1) | — |
| `TradingCardPricerStack-PriceApiServiceRole52419CE7-Qdz9SayiU1zn` | Lambda | CFN `TradingCardPricerStack` (us-east-1) | — |
| `TradingCardPricerStack-PriceFetcherServiceRole3A50D-6CT8egrbo5gj` | Lambda | CFN `TradingCardPricerStack` (us-east-1) | — |

### Seigei (2)

Two Lambda configuration references establish the current consumers. Local `~/Desktop/seigei/scripts/deploy_scheduler.sh` explicitly defines `seigei-scheduler-role`; its origin is `codeberg.org/zerone-dev/seigei`. This pass did not verify the remote revision or the autostop role source; treat source ownership as provisional.

| Role | Type | Control owner | Configured references |
| --- | --- | --- | --- |
| `seigei-autostop-lambda-role` | Lambda | State unverified | Lambda: 1 |
| `seigei-scheduler-role` | Lambda | State unverified | Lambda: 1 |

### Kingdom status (1)

Observed consumer: the `kingdom-status` Lambda. Source/state owner not established; the project label follows the concrete consumer name and is not proof that a particular KINGDOM repository owns this deployment.

| Role | Type | Control owner | Configured references |
| --- | --- | --- | --- |
| `kingdom-lambda-role` | Lambda | State unverified | Lambda: 1 |

### YouSpeak (1)

Observed consumer: the `youspeak-edge` Lambda. A current [youspeak repository](https://github.com/cambridgetcg/youspeak/tree/a46afd5fb6d0606986d30196918011163c0a2099) exists, but this pass did not find a matching IAM declaration there. Preserve the consumer and reconcile its deployment owner.

| Role | Type | Control owner | Configured references |
| --- | --- | --- | --- |
| `youspeak-lambda-role` | Lambda | State unverified | Lambda: 1 |

### Database / shared infrastructure — owner unconfirmed (7)

Types are derived from service trust and configured references, not from ownership guesses. RDS/Glue integration associations, RDS proxy configuration, monitoring and other service consumers were outside the reused dependency scan. The EC2 role is associated with one instance profile and one stopped instance; a stopped instance remains a configured dependency.

| Role | Type | Control owner | Configured references |
| --- | --- | --- | --- |
| `AuroraS3AccessRole` | RDS integration | State unverified | — |
| `EC2` | EC2 instance | State unverified | EC2 stopped: 1; Profile: 1 |
| `Glue-S3` | Glue | State unverified | — |
| `rds-auto-start-role` | Lambda | State unverified | Lambda: 1 |
| `rds-monitoring-role` | RDS monitoring | State unverified | — |
| `rds-proxy-role-1755516221904` | RDS integration | State unverified | — |
| `rds-proxy-role-1755596135935` | RDS integration | State unverified | — |

### TCG data pipelines — provisional grouping (14)

These roles are grouped for review by their observed consumers and naming, not assigned to a canonical repository. Some names are misleading: `Lambda-S3-full` is used by `cardforum-s3-freshness-checker`, and the observed `price_calculator` function uses `cardrush_scraper-1755596135935`, not the similarly named `price_calculator-*` role. Establish source and service ownership before replacements or cleanup.

| Role | Type | Control owner | Configured references |
| --- | --- | --- | --- |
| `cambridgetcg-cardmarket-archive-lambda-role` | Lambda | State unverified | Lambda: 1 |
| `cambridgetcg-price-datafeed-alert-lambda-role` | Lambda | State unverified | Lambda: 1 |
| `cardrush_scraper-1755596135935` | Lambda | State unverified | Lambda: 4 |
| `cost_calculator-1755722783852` | Lambda | State unverified | — |
| `ebay-metadata-sync-role` | Lambda | State unverified | — |
| `ebay-price-push-role` | Lambda | State unverified | — |
| `ECS-fargate-selenium` | ECS task/execution | State unverified | ECS definition: 1 |
| `Lambda-S3-full` | Lambda | State unverified | Lambda: 1 |
| `optcg-scraper-role` | Lambda | State unverified | Lambda: 1 |
| `pipeline-orchestrator-role` | Lambda | State unverified | Lambda: 1 |
| `price-history-api-role` | Lambda | State unverified | Lambda: 1 |
| `price_calculator-1755693407995` | Lambda | State unverified | — |
| `shopify-price-push-role` | Lambda | State unverified | — |
| `stock-inventory-api-role` | Lambda | State unverified | Lambda: 2 |

## Migration implications

1. Preserve the 19 service-linked roles, three Identity Center roles and existing workload/deployment identities while a new agent-access path is introduced. This map authorizes no role or permission changes.
2. Design agent login profiles and limited assignments through the existing access system. Do not use a new profile name as evidence that the agent cannot reach the current administrator login; runtime credential isolation must also be verified.
3. Treat each configured consumer as a migration dependency: establish its source/state owner, define replacement permissions, update that consumer through its owner, verify its work, and only then consider retiring an old identity. No such replacement cutover is verified here.
4. Reconcile source and deployed state before rewriting infrastructure ownership. The ten-record project registry now includes the observed IAM/source associations for business-ecosystem, saas-marketing-suite and cardforum-security, and records RewardsPro legacy under Cambridge TCG. Those associations do not establish full-stack deployment or Terraform state ownership; the separate historical RewardsPro account remains unverified.
5. Review the remaining Cardforum CI trust separately: its repository-owner wildcard remains a scoped security concern, not permission to remove incident-response or emergency-access roles. Confirm the current workflow/source before a trust migration.
6. Investigate the 28 unresolved rows and the unscanned service integrations. No blanket deletion or automatic re-creation plan follows from this inventory.

## Evidence and limits

Private evidence files under ignored `inventory/local/` are not committed:

- `E1 — 20260918T142601.699306Z-iam-roles-identity-center.json`: fresh role paths, trusts, current policy metadata, Identity Center discovery and 140 successful checks.
- `E2 — 20260918T124900.893682Z-captioneer-dependency-refresh.json`: 268 successful checks across 17 enabled regions, including all listed event buses, Lambda versions, ECS definitions, stack ownership, profiles, Scheduler and Step Functions role references.
- `E3 — 20260918T125250.602591Z-captioneer-retirement.json`: exact 133-role remainder after Captioneer retirement; its principal identities match E1.

This document joins E1’s full role set to E2’s complete projected metadata, not just the original Captioneer match filter. CloudFormation ownership comes from `AWS::IAM::Role` physical-resource matches. Terraform links demonstrate source declarations, not possession or correctness of current state.

The reused dependency scan did not inspect RDS associations/proxy/monitoring roles, VPC flow-log assignments, Glue jobs, App Runner service roles, every other service, resource policies, cross-account dependencies, static/application configuration, external CI, old stopped tasks or unreferenced inactive task definitions. It did not inspect secret values, logs or Terraform state. These gaps are material to the unresolved rows and are not converted into unused findings. No broad effective-permission or historical-compromise conclusion is made.
