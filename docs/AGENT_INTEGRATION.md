# Codex and OpenClaw AWS integration on this Mac

Both agents use `kingdom-aws` to submit authorized AWS subtasks to the existing
isolated runtime. Repository editing, tests, and other normal development work
continue through each agent's native tools and authentication. Installing the
skill does not isolate the host agent or change either product's model/provider.

The maintained command is
[`infrastructure/agent-executor/mac-agent.py`](../infrastructure/agent-executor/mac-agent.py),
exposed as `/Users/yournameisai/.local/bin/kingdom-aws`. Its commands are:

| Command | Purpose |
| --- | --- |
| `plan --task JSON --archive TAR [--tier inventory\|iam-audit]` | Validate explicit inputs locally. |
| `submit --task JSON --archive TAR [--tier inventory\|iam-audit]` | Snapshot inputs, queue one task, and open or reuse the finite Terminal session. |
| `status [JOB]` | Inspect the local session or one job's progress and result location. |
| `resume JOB` | Continue only a job blocked before task execution began. |
| `start` | Start the finite local Terminal session when needed. |
| `auth [--tier inventory\|iam-audit]` | Queue identity/runtime checks and renew authentication when needed, without running a model task. |
| `stop` | End the local session after its current request finishes. |

The default inventory tier is read-only. IAM metadata review requires the explicit
`iam-audit` tier. Project deployment and IAM administration are separate scopes;
neither is inferred from a KINGDOM coding task. Keep the source-owning repository
responsible for its infrastructure changes.

The Terminal session lasts at most 45 minutes. macOS password entry and browser
approval remain human steps when authentication needs renewal. Valid scoped SSO
and dedicated ChatGPT authentication are reused. The command must report a
missing prerequisite rather than falling back to the human administrator cache.
It does not grant passwordless sudo or make host AWS access safe for an agent.

The `auth` command checks the selected AWS role with STS and checks the dedicated
subscription file's local schema, current runtime proofs, and clean state. It
can prepare a missing login or quarantine only the exact invalidation marker
written by the executor. Valid or unfamiliar authentication files are preserved.
It does not test Codex server acceptance or subscription entitlement. Those can
still fail during a later model task, which must not be automatically replayed.

Tasks are serialized. Credentials remain in the existing private handoff and
runtime paths; no credential value belongs in a prompt, job file, skill, or log.
Only pre-execution blocks are resumable. After execution starts, inspect a failed
or unknown outcome before deciding on further work; never silently replay it.
See [the task flow](MAC_AGENT_FLOW.md) for input schema, runtime checks, and limits.

## Local installation dependencies

The command's local installation also requires these reviewed helper sources
under `/Users/yournameisai/.aws/agent-runtime/automation/support/`:

| File | Pinned SHA-256 | Purpose |
| --- | --- | --- |
| `refresh-proofs.py` | `bd385fb96e4cf43413aa10a36de856c2a9f6d4e22bc4d76636e336cc3ea054f3` | Refresh the existing runtime's credential-free network/DNS and cleanup evidence. |
| `login-subscription.py` | `50594c79e0f3da278a99ebe6224a99e5970c2ad5f134ee80a85e4e1cd138848d` | Run the separately reviewed device-login flow with fresh matching evidence. |

These are private installation support files, not authentication caches. Preserve
them with the local installation; the repository checkout alone does not provide
them. Missing files or changed fingerprints stop the request. The maintained
[`runtime-auth.py`](../infrastructure/agent-executor/runtime-auth.py) performs
the runtime-only schema check and exact-marker recovery. None of these helpers
grants extra AWS permissions or changes the active model/provider of either host agent.

## One shared skill

The maintained skill is [integration/kingdom-aws/SKILL.md](../integration/kingdom-aws/SKILL.md).
Install its directory at `/Users/yournameisai/.agents/skills/kingdom-aws`; a symlink
to the maintained directory keeps one source of truth. Both products support
this personal skill root. OpenClaw's installed 2026.6.11 loader was also inspected
directly; its personal skill source is `~/.agents/skills`.

Codex supports implicit selection and explicit `$kingdom-aws`. OpenClaw supports
implicit selection and a user-invocable skill command. Use a unique skill name:
OpenClaw workspace skills can shadow a personal skill, while Codex can expose
multiple skills with the same name. After installation, inspect the skill catalog
in a new agent turn/session if it has not refreshed. A gateway/model configuration
change is not needed. [Codex skill documentation](https://developers.openai.com/codex/skills),
[OpenClaw skill discovery](https://docs.openclaw.ai/tools/skills).

OpenClaw does not load `~/.codex/skills` as a native skill root. Do not install a
second diverging copy there and assume it configures OpenClaw. Its managed
`~/.openclaw/skills` and workspace `skills/` roots are alternatives when a
particular agent's discovery settings require them. Agent skill allowlists can
still restrict visibility; inspect those before changing them. The observed
default configuration had no `agents.defaults.skills` field.

No OpenClaw `skills.entries.*.env` or `apiKey` injection is needed. Those fields
inject values into the host process and are not a credential-isolation mechanism.
[OpenClaw skill security](https://docs.openclaw.ai/tools/skills#security).

The local command is the execution authority; the skill is routing guidance.
Keep source pins, identity checks, network proofs, serialized auth refresh, and
cleanup in maintained code. Check `kingdom-aws status` for current availability;
skill discovery alone does not establish that an authenticated runtime is ready.
