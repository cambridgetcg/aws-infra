# ARM64 Canonical image, registry manifest/config checked 2026-09-18.
# This is the immutable 7.2-26.04_edge build created 2026-09-17, not a moving tag.
# See proxy-runtime.md for provenance and the unexecuted runtime checks.
FROM ubuntu/squid:7.2-26.04_edge@sha256:07c74ecce295bbac325c06dc75a3e19ce4c7054bf784f521c62c59350a54d6df AS upstream
FROM upstream AS proxy

# Canonical's chiselled image provides squid-gnutls. The launcher deliberately
# requires a direct /usr/sbin/squid process, without Pebble or an init script.
COPY --from=upstream --chmod=0755 /usr/sbin/squid-gnutls /usr/sbin/squid
USER 584792:584792
WORKDIR /tmp
RUN ["/usr/sbin/squid", "-v"]
ENTRYPOINT ["/usr/sbin/squid"]
CMD ["-N", "-f", "/etc/squid/squid.conf"]
