# AWS access

As of 18 September 2026, AWS CLI v2 is installed on this machine. The existing
`default` profile uses an `aws login` session and region
`us-east-1`. Three SSO profiles are also configured; authentication and the new
restricted permission sets remain pending. After renewal, STS verified Cambridge TCG and the selected inventory
completed. The active principal is IAM user `YuCheung` with AdministratorAccess;
it is not a restricted inventory identity. See the [IAM review](IAM_REVIEW_2026-09-17.md)
and [agent credential model](AGENT_ACCESS.md).

| Account alias | Documented account ID | Verification |
| --- | --- | --- |
| `cambridge-tcg` | `034362054546` | STS identity and selected metadata verified on 17 September 2026. |
| `rewardspro` | `043509841549` | Documented; not yet verified with a current session. |

Account aliases belong to this repository. They are not AWS CLI profile names,
and neither a profile name nor a historical document proves the active account.

## Refresh and verify the existing login when needed

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

Cambridge TCG already has IAM Identity Center in `us-east-1`, with Admin,
PowerUser and ReadOnly permission sets. The owner's portal URL is configured in
`cambridge-human-admin`, `cambridge-agent-inventory` and `cambridge-iam-audit`.
The first selects existing AdministratorAccess; the other two depend on the
[unexecuted access foundation](../infrastructure/agent-access/README.md).
Complete the human SSO login first:

```sh
aws sso login --profile cambridge-human-admin
aws sts get-caller-identity --profile cambridge-human-admin --region us-east-1 --no-cli-pager
```

These profiles are on the human launcher; they must not be copied into an
isolated agent. The SSO directory region and resource region need not be the same.
See [AWS IAM Identity Center CLI configuration](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html).

### If the ordinary AWS password does not work

IAM users and IAM Identity Center users have separate credentials, even when
their usernames match. The existing `aws login` IAM session does not sign the
user into Identity Center. In the access portal, enter the SSO username, choose
**Next**, then **Forgot password** to request a reset.
[AWS portal password reset](https://docs.aws.amazon.com/singlesignon/latest/userguide/resetpassword-accessportal.html).

An administrator already signed into the AWS console can open **IAM Identity
Center → Users → the existing user → Reset password**. Verify the listed email
before sending reset instructions. This console procedure applies to the
Identity Center directory; external-provider or Active Directory passwords must
be reset at their provider. Passwords cannot be retrieved from the inventory API.
[AWS administrator reset procedure](https://docs.aws.amazon.com/singlesignon/latest/userguide/reset-password-for-user.html).

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
The [proposed inventory policy](../policies/README.md) is unattached and adds no
permission grants. It omits STS from its allows because STS identity
inspection itself does not require an explicit allow, but it still requires
usable credentials. See [GetCallerIdentity](https://docs.aws.amazon.com/cli/latest/reference/sts/get-caller-identity.html).
Access denied for a service is missing coverage, not an empty account.

Keep credentials, authorization URLs/codes, tokens, CLI caches and private keys
outside Git. Do not copy another project's secrets or commit `~/.aws` files.
Generated inventory belongs in ignored `inventory/local/`; review any manually
written summary before committing it. The collector requests no Secrets Manager
values, bucket objects or database data. Lambda `ListFunctions` can nevertheless
return environment values to the CLI before its local query excludes them.
Remove that grant and omit that service if the runtime must never receive such
configuration. IAM policy review needs separate permissions from inventory.
