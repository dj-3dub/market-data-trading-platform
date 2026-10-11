# Wacker-Watch (eBPF Off-CPU Duration Agent)

Part of the [Trading Observability Platform](../../README.md). Wacker-Watch is the
**kernel signal** source for the platform: it measures the interval between a
thread switching off CPU and switching back on CPU. It exports intervals over
50 µs as Prometheus metrics for comparison with application latency.

> For the project narrative, design philosophy, and interview talking points,
> see the [repository README](../../README.md). This document covers the agent
> itself.

---

## Why

Application metrics show that a request was slow. Off-CPU telemetry adds a
second signal without changing the application. It includes deliberate sleep,
blocked I/O and runnable waiting; it does not distinguish those causes.
Use it alongside CPU, I/O and runnable-wait evidence when investigating latency.

## How It Works

```text
kernel tracepoint (sched_switch)
        │  perf buffer
        ▼
bpf/wacker_watch.bpf.c   ← measures off-CPU duration, emits events over threshold
        │
        ▼
cmd/wacker_watch.py     ← BCC userland: decodes events, records histogram
        │
        ▼
Prometheus  ──►  Grafana : wacker_watch_off_cpu_duration_ns (p50/p95/p99 by thread command name)
```

1. A `sched_switch` tracepoint records the timestamp when a task goes off-CPU.
2. The same tracepoint closes the interval when that thread is scheduled back in.
3. The eBPF program submits an event through a perf buffer **only when the
   interval exceeds a threshold**, filtering out shorter intervals; high event rates can still overflow the buffer.
4. The Python userland decodes each event and records it into a Prometheus
   `Histogram` labelled by `process_name`, with custom nanosecond-scale buckets.
5. The shared Prometheus instance scrapes it; the shared Grafana instance
   visualises it.

## Key Files

| Path | Purpose |
|------|---------|
| `bpf/wacker_watch.bpf.c` | Kernel-space eBPF probe (BCC) |
| `cmd/wacker_watch.py` | Userland collector: BCC + `prometheus_client` |
| `Dockerfile` | Container image (Ubuntu 24.04, BCC, non-root) |

## Metric

```text
wacker_watch_off_cpu_duration_ns{process_name="<comm>"}
```

A histogram of off-CPU duration in nanoseconds. Buckets are tuned for
microsecond-to-millisecond off-CPU intervals rather than request latency:

```text
50µs  75µs  100µs  250µs  500µs  750µs
1ms   2.5ms 5ms    10ms    50ms   +Inf
```

`process_name` is a thread command name from the kernel's `comm` field, truncated
to 15 characters. Different threads/processes/containers can share the same name.
Percentiles describe only intervals **greater than 50,000 ns**, not the full
off-CPU distribution. A large value is not proof of scheduler contention.

The metric was renamed from `wacker_watch_sched_jitter_ns` to
`wacker_watch_off_cpu_duration_ns`. Historical series are retained in Prometheus,
but the new dashboard queries only the new metric. Rebuild the agent when
upgrading. The dashboard UID remains `wacker-watch`; custom queries using the
old name must be updated.

## Usage

All commands are run from the **repository root**.

```bash
# Install BCC / eBPF tooling (once)
make agent-deps

# Run on the host (needs root to load eBPF)
make agent-run

# Verify prerequisites without loading the probe
make agent-smoke

# Generate scheduler pressure to watch the dashboards react
make agent-stress
```

Metrics endpoint: <http://localhost:8001/metrics>

Port **8001** is used because the platform's api-gateway already owns 8000.
Override with `WACKER_METRICS_PORT` if needed.

### As a container

```bash
make agent-up     # starts the wacker-watch service (compose profile: ebpf)
make agent-down
```

Or standalone:

```bash
docker build -t wacker-watch:latest agents/wacker-watch
docker run --rm -it \
  --cap-add=SYS_ADMIN --cap-add=SYS_PTRACE --cap-add=CAP_BPF \
  --security-opt seccomp=unconfined \
  -v /sys/fs/bpf:/sys/fs/bpf:rw \
  -v /lib/modules:/lib/modules:ro \
  --network host \
  wacker-watch:latest
```

The agent sits behind the `ebpf` compose profile so that a default `make up`
still works on hosts that cannot load eBPF.

## Platform Requirements

eBPF needs a **native Linux kernel**. It will not work under WSL2 (no real host
kernel to attach probes to) and needs elevated capabilities in Docker, which is
why the service is profiled separately.

