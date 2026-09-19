# Run AWS tasks on this Mac

Local Codex and OpenClaw AWS subtasks use the shared `kingdom-aws` command. It
queues reviewed task JSON and a small input archive for the separate
`aws-agent` runtime, reusing valid authentication and pausing only for the
specific access that needs attention. The new queue/authentication workflow
has **not yet passed its live check**; see [authentication automation](MAC_AUTH_AUTOMATION.md).

The underlying [routine runner](../infrastructure/agent-executor/run-task.py)
completed its first inventory task on 19 September 2026. Network/DNS checks,
separate subscription login and post-task cleanup passed. See
[the dated evidence and limits](STATUS.md).

The verified task used `gpt-5.6-luna`. The executor confirmed the pinned Cambridge
inventory role; the model reported four VPCs, expected IAM `AccessDenied` and
overall success. Model-written results are summaries to assess, not independent
attestation of every command. The separate
[fixed smoke helper](../infrastructure/agent-executor/run-inventory-smoke.py)
has offline tests but was not the live entrypoint. An isolated IAM-audit task
has not yet been live-tested.

The human issues a short AWS session from `cambridge-agent-inventory` by default; the
runtime uses its own ChatGPT subscription login. The runner waits for the
runtime's identity, source, input and network checks before issuing AWS access.
Credentials travel directly between child processes through a private pipe.
The human runner never reads the handoff or runtime model-authentication file.

## Paths and ownership

| Purpose | Location |
| --- | --- |
| Human AWS identity manifest | `/Users/yournameisai/.aws/agent-runtime/manifest.json` |
| Runtime image, network and role manifest | `/Users/aws-agent/agent-runtime/tasks/manifest.json` |
| Routine task's temporary inputs | `/Users/aws-agent/agent-runtime/tasks/submitted-*/task.json` and `input.tar` |
| Separate runtime ChatGPT login | `/Users/aws-agent/agent-runtime/model-auth/auth.json` |
| Staged runtime launcher | `/Users/aws-agent/agent-runtime/bundle/executor.py` |

Runtime files belong to UID 502. Its task and authentication directories are
private (`0700`); the files above are private (`0600`). The runtime account is
locked and has no interactive shell. Runtime setup and login use the reviewed
human-to-runtime launcher; do not try to sign into that account or copy human
AWS/Codex caches into it.

Routine submissions create a random `tasks/submitted-*` directory with private
task and archive files. The runtime removes its recorded files and directory
when the task finishes or unwinds. It does not retain input archives as history.

## Prepare task inputs

Run these commands in your own Terminal as the human account. Start in the
repository, then prepare and validate the task inputs shown in the next section:

```sh
cd /Users/yournameisai/Desktop/aws-infra
```

The runner checks the reviewed executor SHA-256 on both sides. A source change
stops the task until its new version is reviewed and staged with updated pins.
The installed command uses the reviewed, accessible Python 3.13 interpreter;
do not broaden the default Homebrew interpreter's permissions.

## Submit a routine task

The dedicated runtime is verified for inventory tasks. Preserve its
[runtime checks](../infrastructure/agent-executor/setup-local.md) and valid
subscription login. Start with a small, reviewed input bundle. This example
creates a README-only archive and an inventory task:

```sh
TASK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/aws-agent-task.XXXXXX")"
TASK_DIR="$(cd "$TASK_DIR" && pwd -P)"
mkdir "$TASK_DIR/context"
printf '%s\n' 'Reviewed context: count VPCs only; do not read application data.' > "$TASK_DIR/context/README.md"
cat > "$TASK_DIR/task.json" <<'JSON'
{
  "task_id": "count-vpcs",
  "model": "gpt-5.6-luna",
  "prompt": "Run aws sts get-caller-identity --profile task --region us-east-1 --output json --no-cli-pager and aws ec2 describe-vpcs --profile task --region us-east-1 --query 'length(Vpcs)' --output json --no-cli-pager. Return the account, role and VPC count only. Do not read credentials, application data or secrets. Report denials and failures explicitly."
}
JSON
COPYFILE_DISABLE=1 tar --format ustar -cf "$TASK_DIR/input.tar" -C "$TASK_DIR/context" README.md
chmod 600 "$TASK_DIR/task.json" "$TASK_DIR/input.tar"
~/.local/bin/kingdom-aws plan \
  --task "$TASK_DIR/task.json" --archive "$TASK_DIR/input.tar"
```

