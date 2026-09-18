# Codex subscription authentication

The executor uses the owner's **Codex subscription through ChatGPT**. The issuer
hands over only one verified temporary AWS session. The runtime launcher reads
its own explicit `--model-auth` file; API-key handoffs and API authentication
are rejected. This implementation has offline tests; a fresh runtime login and
an end-to-end model task still need live verification.

## Create a separate runtime login

Run [login-subscription.py](login-subscription.py) under the dedicated,
unprivileged runtime account after the actual network probe passes. It uses
Codex from the verified image, with a new tmpfs `CODEX_HOME`; no host Codex
installation is required. Never copy the human's `~/.codex/auth.json`, keychain
entries, SSO refresh cache or API keys into this runtime.

For the selected `aws-agent` account, create its private destination directory
and run the staged helper in that account's clean session:

```sh
umask 077
mkdir -p /Users/aws-agent/agent-runtime/model-auth
chmod 700 /Users/aws-agent/agent-runtime/model-auth
env -i HOME=/Users/aws-agent PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin \
  /opt/homebrew/bin/python3.13 -I -B /Users/aws-agent/agent-runtime/bundle/login-subscription.py \
  --login --manifest /Users/aws-agent/agent-runtime/tasks/manifest.json \
  --network-evidence /Users/aws-agent/agent-runtime/tasks/network-probe.json \
  --output-auth /Users/aws-agent/agent-runtime/model-auth/auth.json
```

Without `--login`, the helper is offline. Its network evidence must be a recent
successful report from `executor.py probe` matching the current image, network
and proxy, including the exact proxy configuration SHA-256. The destination filename must be new; existing auth is never
overwritten. For reauthentication after a failed task, choose a new filename
and pass that path to the next `executor.py run --model-auth`.

The helper displays only the expected OpenAI device URL and one-time code.
Complete authorization with the intended subscription account. Keep the code
out of saved logs and transcripts. After success, the container stays alive for
up to 120 seconds so the helper can retrieve one bounded regular `0600`
`auth.json` through a private Docker copy. It validates ChatGPT-only auth,
atomically saves it as a private runtime-owned file, and removes the exact
login container. Stopping the container before retrieval would discard tmpfs.
No AWS session or model API key is supplied during login.

The runtime's separate login must not be used simultaneously by another CLI,
IDE or worker.
File authentication uses `CODEX_HOME/auth.json`; ChatGPT login can refresh its
tokens during use. [Official OpenAI authentication documentation](https://learn.chatgpt.com/docs/auth).

## Task handoff and refresh ownership

The trusted AWS issuer now needs only `--manifest`, the selected `--tier` and
`--handoff-fd`. Remove the former `--model-key-fd` argument. The AWS handoff must
remain a private pipe or socket. The runtime receives it on stdin and invokes:

```sh
python3 executor.py run --manifest /private/runtime/agent-manifest.json \
  --tier inventory --task /private/runtime/task.json \
  --archive /private/runtime/input.tar \
  --model-auth /Users/aws-agent/agent-runtime/model-auth/auth.json
```

The launcher requires a canonical absolute path, a private runtime-owned parent
directory and a private regular file with no symlink or hard-link aliases. It
holds a separate lock for the whole task, preventing concurrent refresh use.
The accepted cache is the known ChatGPT subset: optional `auth_mode: chatgpt`,
absent/null `OPENAI_API_KEY`, a complete token block with account ID, and optional
refresh timestamp. Extra credential modes or an unrecognized schema fail closed.

Before starting the container, the launcher atomically replaces its saved cache
with an empty ChatGPT login record. It then sends the current auth in the private
stdin envelope. Inside the container, a fresh file copy lives under tmpfs
`CODEX_HOME`; ChatGPT login and file storage are forced. The persistent runtime
auth directory is never mounted, and no model API key enters the child environment.

After successful completion, the container returns updated authentication in
the bounded private Docker stdout envelope. Docker logging and subprocess
stderr are disabled. The launcher checks the same account ID and user subject,
validates the task result, atomically saves the updated authentication with mode
`0600`, and emits only the projected result. Original and updated access,
refresh and identity tokens are removed from that output. Account continuity is
a structural check, not offline JWT signature validation or task attestation.

An interrupted task, failed refresh, invalid response or unsafe writeback leaves
the saved login empty: perform a new dedicated device-code login. Never restore
an older cache or silently switch to an API key. Serialized use and durable
refresh ownership avoid reusing a rotated token.
[Official OpenAI guidance on account-auth persistence](https://learn.chatgpt.com/docs/auth/ci-cd-auth).

The subscription login and its refresh tokens have their own lifecycle; they
do not expire when the AWS session ends. The task process can read its supplied
model tokens, and literal output redaction cannot prevent deliberate encoded
exfiltration. The dedicated account, reviewed inputs and network restrictions
remain part of the trust boundary. The proxy needs reviewed ChatGPT/authentication
endpoints, including `chatgpt.com` and `auth.openai.com`; endpoint reachability
and actual model access still require verification.
