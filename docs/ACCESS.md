# AWS access

As of 17 September 2026, AWS CLI v2 is installed on this machine. The only
configured profile is `default`, using an `aws login` session and region
`us-east-1`. The initial STS check failed because its OAuth grant had expired.
**No live inventory has succeeded.**

| Account alias | Documented account ID | Verification |
| --- | --- | --- |
| `cambridge-tcg` | `034362054546` | Documented; not yet verified with a current session. |
| `rewardspro` | `043509841549` | Documented; not yet verified with a current session. |

Account aliases belong to this repository. They are not AWS CLI profile names,
and neither a profile name nor a historical document proves the active account.

## Restore the existing login

Run in your own terminal and complete the browser sign-in for the intended account:

```sh
aws login --profile default
aws sts get-caller-identity --profile default --region us-east-1 --no-cli-pager
```

Compare `Account` with the selected account above and check that `Arn` identifies
the intended principal. Keep this output local. The collector's `scan` command
also checks the returned account before collecting resources. An expired session
or mismatch means no resource scan should proceed under that profile.

`aws login` uses console sign-in to obtain temporary local credentials; it is
available in AWS CLI 2.32.0 and later. Sessions eventually require another login.
See [AWS console-credential login](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html).

## When the profile uses IAM Identity Center instead

Use SSO only for an account with an existing IAM Identity Center setup. Obtain
its start/issuer URL, SSO region, account and assigned role from that setup; do
not invent these values or replace `default` merely to run inventory. To create
a separate profile and subsequently refresh its session:

```sh
aws configure sso --profile cambridge-read
aws sso login --profile cambridge-read
aws sts get-caller-identity --profile cambridge-read --region us-east-1 --no-cli-pager
```

`cambridge-read` is an example profile name, not a profile already configured on
this machine. For an already configured SSO profile, skip `configure sso`.
The SSO directory region and the resource region need not be the same.
See [AWS IAM Identity Center CLI configuration](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html).

## Collector access

The collector uses the standard AWS CLI credential chain and an explicit
`--profile`. Its metadata calls correspond to these actions:

| Purpose | Actions |
| --- | --- |
| Confirm caller | `sts:GetCallerIdentity` |
| EC2 instances and VPCs | `ec2:DescribeInstances`, `ec2:DescribeVpcs` |
| Lambda functions | `lambda:ListFunctions` |
| RDS instances | `rds:DescribeDBInstances` |
| ECS clusters | `ecs:ListClusters` |
| DynamoDB tables | `dynamodb:ListTables` |
| SQS queues | `sqs:ListQueues` |
| CloudFormation stacks | `cloudformation:ListStacks` |
| S3 buckets | `s3:ListAllMyBuckets` |

Allow the selected service reads through the existing account access mechanism.
This list is not a deployed IAM policy and adds no permission grants. STS identity
inspection itself does not require an explicit allow, but it still requires
usable credentials. See [GetCallerIdentity](https://docs.aws.amazon.com/cli/latest/reference/sts/get-caller-identity.html).
Access denied for a service is missing coverage, not an empty account.

Keep credentials, authorization URLs/codes, tokens, CLI caches and private keys
outside Git. Do not copy another project's secrets or commit `~/.aws` files.
Generated inventory belongs in ignored `inventory/local/`; review any manually
written summary before committing it. Inventory access does not require reading
application secrets, function environment values, bucket objects or database data.
