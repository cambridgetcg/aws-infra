# Working across AWS projects

This repository records account context, resource observations and operational
ownership. Existing Terraform and SAM definitions remain in their application
repositories; see [OWNERSHIP.md](OWNERSHIP.md). Creating this repository does not
create cloud resources, move infrastructure state or schedule jobs.

## Inspect the selected scope

Start from this repository's root. Account listing and inventory planning are
offline; `plan` describes read calls, not a Terraform change plan:

```sh
python3 scripts/aws_inventory.py accounts
python3 scripts/aws_inventory.py plan --account cambridge-tcg --profile default --region us-east-1
```

After restoring the intended session using [ACCESS.md](ACCESS.md), verify the
account and perform the selected metadata reads:

```sh
python3 scripts/aws_inventory.py identity --profile default
python3 scripts/aws_inventory.py scan --account cambridge-tcg --profile default --region us-east-1
```

`identity` displays the active principal; compare its account with the registry.
`scan` performs the automatic account comparison. Use the profile verified for
that account; `default` is not assumed to belong to Cambridge. Pass repeated
`--region` and `--service` options to select a bounded scan; inspect `plan` with
the same options first. Service names are `ec2`, `vpc`, `lambda`, `rds`, `ecs`,
`dynamodb`, `sqs`, `cloudformation` and `s3`. A region default is a starting scope,
not evidence that all resources are in that region. S3 bucket listing is
account-level coverage.

The collector checks STS against the selected account record before resource
queries and saves selected metadata as `inventory/local/<UTCtimestamp>-<alias>.json`.
An explicit `--output` must also be an ignored JSON file under `inventory/local/`.
Keep generated inventory private and local. A scan's timestamp, account, regions,
services and outcomes define its coverage: denied, failed and unscanned are not
empty. Even a successful scan covers only the implemented resource types and
selected regions. It is not a billing, security or backup audit. Exit status `0`
means the selected scan completed, `2` means partial collection, and `1` means a
setup, account-verification or report-writing error.

The initial 17 September 2026 access check had an expired login grant; no live
scan was established during repository setup. Preserve that distinction until
a successful scan provides actual observations.

## Carry a named change through to completion

1. **Find the resource and its owner.** Use inventory and the ownership record
   to identify the account, region, stack/state and source repository. If ownership
   is missing, record it before treating a discovered resource as centrally managed.
2. **Prepare the change in its source repository.** Name the intended behavior,
   affected resources and verification steps. Use that repository's Terraform,
   SAM or other existing workflow. Keep state and generated plan files out of Git.
3. **Review the exact execution scope.** Check the current STS identity, account,
   region and actual Terraform plan or CloudFormation change set. Include expected
   replacements/deletions, dependency effects and a practical rollback path.
   A collector `plan` does not substitute for this review.
4. **Execute the authorized scope.** Follow the user's existing authorization and
   the owning repository's workflow. Do not add unrelated resources, permissions,
   deployments or recurring jobs because they appear useful.
5. **Verify and record the outcome.** Check deployment/stack state and the affected
   application's behavior, then refresh the relevant inventory scope. Record the
   source commit, execution time, account/region, result and remaining gaps. If
   verification fails, follow the prepared rollback and verify recovery; account
   for data/schema changes that cannot be reversed by redeploying an older build.

Do not automatically create a Terraform backend, state bucket, locking table,
IAM role or shared stack to make a workflow run. Importing existing resources or
moving state/ownership is a separately named change with its own migration and
recovery steps. The inventory collector itself has no apply, delete or deploy
path.

Run `make check` for repository changes. Tests use fixtures without AWS
credentials. Commit concise operational findings and ownership updates, not raw
cloud responses, credentials, application environment values, state, plans or
generated inventory. No scheduler or notification sender is enabled by setup.
