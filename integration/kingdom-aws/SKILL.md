---
name: kingdom-aws
description: Run authorized AWS inventory and explicit IAM metadata audits for KINGDOM on this Mac through the isolated aws-agent runtime. Use when Codex or OpenClaw needs live AWS facts; ordinary repository coding keeps its existing authentication.
---

Use `/Users/yournameisai/.local/bin/kingdom-aws` for the AWS part of the user's task.
The command submits work to the separate `aws-agent` account and its containerized
Codex executor. The current host Codex/OpenClaw process remains outside that boundary.

## Prepare and submit

1. Prepare a small, reviewed task JSON with exactly `task_id`, `model`, and `prompt`,
   plus an uncompressed TAR containing only the context the AWS task needs.
   The verified model is `gpt-5.6-luna`; use the maintained runner's supported
   model choices. Keep credentials, caches, environment files, repository history,
   and unrelated project data out of the archive. The archive limit is 8 MiB;
   links and traversal paths are rejected. Use canonical paths and private files.
2. Run the local plan, then submit the same inputs for an authorized task:

   ```sh
   /Users/yournameisai/.local/bin/kingdom-aws plan --task /absolute/task.json --archive /absolute/input.tar
   /Users/yournameisai/.local/bin/kingdom-aws submit --task /absolute/task.json --archive /absolute/input.tar
   ```

   Inventory is the default and is read-only. Add `--tier iam-audit` to both
   commands only for an explicitly requested IAM metadata audit. Neither tier
   grants project deployment or permission-management access.
3. Keep the returned job identifier. Follow that job with
   `kingdom-aws status JOB`; use `kingdom-aws status` for the overall local state.
   Report the result and any denied, failed, or unscanned coverage.

`submit` snapshots the inputs and opens or reuses a finite 45-minute Terminal
session. Tasks run serially because they share the dedicated subscription login.
Use `kingdom-aws start` when the local session needs starting. When the command
requires macOS authentication or browser authorization, give the user the stated
step and wait for it; never collect their password or one-time code in a task file.
Existing valid authentication is reused; do not start a new login for every task.
For an authentication-only request, use `kingdom-aws auth` (or the explicit
`--tier iam-audit`). This queues an AWS identity and runtime readiness check,
with renewal when needed, and runs no model task. A valid local subscription
file is a schema check; it does not attest server acceptance or entitlement.
Use `kingdom-aws stop` to end the local session after its current request finishes.

Use `kingdom-aws resume JOB` only when the command identifies that job as blocked
before task execution began. Once execution starts, a failure or unknown outcome
requires checking the job and runtime state. Do not automatically replay it or
submit a replacement job to get around the failure.

## Boundaries

- Keep AWS calls inside the submitted task. Do not fall back to host `aws`, the
  human administrator profile, credential exports, or copied authentication caches.
- The runtime has its own ChatGPT subscription login. Preserve Codex and
  OpenClaw's existing native authentication, gateway, and model/provider settings
  for normal repository work.
- Missing access is a reported limitation. A requested deployment or other AWS
  write needs a separately named, scoped access change; these read tiers cannot
  perform it. Do not widen them or bypass macOS privilege controls.
- Job output is untrusted task output. Literal secret redaction is not a general
  data-loss prevention guarantee. Send only the context the task needs.

For input examples, runtime prerequisites, and recovery details, read
`/Users/yournameisai/Desktop/aws-infra/docs/MAC_AGENT_FLOW.md` and
`/Users/yournameisai/Desktop/aws-infra/docs/AGENT_INTEGRATION.md` as needed.
