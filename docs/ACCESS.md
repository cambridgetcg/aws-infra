# AWS access

As of **18 September 2026, 17:19:40 UTC**, Cambridge TCG's two restricted SSO
profiles are deployed and verified. Use `cambridge-agent-inventory` for routine
discovery and `cambridge-iam-audit` for an explicitly requested IAM review.
Both permission sets use `PT1H` sessions and deny actions outside their tier,
except caller identity inspection. See the [access rebuild](ACCESS_REBUILD.md)
and [agent credential model](AGENT_ACCESS.md).

The existing `default` profile remains an `aws login` IAM session with broad
human administrator access in `us-east-1`. `cambridge-human-admin` selects the
existing SSO AdministratorAccess permission set. Neither is an automatic
fallback when scoped access is unavailable. Host profiles do not isolate an
agent from the human's other credentials; the selected local Mac executor is
still awaiting creation and isolation checks.

| Account alias | Documented account ID | Verification |
| --- | --- | --- |
| `cambridge-tcg` | `034362054546` | Restricted SSO identities and sampled metadata access verified on 18 September 2026; earlier estate inventory remains separately dated. |
| `rewardspro` | `043509841549` | Documented; not yet verified with a current session. |

Account aliases belong to this repository. They are not AWS CLI profile names,
and neither a profile name nor a historical document proves the active account.

## Use the restricted profiles

```sh
aws sso login --profile cambridge-agent-inventory --use-device-code
python3 scripts/aws_inventory.py identity --profile cambridge-agent-inventory
make inventory-plan
make inventory-scan
```

The Make targets select the eight supported inventory actions and exclude
Lambda. IAM review uses the separate `cambridge-iam-audit` profile; it grants
34 named IAM metadata reads, including policy/trust documents and key IDs/last
use, but never secret access-key values. It does not grant Identity Center,
Organizations, CloudTrail or Access Analyzer APIs.

Live verification matched the exact generated roles and immutable role IDs in
account `034362054546`. Inventory described four VPCs and was denied IAM role
listing; IAM audit listed 135 roles and was denied VPC discovery. Exported
temporary sessions had 3,598 seconds remaining and were held only in memory.
The test did not exercise mutations or secret/data reads.

The following full restricted collector run succeeded for all eight selected
collections: EC2 instances, VPCs, RDS instances, ECS clusters, DynamoDB tables,
SQS queues and CloudFormation summaries in `us-east-1`, plus global S3 bucket
names. Lambda and other regions/services were unscanned. Private evidence is
`inventory/local/20260918T171940.627853Z-cambridge-tcg.json`.

## Refresh and verify the separate human login when needed

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
The first selects existing AdministratorAccess; the other two select the
[deployed access foundation](../infrastructure/agent-access/README.md).
The CLI's device-code authorization succeeded on 18 September. When a new
human administration session is needed:

```sh
aws sso login --profile cambridge-human-admin --use-device-code
aws sts get-caller-identity --profile cambridge-human-admin --region us-east-1 --no-cli-pager
```

Complete the browser's **AWS CLI authorization** while `aws sso login` is still
running. Signing into the access portal or resetting its password alone does
not create the CLI token. If that command times out, run it again and finish the
new authorization flow; an old browser window cannot complete the expired one.

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

The deployed inventory tier allows the eight reads above other than Lambda;
the Make targets select that scope explicitly. A direct collector scan defaults
to all supported services, so provide those service selections when bypassing
Make. The earlier [proposed inventory policy](../policies/README.md), which
includes Lambda, remains unattached and is not this deployed policy. The deployed
tiers omit STS from their allows because STS identity
inspection itself does not require an explicit allow, but it still requires
usable credentials. See [GetCallerIdentity](https://docs.aws.amazon.com/cli/latest/reference/sts/get-caller-identity.html).
Access denied for a service is missing coverage, not an empty account.

Keep credentials, authorization URLs/codes, tokens, CLI caches and private keys
outside Git. Do not copy another project's secrets or commit `~/.aws` files.
Generated inventory belongs in ignored `inventory/local/`; review any manually
written summary before committing it. The collector requests no Secrets Manager
values, bucket objects or database data. Lambda `ListFunctions` can nevertheless
return environment values to the CLI before its local query excludes them.
The deployed inventory tier excludes that grant and its routine scan omits the
service. IAM policy review uses the separate audit tier.
