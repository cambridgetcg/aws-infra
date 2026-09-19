# Authentication for Mac AWS tasks

`kingdom-aws` is the shared submission command for local Codex and OpenClaw AWS
subtasks. It uses a serialized queue and a temporary Terminal worker on this
Mac. Inventory remains the default; IAM audit requires `--tier iam-audit`.
Its first automated inventory job succeeded at 09:40:57 UTC on 19 September
2026. The user entered the Mac password; existing AWS and dedicated Codex logins
were reused without another browser approval. Automatic browser-renewal branches
have offline tests. A second authentication-only check reused the same worker
without another Mac password prompt; the worker then closed on request.
See [current evidence and limits](STATUS.md).

## Submit, inspect and continue

Prepare reviewed task JSON and an uncompressed TAR as described in the
[Mac task guide](MAC_AGENT_FLOW.md), then use the installed command:

```sh
~/.local/bin/kingdom-aws plan --task /absolute/path/task.json --archive /absolute/path/input.tar
~/.local/bin/kingdom-aws submit --task /absolute/path/task.json --archive /absolute/path/input.tar
~/.local/bin/kingdom-aws status
```

`plan` validates locally. `submit` records the selected tier and input snapshot
as a job; keep its returned job ID. An available worker processes jobs one at a
time. Submitting a job does not grant administrator access or change its tier.
Inspect one job with `kingdom-aws status JOB_ID`. A successful task's status
includes `result_file`, the private JSON path containing its redacted result.
The human queue retains input snapshots, status and results under
`~/.aws/agent-runtime/automation/jobs/`; it does not automatically prune them.
Temporary runtime input files are removed separately when the task finishes.

If a worker or Mac authorization is needed, run:

```sh
~/.local/bin/kingdom-aws start
```

This opens a Terminal worker lasting at most 45 minutes, or 10 minutes idle.
Enter the Mac password only at its Terminal password prompt. Browser authorization appears only for the
authentication that needs it. Keep that Terminal open while it is working.
The worker installs no daemon, passwordless sudo rule or background login loop.
Use `kingdom-aws stop` to close it after the current request finishes; confirm
`session_active: false` with `kingdom-aws status` before closing its window.

A job blocked **before execution** can continue after its prerequisite is fixed:

```sh
~/.local/bin/kingdom-aws resume JOB_ID
```

Resume keeps the job's reviewed inputs and tier. A failed, interrupted or
possibly started task is never automatically replayed; inspect its result and
cleanup before deliberately submitting another attempt. Browser approval alone
does not complete authentication: the corresponding CLI must finish, and the
identity/runtime checks must pass before the job can proceed.

## What refreshes automatically

| Access | Reused automatically | Human action when needed |
| --- | --- | --- |
| Mac runtime access | The current Terminal's valid sudo authorization, within the worker's finite lifetime. | Enter the Mac password in the new Terminal worker. |
| AWS inventory or IAM audit | The named profile's native SSO provider refreshes temporary credentials while its Identity Center session remains valid. | Complete AWS browser sign-in when the provider specifically reports missing or expired SSO authorization. |
| Codex subscription | The dedicated runtime login is reused; Codex refreshes it during normal use, and successful tasks privately persist the returned authentication. | Complete a fresh device-code login when runtime auth is missing or is the exact invalidated record left by an unsuccessful task. |

AWS permission-set credentials and the Identity Center portal session have
separate lifetimes. A one-hour task session does not imply a browser login every
hour. The SSO refresh cache stays with the trusted human-side issuer; tasks
receive only the selected, verified temporary role session.
[AWS SSO refresh behavior](https://docs.aws.amazon.com/sdkref/latest/guide/understanding-sso.html).

Codex supports automatic ChatGPT token refresh during use. Reuse is serialized
because multiple workers sharing a rotating login can invalidate each other's
state. This flow keeps the selected subscription and does not switch to an API
key or copy the human's Codex cache.
[Official OpenAI authentication documentation](https://learn.chatgpt.com/docs/auth#login-caching).

The live check established reuse and successful execution, not an observed token
rotation or an expired-session renewal. Those events are not inferred from a
successful job. The automated renewal paths are covered by offline tests.

## Errors that need a different response

AWS `AccessDenied`, a wrong account or role, a missing profile, a network/TLS
failure and a generic CLI failure are not proof that SSO expired. They stop or
block the job with their own reason; they never trigger administrator fallback,
permission changes, or a different authentication method. AWS return codes
alone cannot identify expired SSO: code 253 includes configuration failures,
254 covers service errors, and 255 is generic.
[AWS CLI return codes](https://docs.aws.amazon.com/cli/latest/userguide/cli-usage-returncodes.html).

For model authentication, a malformed, linked, incorrectly owned or unexpectedly
changed auth file is a validation failure, not permission to overwrite it.
Local schema validity does not prove that a remote service still accepts a
token. An actual task failure is reported without automatically relabeling it
as expired auth. There is no old-cache restoration after an uncertain refresh.

Fresh model login requires matching current runtime/network checks and recent
proofs. Routine tasks keep the existing source, identity, network and input
checks. Logs and job status contain bounded state/reason metadata and redacted
results, never token values or saved device codes.

The shared command lets both local tools submit the same kind of isolated AWS
task. It does not move their entire host sessions into the container, remove
their existing access, or expand the approved endpoint list. Named-project
writes remain a separately scoped change; isolated IAM-audit execution still
needs its own live verification.
