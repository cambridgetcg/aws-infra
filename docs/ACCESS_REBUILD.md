# AWS access rebuild — proposed 18 September 2026

**133 IAM roles remain. Rebuild agent access alongside them, then retire specific
roles after migrating their consumers.** A blanket deletion would remove service,
application, deployment and human-access identities. The [complete role map](IAM_ROLE_MAP_2026-09-18.md)
records the evidence for each role.

The user confirmed **preserve current applications, read-only agent access by
default, and temporary access to named projects when changes are needed**.
No further roles, assignments, keys or runtime settings have been changed by
this review. Three named SSO profiles have been configured locally, preserving
the existing default login. SSO authentication and provisioning are pending.
Captioneer's five-role retirement remains complete.

## What exists

The fresh IAM/Identity Center audit completed at **14:26 UTC**, with 140 checks
succeeding. Role-to-workload references use the separately dated **12:49 UTC**
17-region scan; they are evidence of configured consumers, not a new deletion gate.

| Exclusive ownership class | Roles | Treatment |
| --- | ---: | --- |
| AWS service-linked | 19 | Manage through their owning AWS services; preserve during access rebuild. |
| Identity Center generated | 3 | Manage permission sets/assignments through Identity Center. |
| CloudFormation owned | 50 | Change through the owning stacks after workload migration. |
| State/source ownership not fully reconciled | 61 | Establish owner and consumers before changing or retiring. |

55 roles have selected configured consumer references. 83 have such references
or direct CloudFormation ownership; including service-linked and Identity Center
roles brings the preservation set to 105. The other **28 are unresolved**, not
proven unused. Names, old last-use timestamps and an empty selected scan do not
establish safe deletion.

Existing human access is IAM user `YuCheung` through `aws login`. Identity Center
also exists in `us-east-1`: AdministratorAccess sessions are 8 hours; PowerUser
and ReadOnly sessions are 12 hours. The existing `default` login is preserved
alongside the three newly configured SSO profiles. AWS IAM roles, Identity Center permission sets and local CLI profiles
are different things; deleting a workload role does not rebuild a local profile.

## The new flow

```mermaid
flowchart LR
  Human["Human signs into existing Identity Center"] --> Launcher["Trusted launcher selects account, tier and task"]
  Launcher --> Session["One scoped temporary session"]
  Session --> Agent["Isolated agent executor"]
  Agent --> AWS["AWS enforces role permissions"]
  Agent --> Result["Reviewed output and verification"]
  Result --> Expiry["Session expires; task storage discarded"]
  Change["Named project change"] --> Review["Review exact resources and permissions"]
  Review --> Launcher
```

The launcher keeps the human SSO refresh token and broader profiles. The executor
receives only the selected temporary role credentials, expiration and reviewed
task inputs. It cannot request arbitrary role ARNs or run arbitrary commands on
the human host. Its session is not automatically renewed. Selecting a different
profile inside today's unrestricted host chat does not create this boundary.

| Profile on the trusted launcher | Proposed purpose | Status |
| --- | --- | --- |
| `cambridge-human-admin` | Existing SSO AdministratorAccess, selected for human administration | Configured using the owner's portal URL; sign-in pending. |
| `cambridge-agent-inventory` | New `AWSInfraInventory`: eight discovery actions, one-hour credentials | Profile configured; permission set not provisioned or assigned. |
| `cambridge-iam-audit` | New `AWSInfraIAMAudit`: 34 IAM metadata actions, one-hour credentials | Profile configured; permission set not provisioned or assigned. |
| Project deployment | Exact project/environment resources and required role passing | Define after a project and its deployment owner are selected. No generic administrator fallback. |

The [additive foundation](../infrastructure/agent-access/README.md) contains the
complete permission documents, required assignments, account/region restriction,
[profile example](../infrastructure/agent-access/aws-config.example), verification
steps and recovery procedure. Inventory excludes Lambda listing because that API
can return environment values. IAM audit includes identity and policy metadata,
not Identity Center/Organizations/CloudTrail/Access Analyzer APIs. Neither tier
is an exhaustive estate audit or a guarantee that user-entered metadata contains
no sensitive content. Both explicitly deny actions outside their tier.