The plan command validates locally and prints input fingerprints; it starts
no child process or authentication. It requires exactly `task_id`, `model` and
`prompt`, and an uncompressed TAR of at most 8 MiB. Inputs must be owned by the
human, regular files, canonical paths without symlinks, and not writable by
other users. Archives cannot contain links, traversal paths or credential/cache
directories. Review file contents too: filename checks cannot identify secrets
inside ordinary files. Submit only the context this task needs.

After reviewing that plan, submit the same files:

```sh
~/.local/bin/kingdom-aws submit \
  --task "$TASK_DIR/task.json" --archive "$TASK_DIR/input.tar"
~/.local/bin/kingdom-aws status
```

`inventory` is the default tier. For an explicitly requested IAM metadata audit,
use `--tier iam-audit` during both planning and submission. Both tiers use exact
pinned role identities. A conflicting
`AWS_PROFILE`, inherited credential override or unavailable scoped session stops
the task; there is no administrator fallback. Native AWS SSO refresh is tried
without asking for another browser sign-in on every job.

If the job needs a worker or Mac authentication, run `kingdom-aws start`. Its
Terminal prompts for the Mac password and any necessary browser approval.
Use `kingdom-aws status JOB_ID` for the returned job ID. After a prerequisite
is resolved, `kingdom-aws resume JOB_ID` continues only jobs blocked before
execution. An actual task failure is never automatically replayed. See the
[submit/auth-needed/resume flow](MAC_AUTH_AUTOMATION.md).

The target validates the transported inputs again before signaling readiness.
Only then does the human-side issuer send AWS credentials directly into the
runtime pipe. Tasks share the dedicated subscription login and must run serially.
It also requires the latest network probe report to pass and the DNS/cleanup
receipt to match the current engine, manifest, images, proxy and networks. A
newer failed network report blocks execution; missing or changed identities
require revalidation. These private receipts record point-in-time checks, not
independent attestation. Routine tasks reuse matching proofs without a
30-minute age limit and inspect the live network configuration on every run.
After VM, proxy, network or image rebuild/restart work, rerun the operational
checks before submitting tasks, even if identifiers stayed the same. The
initial subscription-login flow keeps its stricter 30-minute receipt limit.

The runner prints the executor's bounded, redacted JSON result and returns a
failure code for failed issuance, execution, identity checks or staging cleanup.
Treat any model-written claim of task success as a summary to assess, not an
independent audit record. The 600-second task and 35-second cleanup bounds also
apply to routine submissions. Abrupt process or machine loss can require manual
inspection of the dedicated runtime before another task.

## Subscription login and recovery

The runtime reuses its separate login using the owner's Codex subscription.
Codex can refresh it during normal use. When a fresh login is necessary, its
[login helper](../infrastructure/agent-executor/subscription-auth.md)
uses the verified container and stores the resulting authentication only under
the private runtime account. The prepared Mac login flow also checks fresh,
matching network and DNS/cleanup receipts. It does not copy the human's Codex
cache, use an API key, or supply AWS credentials during login.

A successful task privately saves returned model authentication for the next
serialized task. AWS sessions expire separately; their expiry does not revoke
the ChatGPT login. After an interrupted task or failed authentication round trip,
inspect cleanup before another task. Never restore an older token cache.
The automation's fresh-login path handles only a missing file or the exact
invalidated record at `model-auth/auth.json`; other malformed or unsafe files
stop for review. Authentication values remain private to the runtime.

## What these entrypoints cover

The smoke runner accepts only its fixed inventory verification. The routine
runner provides reviewed task submission for inventory and explicit IAM audit
using the [general executor](../infrastructure/agent-executor/README.md).
The inventory flow is live-verified; IAM audit has profile-level allow/deny
checks and offline runner tests, but no isolated model-task verification yet.
Neither runner changes AWS permissions or provisions infrastructure. The shared
queue and authentication automation are an additional layer whose live check
is still pending; the existing verified runner remains its execution boundary.

The existing host Codex/OpenClaw sessions remain outside this runtime boundary.
Using these entrypoints does not redirect their AWS commands or remove their
existing human-side access.
