# Dedicated Squid proxy — running and network verified

[proxy.Dockerfile](proxy.Dockerfile) adapts Canonical's ARM64 Squid image to the
executor's exact direct-process contract. The image built successfully on the
dedicated runtime at 20:04 UTC on 18 September 2026. A no-network container
verified Squid 7.2 and the image's user, entrypoint and volume configuration.
Configuration parsing, proxy startup and all 28 network checks passed by
20:46:32 UTC. DNS observation and deadline cleanup passed at 20:53:23 UTC.
Fresh subscription verification and the first scoped task remain pending.

## Verified upstream inputs

Public Docker Registry manifests and the small image configuration blob were
read on 18 September 2026; their SHA-256 values were checked locally. The selected
image is Canonical's `ubuntu/squid:7.2-26.04_edge`, published for `linux/arm64/v8`
on 17 September. It is an **edge-channel artifact**, pinned to immutable bytes;
the pin does not turn it into a stable-channel release. Local testing covers
build/version metadata and the current proxy's credential-free network behavior.
[Canonical publisher and channels](https://hub.docker.com/r/ubuntu/squid)

| Input | Digest |
| --- | --- |
| Multi-platform index | `sha256:29c318e6abfe76dab959374cb88acd6ebaff8a4e2eec023a941c7e0e84635523` |
| ARM64 manifest used by the Dockerfile | `sha256:07c74ecce295bbac325c06dc75a3e19ce4c7054bf784f521c62c59350a54d6df` |
| Upstream image configuration | `sha256:fcdf26e83a4ac465520871d62ad955d4b645912ab9134985499645a61b995d05` |

The inspected image configuration declares user `584792`, the Pebble entrypoint,
and no volumes. The reviewed [Canonical recipe](https://github.com/canonical/squid-rock/blob/64a5adbe713b9a798157208bedd4e9230f63beea/squid/7.2-26.04/rockcraft.yaml)
uses `_daemon_`, owns `/run`, `/var/log/squid` and `/var/spool/squid` as
`584792:584792`, and installs the standard Squid slice. Its
[entrypoint source](https://github.com/canonical/squid-rock/blob/64a5adbe713b9a798157208bedd4e9230f63beea/squid/7.2-26.04/entrypoint.sh)
invokes `/usr/sbin/squid-gnutls`. The derivative copies that binary to
`/usr/sbin/squid`, fixes UID/GID, and replaces Pebble with the exact required
arguments. It installs no new packages and declares no persistent volumes.
The inspected source pin is a reviewed recipe, not a verified build attestation
linking that commit to the published image.

The registry did not resolve `7.2-26.04_beta` during this check, despite the
publisher overview mentioning it. Older 6.6 images have different entrypoint and
volume metadata. Do not silently substitute them or a moving `latest` tag.

## Build and prepare the exact configuration

Run from the repository root using only the dedicated runtime account's Docker
context established by [setup-local.md](setup-local.md):

```sh
docker build --platform linux/arm64 --network none \
  -f infrastructure/agent-executor/proxy.Dockerfile \
  -t aws-agent-egress:reviewed infrastructure/agent-executor
docker image inspect aws-agent-egress:reviewed --format '{{.Id}}'
```

The build's `squid -v` must succeed and report the expected Squid/ARM64 binary.
Use the resulting **local image ID**, not the upstream manifest digest, for
`proxy_identity.image_id` and the launch command. The Dockerfile needs no local
COPY inputs; its binary comes from the pinned upstream stage.

Choose an unused, nonoverlapping RFC1918 subnet and a free proxy address in it.
Copy the reviewed [egress policy](egress.squid.conf) to
`/Users/aws-agent/agent-runtime/proxy/egress.squid.conf`, the sole host directory
shared read-only into the dedicated VM. Preserve the reviewed endpoint allowlist.
The subscription path needs the separately reviewed ChatGPT/login endpoints;
this recipe does not introduce an API-key requirement or copy a human login.

In this **operator copy**, replace the single `http_port 3128` line with
`http_port <PROXY_INTERNAL_IPV4>:3128`, using the chosen literal IP. This binds
the listener to the internal network rather than the proxy's outbound interface.
Add these operational settings without importing the distribution's permissive
`conf.d` configuration:

```squidconf
visible_hostname aws-agent-egress
cache_effective_user _daemon_
cache_effective_group _daemon_
pid_filename /run/squid.pid
cache_log /var/log/squid/cache.log
pinger_enable off
max_filedescriptors 1024
```

The PID and diagnostic log paths are placed on temporary writable storage;
the ICMP helper is disabled because the process gets no raw-network capability.
Upstream documents [PID paths](https://www.squid-cache.org/Doc/config/pid_filename/),
[administrative logging](https://www.squid-cache.org/Doc/config/cache_log/) and
[the pinger switch](https://www.squid-cache.org/Doc/config/pinger_enable/).
The existing `cache_store_log none` directive is supported in Squid 7; its
[reference](https://www.squid-cache.org/Doc/config/cache_store_log/) marks removal
in version 8. The actual build must still parse the complete configuration.

Keep the parent directory mode **0700**, owned by `aws-agent`. The policy file
contains no secrets and must be **0644**, owned by `aws-agent`, so container UID
584792 can read it. Mode 0600 under the Mac user's UID would prevent that read.
Record the canonical path and SHA-256 of this complete, reviewed runtime file;
the launcher checks both the local file and the file mounted by the VM daemon.
Never place manifests, SSO caches or subscription credentials in this directory.

## Parse before starting the proxy

Set `AWS_AGENT_PROXY_IMAGE` to the verified local `sha256:…` image ID and
`AWS_AGENT_PROXY_CONFIG` to the canonical path above. These names hold public
image/config metadata, never credentials. This validation container has no
network and only the same read-only policy bind:

```sh
docker run --rm --pull never --platform linux/arm64 \
  --network none --user 584792:584792 --read-only --cap-drop ALL \
  --security-opt no-new-privileges --ulimit core=0 --ulimit nofile=1024:1024 \
  --tmpfs /run:rw,nosuid,nodev,noexec,uid=584792,gid=584792,mode=0700,size=1m \
  --tmpfs /tmp:rw,nosuid,nodev,noexec,uid=584792,gid=584792,mode=0700,size=8m \
  --tmpfs /var/log/squid:rw,nosuid,nodev,noexec,uid=584792,gid=584792,mode=0700,size=4m \
  --tmpfs /var/spool/squid:rw,nosuid,nodev,noexec,uid=584792,gid=584792,mode=0700,size=16m \
  --mount "type=bind,src=${AWS_AGENT_PROXY_CONFIG:?},dst=/etc/squid/squid.conf,readonly" \
  --entrypoint /usr/sbin/squid "${AWS_AGENT_PROXY_IMAGE:?}" \
  -k parse -f /etc/squid/squid.conf
```

A zero parse exit code establishes syntax only. Check unexpected directives and
permission diagnostics; do not weaken the policy to make startup succeed.

## Create the two-network proxy

Use Engine server 28 or newer. Before these commands, verify the names are unused
on the dedicated engine; do not replace existing application networks or
containers. Set `AWS_AGENT_SUBNET` and `AWS_AGENT_PROXY_IP` to the reviewed
subnet/address selected above. The outbound network must contain only this proxy.

```sh
docker network create --driver bridge --ipv6=false aws-agent-outbound
docker network create --driver bridge --internal --ipv6=false \
  --subnet "${AWS_AGENT_SUBNET:?}" \
  --opt com.docker.network.bridge.gateway_mode_ipv4=isolated aws-agent-internal
docker create --pull never --platform linux/arm64 --name aws-agent-egress \
  --network aws-agent-outbound --user 584792:584792 --read-only \
  --cap-drop ALL --security-opt no-new-privileges --log-driver none \
  --ulimit core=0 --ulimit nofile=1024:1024 --pids-limit 64 --memory 256m --cpus 1 \
  --sysctl net.ipv4.ip_forward=0 --sysctl net.ipv6.conf.all.disable_ipv6=1 \
  --sysctl net.ipv6.conf.default.disable_ipv6=1 \
  --tmpfs /run:rw,nosuid,nodev,noexec,uid=584792,gid=584792,mode=0700,size=1m \
  --tmpfs /tmp:rw,nosuid,nodev,noexec,uid=584792,gid=584792,mode=0700,size=8m \
  --tmpfs /var/log/squid:rw,nosuid,nodev,noexec,uid=584792,gid=584792,mode=0700,size=4m \
  --tmpfs /var/spool/squid:rw,nosuid,nodev,noexec,uid=584792,gid=584792,mode=0700,size=16m \
  --mount "type=bind,src=${AWS_AGENT_PROXY_CONFIG:?},dst=/etc/squid/squid.conf,readonly" \
  --entrypoint /usr/sbin/squid "${AWS_AGENT_PROXY_IMAGE:?}" \
  -N -f /etc/squid/squid.conf
docker network connect --ip "${AWS_AGENT_PROXY_IP:?}" --alias egress \
  aws-agent-internal aws-agent-egress
docker start aws-agent-egress
```

No host port is published. Both networks are attached before startup, so the
internal address exists when Squid binds. The proxy resolves permitted endpoint
names using its outbound network; the agent's separate DNS restrictions do not
apply to the proxy. Direct routing through the proxy is disabled.

Inspect only necessary metadata to confirm running state, UID/GID, exact process
arguments, local image ID, both network endpoints, read-only root/config and the
four allowed tmpfs mounts. A `VOLUME`/anonymous mount or extra bind fails the
launcher contract. Record the full container ID and image ID in the private
runtime manifest, and use its current internal IPv4 address for the agent.

Run [probe_network.py](probe_network.py) without credentials in the final agent
image and exact task network configuration. Complete the remaining DNS escape,
host/private-address and external expiry/cleanup checks. Then verify the fresh,
separate subscription login through the approved endpoints and prove the
expected AWS role/read boundaries. The current recipe passed all 28 network
checks, plus DNS capture with zero drops/errors and a 10.174-second dummy
deadline/cleanup check. DNS controls were actual UDP queries and synthetic
checksummed TCP DNS packets captured on `eth0` before/after the six negative
queries; no negative nonce appeared. The TCP control calibrates capture and
does not assert successful TCP DNS transactions or universal future escape
prevention. Authentication and the first isolated AWS/model task remain pending.
Exact image/configuration and detailed evidence remain in private receipts.
Recreate the proxy and repeat the probes whenever its image or configuration
changes; a matching file hash does not attest the process's effective policy.
