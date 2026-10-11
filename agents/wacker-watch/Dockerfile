# Dockerfile for the Wacker-Watch eBPF collector
# - Builds a Python-based container on Ubuntu 24.04 with BCC + Prometheus client
# - Designed to run as a non-root user; the container must still be started
#   with specific kernel capabilities to load eBPF programs (see run notes).
# - Build context is this directory: agents/wacker-watch
#   docker build -t wacker-watch:latest agents/wacker-watch

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Install runtime/build deps (keep minimal)
# NOTE: the BCC Python bindings come from python3-bpfcc. The `bcc` package on
# PyPI is unmaintained and does not build against Python 3.12 (Ubuntu 24.04).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
	 python3 python3-pip python3-setuptools python3-venv python3-bpfcc \
	 bpfcc-tools libbpfcc-dev llvm clang ca-certificates procps iproute2 \
 && rm -rf /var/lib/apt/lists/*

# Create a non-root user to run the collector.
# NOTE: ubuntu:24.04 already ships an "ubuntu" user at uid 1000, so the
# collector uses 1001 to stay deterministic.
RUN useradd --create-home --shell /bin/bash --uid 1001 wacker

WORKDIR /app

# Copy source into the image
COPY cmd ./cmd
COPY bpf ./bpf

# Install Python deps (BCC itself comes from python3-bpfcc above)
RUN pip3 install --no-cache-dir --break-system-packages prometheus_client

# Fix permissions
RUN chown -R wacker:wacker /app

USER wacker

ENV PATH="/home/wacker/.local/bin:${PATH}"

# Expose the metrics port (see WACKER_METRICS_PORT in cmd/wacker_watch.py)
EXPOSE 8001

# Default command - run the collector. NOTE: Loading eBPF requires privileges
# from the host; run the container with the capabilities shown below.
ENTRYPOINT ["python3", "cmd/wacker_watch.py"]

# Run notes (not enforced by the image):
# IMPORTANT: eBPF requires features provided by a native Linux kernel. WSL
# (Windows Subsystem for Linux) does not provide a full host kernel environment
# for loading eBPF programs from containers - do not rely on WSL for eBPF demos.
# Run this image on a native Linux host (bare-metal or VM) with a compatible
# kernel. To allow the container to load eBPF programs, start it with extra
# caps and mount the host's /sys/fs/bpf when necessary. Example:
#
#    docker build -t wacker-watch:latest agents/wacker-watch
#    docker run --rm -it \
#      --cap-add=SYS_ADMIN --cap-add=SYS_PTRACE --cap-add=CAP_BPF \
#      --security-opt seccomp=unconfined \
#      -v /sys/fs/bpf:/sys/fs/bpf:rw \
#      -v /lib/modules:/lib/modules:ro \
#      --network host \
#      wacker-watch:latest
#
#  - Alternatively run the collector on the host (recommended for demos) and use
#    this image only for packaging or for environments where the host grants the
#    container necessary capabilities.
#  - From the repository root the same run is available as:
#      make agent-up / make agent-down