Linux kernel headers matching the running kernel are also required — mismatched
headers are the most common cause of a failed `BPF(text=...)` load.

## Security Model

Two different postures, depending on how you run it:

**On the host** (`make agent-run`) the collector runs under `sudo`, because
loading an eBPF program into the kernel is a privileged operation. The image's
non-root `wacker` user (uid 1001) is the default for the container image.

**As a container** (`make agent-up`) the service is started as uid 0 with
`SYS_ADMIN`, `SYS_PTRACE`, `BPF`, and `seccomp=unconfined`. The root UID is
required, not incidental: BCC's `TRACEPOINT_PROBE` reads the `sched_switch`
field layout from `/sys/kernel/debug/tracing/events/sched/sched_switch/format`,
which is mode `0640 root:root`, so the non-root user cannot compile the probe.
Since the container already needs those capabilities, the effective security
boundary is the capability set rather than the UID.

For a shared host, prefer running the collector on the host directly rather than
granting a container `SYS_ADMIN`.

## BCC Version Compatibility

The collector is written to work across BCC releases, which differ in how perf
buffer callbacks deliver data:

| BCC | Callback `data` | Decoding |
|-----|------------------|----------|
| 0.29 (Ubuntu 24.04) | `bytes` | `ctypes.from_buffer_copy` on the mirrored struct |
| 0.31 (Debian 13) | `int` (raw pointer) | `Table.event(data)`, which derives the field layout from the compiled module |

`cmd/wacker_watch.py` detects which is in use at runtime. Note that BCC 0.31
no longer exposes an auto-generated `event_t` attribute on the `BPF` object, so
the script carries an explicit `ctypes` mirror of the C struct as a fallback.
**If you change `struct event_t` in the BPF source, update `EventT` in
`wacker_watch.py` to match**, or the decoded fields will be garbage.

The BCC Python bindings come from the `python3-bpfcc` package. The `bcc` package
on PyPI is unmaintained and does not build against Python 3.12+.

## Container Requirements

The agent container needs three host trees mounted (all configured in
`docker-compose.yml`):

- `/sys/kernel/debug` — tracepoint field layout for `TRACEPOINT_PROBE`
- `/lib/modules` — kernel module tree
- `/usr/src` — `build` symlinks point here, so headers resolve

## Host Firewall

When the agent runs **on the host** (`make agent-run`), Prometheus scrapes it at
`host.docker.internal:8001`. That path crosses the host firewall, so port 8001
must be open for Docker traffic, e.g.:

```bash
sudo ufw allow 8001/tcp
```

If you prefer not to open a port, run the agent as a container instead
(`make agent-up`) — then Prometheus reaches it over the internal compose network
and no host firewall rule is needed.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `Failed to read BPF program` | `bpf/wacker_watch.bpf.c` not found — run from repo root, or the file is missing from the image |
| `Failed to compile BPF module` (container) | `TRACEPOINT_PROBE` cannot read the tracepoint format — confirm `/sys/kernel/debug` is mounted |
| `Unable to find kernel headers` | `linux-headers-$(uname -r)` missing, or `/usr/src` not mounted into the container |
| `incomplete definition of type 'struct tracepoint__sched__sched_switch'` | debugfs not mounted in the container |
| `BPF(text=...)` raises on load | Missing/mismatched kernel headers, or no `CAP_BPF`/`SYS_ADMIN` |
| `Failed to import bcc` | Run `make agent-deps` |
| `'BPF' object has no attribute 'event_t'` | Fixed — BCC 0.29+ needs the `Table.event()` path. Update to the current collector |
| Garbled process names / offsets | `EventT` in `wacker_watch.py` drifted from `struct event_t` in the C source |
| No metrics in Grafana | Check `make ps`; the agent is only present when started with `make agent-up` or `make agent-run` |
| `host.docker.internal:8001` target down | Host firewall blocking Docker → `sudo ufw allow 8001/tcp`, or use `make agent-up` |
| Metrics stop after a burst | Perf buffer overflow under high event rates — see ring buffer in the roadmap |
| Nothing under `process_name` | Expected on an idle host; run `make agent-stress` to generate load |

## Future Enhancements

- Ring buffer support for higher event throughput
- Per-cgroup and per-numa-node attribution
- Runnable-wait measurement before defining scheduler-delay objectives
- Historical trend analysis and baseline comparison
- Additional scheduler tracepoints (wakeup latency, run-queue length)
