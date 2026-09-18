# Shared infrastructure ownership

This directory is reserved for shared stacks that are deliberately owned here.
There is no root Terraform configuration to apply yet.

The first [agent-access foundation](agent-access/README.md) was deployed and
verified on 18 September 2026 at 17:17:45 UTC. The `aws-infra-agent-access`
CloudFormation stack in Cambridge TCG `us-east-1` owns two scoped Identity Center
permission sets and two assignments to the same verified existing USER. Both
use one-hour sessions; profile checks passed at 17:18:32 UTC. This repository
owns that stack's source. Its two generated SSO roles bring the account to 135
roles; all 133 preexisting role configurations and session ceilings were
preserved. No application resource or state was imported.

The inventory tier completed all eight selected collector reads at 17:19:40 UTC:
regional metadata in `us-east-1` and global S3 bucket names, with Lambda excluded.

The [isolated executor](agent-executor/README.md) contains the whole-agent runtime,
temporary credential handoff, pinned image recipe and offline tests. It remains
inactive. SSO provisioning and host-profile checks are complete. The user
selected this Mac, but the separate runtime has not yet been created; model
authentication, network restrictions and runtime isolation still need live
verification.

Existing application definitions stay in their recorded repositories. Before
adding a shared stack, record its purpose, AWS account and regions, state owner,
deployment identity, dependencies, cost expectation, verification and rollback.
Use an isolated stack directory with an explicit account restriction.

For an existing resource, first determine whether Terraform, CloudFormation or
another owner already controls it. Preserve state and backup evidence before
any explicit transfer. Copying a `.tf` file does not transfer state ownership.

Remote-state buckets, lock configuration, IAM roles and OIDC trust are AWS
resources themselves. Add and deploy them as concrete changes when needed;
repository creation does not silently bootstrap them.
