# Run AWS tasks on this Mac

The [smoke runner](../infrastructure/agent-executor/run-inventory-smoke.py)
performs one fixed inventory verification. The
[routine runner](../infrastructure/agent-executor/run-task.py) submits reviewed
task JSON and a small input archive through the same separate `aws-agent` runtime.
**The isolated smoke check is still pending.** Account, VM and image checks do
not establish that subscription authentication and the full task work together.
Complete the [runtime checks](../infrastructure/agent-executor/setup-local.md)
and fresh runtime subscription login before using `--run`.

The human issues a short AWS session from `cambridge-agent-inventory` by default; the
runtime uses its own ChatGPT subscription login. The runner waits for the
runtime's identity, source, input and network checks before issuing AWS access.
Credentials travel directly between child processes through a private pipe.
The human runner never reads the handoff or runtime model-authentication file.

## Paths and ownership

| Purpose | Fixed path |
| --- | --- |
| Human AWS identity manifest | `/Users/yournameisai/.aws/agent-runtime/manifest.json` |
| Runtime image, network and role manifest | `/Users/aws-agent/agent-runtime/tasks/manifest.json` |
| Reviewed smoke task | `/Users/aws-agent/agent-runtime/tasks/inventory-smoke.json` |
| README-only task archive | `/Users/aws-agent/agent-runtime/tasks/input.tar` |
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

Run these commands in your own Terminal as the human account. First, inspect
the runner's offline plan; it does not authenticate or start a task:

```sh
cd /Users/yournameisai/Desktop/aws-infra
/opt/homebrew/bin/python3.13 -I -S -B infrastructure/agent-executor/run-inventory-smoke.py
```

If the scoped AWS SSO login has expired, renew that profile and complete its
browser authorization while the CLI is waiting:

```sh
aws sso login --profile cambridge-agent-inventory --use-device-code
```

After the runtime's network and subscription checks pass, authenticate to macOS
in that same Terminal, then run the smoke check:

```sh
sudo -v
/opt/homebrew/bin/python3.13 -I -S -B infrastructure/agent-executor/run-inventory-smoke.py --run
```

`sudo -v` is the separate macOS password prompt. The runner uses `sudo -n` and
never prompts or reads a password from the credential pipe. Keep the Terminal
open. It allows 600 seconds for the task and up to 35 seconds for cleanup.
An unavailable scoped profile fails; there is no administrator-profile fallback.

The fixed task uses `gpt-5.6-luna` and checks caller identity, counts VPCs in
`us-east-1`, and expects IAM role listing to return `AccessDenied`. Success means
the command exits zero **and** its returned task result reports these expected
outcomes. The returned model summary is not independent attestation of every
command; the pinned executor separately verifies the AWS role identity.

The runner checks the reviewed executor SHA-256 on both sides. A source change
stops the task until its new version is reviewed and staged with updated pins.
Use the accessible Python 3.13 executable shown above; do not substitute the
default Homebrew interpreter or broaden its permissions.

## Submit a routine task

Use this after the smoke check has passed. Start with a small, reviewed input
bundle. This example creates a README-only archive and an inventory task:

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

A successful task privately saves refreshed model authentication for the next
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
Neither runner changes AWS permissions or provisions infrastructure. Automated
reauthentication recovery remains separate work; current recovery uses the
reviewed subscription-login flow described above.

The existing host Codex/OpenClaw sessions remain outside this runtime boundary.
Using these entrypoints does not redirect their AWS commands or remove their
existing human-side access.
