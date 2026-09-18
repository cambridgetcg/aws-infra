# ARM64 only. Inputs are pinned by immutable upstream digests; no image was built here.
FROM amazon/aws-cli:2.33.6@sha256:5b2cc3c760d978e00378e265ffa8d7a08dae1eec64c1047cfd601f49acef7d98 AS awscli
FROM python:3.13.11-slim-bookworm@sha256:a4997dee8fbd74dd6464782b13f5696140f691ff7efc0098bb0b796fce883049

COPY --from=awscli /usr/local/aws-cli /usr/local/aws-cli
RUN ln -s /usr/local/aws-cli/v2/current/bin/aws /usr/local/bin/aws
ADD --checksum=sha256:97d93e11df72d3c26772db019e6ea8bb72c246500d46b98c760839f3240355e6 https://github.com/openai/codex/releases/download/rust-v0.154.0/codex-package-aarch64-unknown-linux-musl.tar.gz /tmp/codex.tar.gz
RUN mkdir /opt/codex && tar -xzf /tmp/codex.tar.gz -C /opt/codex && \
    ln -s /opt/codex/bin/codex /usr/local/bin/codex && \
    rm /tmp/codex.tar.gz && \
    groupadd --gid 10001 executor && \
    useradd --uid 10001 --gid 10001 --home-dir /home/agent --create-home executor && \
    mkdir -p /work /run/session && chown executor:executor /work /run/session && \
    aws --version && codex --version
COPY executor.py /opt/executor.py
COPY probe_network.py /opt/probe_network.py
ENV HOME=/home/agent PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
WORKDIR /work
ENTRYPOINT ["/usr/local/bin/python3", "-I", "-B", "/opt/executor.py", "entry"]
