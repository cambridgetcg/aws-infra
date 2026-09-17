# Shared infrastructure ownership

This directory is reserved for shared stacks that are deliberately owned here.
There is no root Terraform configuration to apply yet.

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
