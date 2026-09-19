# AWS infrastructure

A shared home for understanding and operating AWS across the projects in
`cambridgetcg`. This repository is **private**.

It starts with an account registry, a map of existing infrastructure ownership,
a repeatable read-only inventory command, and operating runbooks. Existing
application repositories continue to own their Terraform, SAM and deployment
scripts. New shared infrastructure can be added here when its account, state
and responsibilities are defined.

The [17 September IAM review](docs/IAM_REVIEW_2026-09-17.md) confirms live access
to Cambridge TCG and records the original GitHub role-trust exposure. All five
Captioneer IAM roles were [retired and verified absent](docs/CAPTIONEER_CLEANUP.md)
on 18 September. See
[agent access](docs/AGENT_ACCESS.md) for credential handling and the proposed
separation between discovery, deployment and administration.

The [18 September role map](docs/IAM_ROLE_MAP_2026-09-18.md) covers the 133 roles
preserved during the rebuild. The deployed
[access foundation](infrastructure/agent-access/README.md) adds two scoped SSO
roles, bringing the total to 135. Both named profiles passed live identity and
permission checks with one-hour sessions. The [agent flow](docs/ACCESS_REBUILD.md)
defaults to read-only discovery; named-project changes need their own scoped
identity. On 19 September 2026, the dedicated Mac executor completed its first
inventory task through the maintained routine CLI, with a separate Codex
subscription login, verified scoped AWS identity and successful cleanup.
Follow the [Mac agent flow](docs/MAC_AGENT_FLOW.md). Existing host Codex/OpenClaw
sessions are not automatically moved into that runtime.

## Start here

Requirements: macOS or Linux, Python 3.11+, Git, and AWS CLI v2 for authenticated reads.
Offline plans and tests need no AWS credentials; the tests also use Git.

```sh
make check
python3 scripts/aws_inventory.py accounts
make inventory-plan
```

The plan prints the selected account, regions and read commands without
contacting AWS. The default inventory workflow selects only the eight reads in
the deployed inventory tier. After completing SSO authorization:

```sh
aws sso login --profile cambridge-agent-inventory
python3 scripts/aws_inventory.py identity --profile cambridge-agent-inventory
make inventory-scan
```

No administrator fallback is used if scoped access is unavailable. These host
commands do not isolate the process from other local credentials; autonomous
tasks need the [isolated executor](infrastructure/agent-executor/README.md).
See [access and authentication](docs/ACCESS.md) for the separate human login.

Every scan first checks the actual STS account against the chosen registry
entry. A wrong account stops before resource collection. An inaccessible
service is recorded as unavailable, not as an empty account. Inventory output
stays under ignored `inventory/local/`, with private file permissions.

Narrow a scan when useful:

```sh
python3 scripts/aws_inventory.py scan --account rewardspro --profile YOUR_PROFILE \
  --region eu-north-1 --service lambda --service dynamodb --service sqs
```

## What connects to what

```mermaid
flowchart TB
  Operator["Operator or agent"] --> Repo["aws-infra · accounts, ownership, runbooks"]
  Repo --> CLI["Read-only inventory CLI"]
  CLI --> STS["STS · verify selected account"]
  STS --> APIs["Selected AWS service APIs and regions"]
  APIs --> Local["Local inventory · excluded from Git"]
  Repo --> Owners["Existing infrastructure owners"]
  Owners --> Commerce["Commerce / RewardsPro · monorepo"]
  Owners --> Pricing["Pricing backend · SAM"]
  Owners --> Cashloom["CashLoom · Terraform"]
  Owners --> Watchdog["Estate watchdog · reporting source"]
```

## Where things belong

| Path | Purpose |
| --- | --- |
| [config/accounts.json](config/accounts.json) | Named accounts, expected IDs and candidate regions. |
| [config/projects.json](config/projects.json) | Projects, existing source owners and provisional account associations. |
| [docs/OWNERSHIP.md](docs/OWNERSHIP.md) | Human-readable map of what already exists and who changes it. |
| [docs/ACCESS.md](docs/ACCESS.md) | Temporary authentication and collector permissions. |
| [docs/AGENT_ACCESS.md](docs/AGENT_ACCESS.md) | Current credential boundary and proposed agent access tiers. |
| [docs/IAM_ROLE_MAP_2026-09-18.md](docs/IAM_ROLE_MAP_2026-09-18.md) | Preserved 133-role baseline at 14:26 UTC, owners, consumers and gaps; two scoped roles were added later. |
| [docs/ACCESS_REBUILD.md](docs/ACCESS_REBUILD.md) | Confirmed migration scope, profiles and isolated agent flow. |
| [docs/MAC_AGENT_FLOW.md](docs/MAC_AGENT_FLOW.md) | How the Mac operator signs in, launches one scoped task and verifies its result. |
| [docs/IAM_REVIEW_2026-09-17.md](docs/IAM_REVIEW_2026-09-17.md) | Verified IAM findings, priorities and review limits. |
| [docs/CAPTIONEER_CLEANUP.md](docs/CAPTIONEER_CLEANUP.md) | Completed five-role retirement, dependency checks and verification. |
| [policies/](policies/README.md) | Proposed inventory permissions and historical Captioneer policy documents. |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Inventory, change, verification and recovery workflow. |
| [docs/STATUS.md](docs/STATUS.md) | Dated observations and outstanding setup. |
| [infrastructure/](infrastructure/README.md) | Boundary for shared stacks adopted into this repository. |
| [infrastructure/agent-access/](infrastructure/agent-access/README.md) | Deployed Identity Center foundation, verification record and profile example. |
| [infrastructure/agent-executor/](infrastructure/agent-executor/README.md) | Verified Mac runtime, private credential handoff, separate subscription login and first inventory task. |
| `scripts/aws_inventory.py` | Account verification, offline plans and metadata collection. |
| `tests/` | Offline tests for account selection, output and failure handling. |
| `inventory/local/` | Generated private reports; never committed. |

## Coverage and limits

The collector covers selected EC2 instance/VPC metadata, Lambda functions, RDS
instances, ECS clusters, DynamoDB tables, SQS queues, CloudFormation stack
summaries and global S3 bucket names. AWS CLI pagination remains enabled.
It does not enumerate every AWS service, every region, billing, or effective IAM
permissions. Saved reports exclude application configuration and secret fields.
Some APIs, especially Lambda listing, can return environment configuration to
the CLI before local filtering; see the [permission analysis](policies/README.md).
Output filtering is not an IAM restriction. Collection failures and unscanned
scope are part of the report.

Cambridge TCG's identity and all eight scoped inventory collections passed on
18 September. RewardsPro legacy IAM/Lambda references were separately observed
in Cambridge TCG `eu-north-1`. The historical RewardsPro account and v2 deployment
remain unverified; their candidate regions include `eu-west-2`, `eu-north-1` and
`us-east-1`. Full workload/state ownership remains separate from these selected
observations. See [current status](docs/STATUS.md).

CI runs tests and repository checks without AWS credentials. Creating or
pushing this repository provisions no AWS resources and starts no scheduled job.
