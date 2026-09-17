# AWS infrastructure

A shared home for understanding and operating AWS across the projects in
`cambridgetcg`. This repository is **private**.

It starts with an account registry, a map of existing infrastructure ownership,
a repeatable read-only inventory command, and operating runbooks. Existing
application repositories continue to own their Terraform, SAM and deployment
scripts. New shared infrastructure can be added here when its account, state
and responsibilities are defined.

## Start here

Requirements: macOS or Linux, Python 3.11+, Git, and AWS CLI v2 for authenticated reads. The
offline plan and tests need only Python.

```sh
make check
python3 scripts/aws_inventory.py accounts
python3 scripts/aws_inventory.py plan --account cambridge-tcg --profile default
```

The plan prints the selected account, regions and read commands without
contacting AWS. Once the AWS session is ready:

```sh
aws login --profile default
python3 scripts/aws_inventory.py identity --profile default
python3 scripts/aws_inventory.py scan --account cambridge-tcg --profile default
```

For an already configured IAM Identity Center profile, use `aws sso login
--profile YOUR_PROFILE` instead. See [access and authentication](docs/ACCESS.md).

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
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Inventory, change, verification and recovery workflow. |
| [docs/STATUS.md](docs/STATUS.md) | Dated observations and outstanding setup. |
| [infrastructure/](infrastructure/README.md) | Boundary for shared stacks adopted into this repository. |
| `scripts/aws_inventory.py` | Account verification, offline plans and metadata collection. |
| `tests/` | Offline tests for account selection, output and failure handling. |
| `inventory/local/` | Generated private reports; never committed. |

## Coverage and limits

The collector covers selected EC2 instance/VPC metadata, Lambda functions, RDS
instances, ECS clusters, DynamoDB tables, SQS queues, CloudFormation stack
summaries and global S3 bucket names. AWS CLI pagination remains enabled.
It does not enumerate every AWS service, every region, resource contents,
application configuration, secrets, billing, or effective IAM permissions.
Collection failures and unscanned scope are part of the report.

The account IDs and source definitions are **documented, not live-verified**.
The initial AWS session was expired; no successful resource inventory is claimed.
RewardsPro has conflicting historical region references, so its defaults
include `eu-west-2`, `eu-north-1` and `us-east-1` pending verification of the
separate v2 and legacy stacks and their actual account ownership.

CI runs tests and repository checks without AWS credentials. Creating or
pushing this repository provisions no AWS resources and starts no scheduled job.