A one-hour permission-set session limits the role credentials, not an SSO cache's
ability to obtain new credentials. Do not copy that cache into the executor.
The broker must verify the **exact account and generated role**, plus expiration,
before delivering a session. `aws configure export-credentials` must never be
run against `default` as a convenience fallback, or have its credential output
printed into prompts/transcripts. No credential export was performed here.
[AWS credential export](https://docs.aws.amazon.com/cli/latest/reference/configure/export-credentials.html),
[SSO role credentials](https://docs.aws.amazon.com/singlesignon/latest/PortalAPIReference/API_GetRoleCredentials.html).

## Runtime choice

The [executor bundle](../infrastructure/agent-executor/README.md) implements the
trusted issuer, separate launcher and whole Codex process described here. It
defaults to inventory, pins the generated role's account/name/immutable ID,
rejects persistent credentials and ends before expiration. Its offline tests
cover credential/identity rejection, archive handling, bounded I/O and container
controls. The image and network have not been built or exercised; the bundle is
prepared, not active. Named-project write access remains a per-project follow-up.

Use a whole executor under a separate standard OS account or a remote VM with
no access to the human home, login caches, keychain, SSH agent or host-control
sockets. A container can add restrictions, but a host agent retaining arbitrary
shell/Docker access remains a trusted administrator outside that boundary.

This Mac has Docker CLI 29.1.5, Colima 0.9.1 and Lima 2.0.3. No runtime was started
or modified. **Installed Colima 0.9.1 turns an empty/null mount list into a writable
home mount.** A dedicated profile needs an explicit nonempty task-only mount
list, and its automatically added read-only Colima cache also needs review.
Verify actual guest mounts before supplying credentials.
[Installed-version implementation](https://github.com/abiosoft/colima/blob/v0.9.1/environment/vm/lima/yaml.go#L333),
[Docker bind mounts](https://docs.docker.com/engine/storage/bind-mounts/).

For each task, use a reviewed image, non-root process, read-only root filesystem,
limited scratch storage, no privileged capabilities, no Docker/SSH sockets and
no host credential mounts. Supply a single `task` profile in private scratch
storage through an unlogged pipe. Use a clean environment, disable instance
metadata credentials and exclude other credential providers. Restrict network
access to required AWS/model endpoints and test that host/private services are
unreachable. Ordinary Docker networking alone is not an endpoint allowlist.
Scratch memory can swap to disk; do not claim that tmpfs guarantees no persistence.
[Docker run controls](https://docs.docker.com/reference/cli/docker/container/run/),
[tmpfs limits](https://docs.docker.com/engine/storage/tmpfs/).

Installed Codex is 0.154.0. Current permission profiles support filesystem deny
rules, but existing `sandbox_mode` settings can override them. Domain rules need
an active network proxy. Those profiles govern sandboxed local commands; MCP,
browser, connectors and other host-control surfaces have separate controls.
A Codex configuration change alone would not isolate unrestricted OpenClaw under
the same OS user. This review used the OpenAI Docs skill; no Codex or OpenClaw
configuration was changed. [Official OpenAI permissions documentation](https://learn.chatgpt.com/docs/permissions).

## Migration order

1. Complete sign-in at the supplied portal and match the signed-in identity to
   the intended existing directory user for each new tier. The owner supplied
   `https://ssoins-72237658457aa79e.portal.us-east-1.app.aws`; the three local
   profiles use it. The IAM login identity alone does not identify an SSO user.
2. Review and deploy the additive foundation; configure and authenticate its
   named human-launcher profiles. Preserve recovery access.
3. Build and verify the isolated executor using only its task session: correct
   role/account, allowed reads, denied out-of-scope access, no human cache or
   host-control access, and expiry without refresh.
4. Select each project's deployment owner, environment, resources and state
   backend. Add a separate narrow deployment identity and test its real workflow.
5. Migrate observed consumers through their owning stacks. Only then prepare
   exact-role retirement records, backup definitions and delete verified unused
   identities. Preserve AWS service-linked and SSO-managed ownership semantics.

The remaining `cardforum-dev-cicd-secrets` role trusts any GitHub owner with a
repository named `cardforum`. Its boundary currently has only deny statements,
so its inline grants do not demonstrate usable identity-based access. Repairing
that boundary without fixing trust could change its exposure. Treat it as a
separate source-owned change, not evidence that all IAM roles should be reset.
[Boundary evaluation](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html).

Private audit evidence is `inventory/local/20260918T142601.699306Z-iam-roles-identity-center.json`.
Runtime findings were read-only. Raw responses, principal IDs, credentials and
provider caches are excluded from this published plan. RewardsPro remains
unverified; the proposed stack is intentionally limited to Cambridge TCG.
