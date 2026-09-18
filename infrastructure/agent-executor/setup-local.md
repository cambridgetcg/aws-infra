# Dedicated runtime on this Mac — review before activation

The dedicated-account-and-VM setup on this Mac is authorized. The locked account
and its staged files were verified at 18:42 UTC on 18 September, and its separate
VM started at 18:43 UTC. Full VM inspection, container setup and runtime activation
remain pending. Keep [the executor activation requirements](README.md).

The macOS administrator-dialog attempt timed out on 18 September; the owner
confirmed no dialog appeared. A Terminal handoff then created `aws-agent`
(UID 502) and staged its files, but stopped at the final access check because
the script used nonexistent `/usr/bin/test`. The source now uses `/bin/test`
and checks that executable before any account changes. **Do not rerun creation
against this existing account.** The prepared continuation checks its exact
private identity, locked status, file hashes and actual home-access denial
before starting only the new Colima profile; it changes no existing account
attributes or staged files. The later continuation verified the real UID 502,
supplementary groups, denied read/traversal of the human home, all 14 source
hashes and the launcher's actual Python dependencies before starting the VM.
Its final metadata checker expected incorrectly capitalized Lima JSON keys and
stopped; a corrected inspection is prepared. No AWS or model credentials have
been passed to this runtime.

Read-only inspection on 2026-09-18 found Docker CLI 29.1.5, Colima 0.9.1,
Lima 2.0.3, and Python 3.14.3 already installed. No Docker server was reachable.
The existing `default` and `lounge-test` Colima profiles were stopped; preserve
both. Only the human account, `yournameisai` (UID 501, administrator), existed
outside system accounts. Its home is mode 0700. `sudo -n true` required a human
password. Those observations do not establish the state of a future runtime.

Later inspection found the default Homebrew Python executable is mode 0700 and
inaccessible to the runtime account. Use **`/opt/homebrew/bin/python3.13`** for
local runtime commands: it is Python 3.13.11 with accessible ancestry, passes
the executor tests and loads both launcher modules under the actual runtime UID.
The host launchers use Docker subprocesses and do not require host Python SSL;
their SHA-256 fallback, archive operations, entropy and nanosecond timestamp
parsing were checked. The container's TLS checks remain required. No interpreter
or Homebrew library permissions were broadened. System Python
3.9 rejects nanosecond authentication timestamps and is not a substitute.

The smallest local path is a new standard account `aws-agent`, its own Colima
profile `aws-agent`, and the whole task agent inside the guarded container.
Human SSO issuance stays in the human account. The launcher and Docker engine
run as the standard account outside the task container. The current interactive
Codex/OpenClaw processes remain outside this boundary and retain their existing
access; this setup does not reconfigure them.

## Account and files

1. **For a new account only**, review and run [bootstrap-local.py](bootstrap-local.py) in plan mode, then
   authorize its exact apply command through the human's normal macOS privilege
   prompt. It creates a **locked, non-administrator runtime identity**, not an
   interactive login: `AuthenticationAuthority=;DisabledUser;`, shell
   `/usr/bin/false`, no password, and no administrator membership. It checks the
   known human identity/home, chooses an unused UID from 502 upward, and refuses
   any existing `aws-agent` record or home. Native OpenDirectory record creation
   avoids `dscl` property upserts; full attribute names are used for verification.
   It creates only the new private home and stages explicitly named reviewed files.
   It does not start a VM, change sudo rules, enable remote access, or set tokens.

   ```sh
   /opt/homebrew/bin/python3.13 -I -S -B infrastructure/agent-executor/bootstrap-local.py --plan
   sudo /opt/homebrew/bin/python3.13 -I -S -B infrastructure/agent-executor/bootstrap-local.py --apply
   ```

   The human supplies OS authentication to macOS/sudo, never to chat or a command
   argument. A failure leaves the locked partial identity/private home for
   inspection; rerunning does not overwrite it or perform automatic cleanup.
2. Verify its UID differs from 0 and 501 and it is not in `admin`. Verify it
   cannot traverse `/Users/yournameisai` or access that user's AWS, Codex,
   OpenClaw, SSH, or Docker directories. Do not add Full Disk Access, shared
   Apple accounts, administrator membership, sudo rules, or broad filesystem
   permissions. Existing Homebrew tools are readable through `/opt/homebrew`;
   no duplicate service installation is required.
3. The bootstrap stages these new-account directories, owned by `aws-agent:staff`
   and mode 0700:
   `/Users/aws-agent/.colima/aws-agent`,
   `/Users/aws-agent/agent-runtime/bundle`,
   `/Users/aws-agent/agent-runtime/proxy`, and
   `/Users/aws-agent/agent-runtime/tasks`.
   Reviewed executor source files go in `bundle`, the reviewed Squid config in
   `proxy/egress.squid.conf`, and [the profile example](setup-local.example.yaml)
   in `/Users/aws-agent/.colima/aws-agent/colima.yaml`; files are mode 0600 except
   the nonsecret proxy config, which is 0644 so Squid UID 584792 can read its
   individual read-only bind mount. The enclosing host directory remains 0700.
   The explicit file list also stages the proxy Dockerfile, proxy runtime guide,
   subscription login helper and authentication guide. No credential file is staged.

