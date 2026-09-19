# Run AWS tasks on this Mac

The [routine runner](../infrastructure/agent-executor/run-task.py) submits reviewed
task JSON and a small input archive through the separate `aws-agent` runtime.
**Its first inventory task passed on 19 September 2026 at 08:55:47.967 UTC
(09:55:47.967 BST).** Refreshed network/DNS checks, a fresh separate subscription
login and post-task cleanup all passed. The temporary setup controller closed
at 08:56:42.783 UTC; its Terminal window can be closed. See
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

## Invoke from the human Terminal

Run these commands in your own Terminal as the human account. Start in the
repository, then prepare and validate the task inputs shown in the next section:

```sh
cd /Users/yournameisai/Desktop/aws-infra
```

If the scoped AWS SSO login has expired, renew that profile and complete its
browser authorization while the CLI is waiting:

```sh
aws sso login --profile cambridge-agent-inventory --use-device-code
```

The `sudo -v` step below is the separate macOS password prompt. The runner uses `sudo -n` and
never prompts or reads a password from the credential pipe. Keep the Terminal
open. It allows 600 seconds for the task and up to 35 seconds for cleanup.
An unavailable scoped profile fails; there is no administrator-profile fallback.

The runner checks the reviewed executor SHA-256 on both sides. A source change
stops the task until its new version is reviewed and staged with updated pins.
Use the accessible Python 3.13 executable shown above; do not substitute the
default Homebrew interpreter or broaden its permissions.

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
/opt/homebrew/bin/python3.13 -I -S -B infrastructure/agent-executor/run-task.py \
  --task "$TASK_DIR/task.json" --archive "$TASK_DIR/input.tar"
```

The default command validates locally and prints input fingerprints; it starts
no child process or authentication. It requires exactly `task_id`, `model` and
`prompt`, and an uncompressed TAR of at most 8 MiB. Inputs must be owned by the
human, regular files, canonical paths without symlinks, and not writable by
other users. Archives cannot contain links, traversal paths or credential/cache
directories. Review file contents too: filename checks cannot identify secrets
inside ordinary files. Submit only the context this task needs.

After reviewing that plan, use the same Terminal and files:

```sh
sudo -v
/opt/homebrew/bin/python3.13 -I -S -B infrastructure/agent-executor/run-task.py \
  --task "$TASK_DIR/task.json" --archive "$TASK_DIR/input.tar" --run
```

`inventory` is the default tier. For an explicitly requested IAM metadata audit,
use `--tier iam-audit` during both validation and execution, and renew
`cambridge-iam-audit` with `aws sso login --profile cambridge-iam-audit --use-device-code`
only if needed. Both tiers use exact pinned role identities. A conflicting
`AWS_PROFILE`, inherited credential override or unavailable scoped session stops
the task; there is no administrator fallback.

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

The runtime needs a fresh, separate device-code login using the owner's Codex
subscription. Its [login helper](../infrastructure/agent-executor/subscription-auth.md)
uses the verified container and stores the resulting authentication only under
the private runtime account. The prepared Mac login flow also checks fresh,
matching network and DNS/cleanup receipts. It does not copy the human's Codex
cache, use an API key, or supply AWS credentials during login.

A successful task privately saves returned model authentication for the next
serialized task. AWS sessions expire separately; their expiry does not revoke
the ChatGPT login. After an interrupted task or failed authentication round trip,
inspect cleanup and perform a fresh runtime login. Never restore an older token
cache. Both runners use `model-auth/auth.json`; changing to a new authentication
filename requires a reviewed runner change. The existing login
helper refuses to overwrite a file, so recovery needs a reviewed runtime-side
handling of the previous invalidated file before reusing this fixed path.

## What these entrypoints cover

The smoke runner accepts only its fixed inventory verification. The routine
runner provides reviewed task submission for inventory and explicit IAM audit
using the [general executor](../infrastructure/agent-executor/README.md).
The inventory flow is live-verified; IAM audit has profile-level allow/deny
checks and offline runner tests, but no isolated model-task verification yet.
Neither runner changes AWS permissions or provisions infrastructure. Automated
reauthentication recovery remains separate work; current recovery uses the
reviewed subscription-login flow described above.

The existing host Codex/OpenClaw sessions remain outside this runtime boundary.
Using these entrypoints does not redirect their AWS commands or remove their
existing human-side access.