Only the proxy-config directory is intentionally shared into the VM, read-only.
Do not store tokens, manifests, task credentials, or model auth there. Colima
0.9.1 adds its own read-only cache mount when explicit mounts are used; inspect
the generated VM configuration to confirm both mount sources stay in the new
account. An empty `mounts: []` instead selects the home-directory default.
[Colima 0.9.1 mount construction](https://github.com/abiosoft/colima/blob/v0.9.1/environment/vm/lima/yaml.go#L333)
is the source for this behavior. Do not reuse either existing profile.

## Start and verify without credentials

After the account/files are reviewed, the human can run the following from a
terminal with a current sudo authentication. It starts only the new profile;
the clean environment excludes inherited model keys, AWS variables, SSH agent
settings, and alternate Docker contexts.

```sh
sudo -n -u aws-agent -H /usr/bin/env -i \
  HOME=/Users/aws-agent USER=aws-agent LOGNAME=aws-agent \
  PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin \
  /opt/homebrew/bin/colima --profile aws-agent start \
  --template=false --activate=false --ssh-config=false --ssh-agent=false
```

The locked identity's actual `sudo -u` execution and VZ startup succeeded on
18 September. For another machine, if startup requires an interactive login, stop and
review a separate **standard GUI account** setup; never automatically unlock
this identity, assign it a password, or grant it administrator privileges.
[Apple's account setup instructions](https://support.apple.com/guide/mac-help/add-a-user-or-group-mchl3e281fc9/mac)
describe that fallback. Inspect the generated Lima configuration and guest mount table: the human
home and human credential directories must be absent. Confirm SSH-agent
forwarding is disabled. Colima's private SSH connection to its VM is separate
from macOS Remote Login; this workflow does not require enabling host SSH or
general remote access.

Within the same clean `aws-agent` environment, select Docker context
`colima-aws-agent` using `docker context use colima-aws-agent`. This changes only
the new account's Docker config, which the fixed launcher later reads. Inspect
the actual server version; an installed CLI version does not prove Engine 28+
is running. Check that no other engine/context is selected before building.

Build the pinned executor from the copied bundle; Docker receives its restricted
build context, not a mount of the host home. Build/review a compatible pinned
Squid image and create the separate outbound proxy network and isolated internal
network described in [README.md](README.md). Set the proxy config bind source
and manifest `proxy_identity.config_path` to
`/Users/aws-agent/agent-runtime/proxy/egress.squid.conf`, the path shared into
the VM. Store private manifests and tasks outside that mounted directory.

Before passing any credentials, verify image versions/layout, exact network and
proxy evidence, absence of host mounts/sockets in the task container, denied
access to human paths, and all positive/negative network probes. Treat missing
listeners, failed positive controls, or incomplete probes as inconclusive.
Record the resulting image/container IDs and config fingerprint for the runtime
manifest. No automatic startup, scheduled tasks, or LaunchAgents are needed.

## Local handoff, without a host SSH server

Once those checks pass, complete the scoped SSO login in the **human** account
and fill the exact generated role ARN/RoleId in both private manifests. Follow
[subscription-auth.md](subscription-auth.md) to complete a fresh ChatGPT login
for the runtime in a private, runtime-owned credential directory. The task uses
subscription authentication, with no API-key fallback. Do not copy human Codex
auth caches or transfer keys found in the human process environment.

For a local task, replace the README's SSH transport with a local pipe to the
standard account. Authenticate sudo separately in the human terminal before
the pipeline; `-n` deliberately fails rather than reading a password from the
credential stream. Example, after paths and model auth are prepared:

```sh
/opt/homebrew/bin/python3.13 infrastructure/agent-executor/executor.py issue \
  --manifest /private/operator/agent-manifest.json --tier inventory \
  --handoff-fd 3 3>&1 1>/dev/null |
sudo -n -u aws-agent -H /usr/bin/env -i \
  HOME=/Users/aws-agent USER=aws-agent LOGNAME=aws-agent \
  PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin \
  /opt/homebrew/bin/python3.13 /Users/aws-agent/agent-runtime/bundle/executor.py run \
  --manifest /Users/aws-agent/agent-runtime/tasks/manifest.json --tier inventory \
  --model-auth /Users/aws-agent/agent-runtime/model-auth/auth.json \
  --task /Users/aws-agent/agent-runtime/tasks/task.json \
  --archive /Users/aws-agent/agent-runtime/tasks/input.tar
```

Use the actual private runtime authentication path created by the subscription
guide. Its directory is 0700 and `auth.json` is 0600; neither belongs in Git or
the VM's proxy-config mount. The launcher serializes tasks and preserves updated
subscription tokens; a failed credential round trip requires a fresh login.
The task sees only its short scoped AWS session and runtime subscription login. It
cannot access the operator's issuer, sudo session, home, or Docker socket through
the container's filesystem. Actual network isolation still depends on the
verified runtime controls. After the task, the container is removed; credentials
expire normally. Stop only profile `aws-agent` under its owning account when
finished. Leave the human's existing profiles and applications unchanged.

Remaining activation steps are complete VM inspection, actual image/proxy builds
and isolation probes, and fresh task model authentication. A temporary foreground
setup session is prepared with a fixed list of reviewed, credential-free actions
and private receipts. It does not install a service or change sudo rules. Human
OS authentication is still needed to enter that session; browser SSO login alone
cannot satisfy that requirement.
