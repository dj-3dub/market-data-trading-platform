#!/usr/bin/env python3
import ctypes
import os
from pathlib import Path
from bcc import BPF
from prometheus_client import start_http_server, Histogram

# Port 8001 is reserved for this agent so it never collides with the trading
# platform's api-gateway, which is published on host port 8000.
METRICS_PORT = int(os.environ.get('WACKER_METRICS_PORT', '8001'))

# Kernel's TASK_COMM_LEN. Kept in sync with <linux/sched.h>.
TASK_COMM_LEN = 16

# 1. Initialize Prometheus Metrics
# We use custom exponential buckets tailored for microsecond/nanosecond tracking
LATENCY_BUCKETS = (
    50000, 75000, 100000, 250000, 500000, 750000,
    1000000, 2500000, 5000000, 10000000, 50000000,
    float("inf")
)

WACKER_OFF_CPU_HIST = Histogram(
    'wacker_watch_off_cpu_duration_ns',
    'Off-CPU intervals greater than 50000 ns, including sleep, I/O wait and runnable wait',
    ['process_name'],
    buckets=LATENCY_BUCKETS
)

# 2. The Kernel-Space eBPF C Code
# Load the eBPF program from the bpf source file so it can be maintained separately.
BPF_PATH = Path(__file__).resolve().parent.parent / 'bpf' / 'wacker_watch.bpf.c'
try:
    ebpf_program = BPF_PATH.read_text()
except Exception as e:
    print(f"Failed to read BPF program from {BPF_PATH}: {e}")
    raise


class EventT(ctypes.Structure):
    """Python mirror of `struct event_t` in bpf/wacker_watch.bpf.c.

    BCC only auto-generates the `event_t` ctype on some releases; on BCC 0.29+
    (including the 0.31 in Ubuntu 24.04) `BPF` exposes no such attribute, so the
    struct is mirrored here. ctypes uses the platform's natural alignment, which
    matches the C layout on x86-64: pid at 0, off_cpu_ns at 8, comm at 16, total 32.
    """
    _fields_ = [
        ('pid', ctypes.c_uint32),
        ('off_cpu_ns', ctypes.c_uint64),
        ('comm', ctypes.c_char * TASK_COMM_LEN),
    ]


def resolve_event_type(bpf):
    """Prefer the BCC-generated struct, fall back to the local mirror."""
    generated = getattr(bpf, 'event_t', None)
    if generated is not None:
        return generated
    return EventT


def make_event_decoder(table, event_type):
    """Build the perf-buffer callback, tolerating both BCC callback APIs.

    BCC 0.29 (Ubuntu 24.04) hands the callback a `bytes` object. BCC 0.31 hands
    it a raw pointer as an `int`, and expects the struct to be recovered via
    `Table.event(data)`, which derives the field layout from the compiled BPF
    module. Prefer the table API when present, and fall back to the mirrored
    ctypes struct otherwise.
    """
    table_event = getattr(table, 'event', None)

    def process_kernel_event(cpu, data, size):
        if table_event is not None and isinstance(data, int):
            event = table_event(data)
        else:
            try:
                event = event_type.from_buffer_copy(data)
            except (AttributeError, TypeError):
                event = event_type(data)

        proc_name = (event.comm or b'').decode('utf-8', errors='ignore').rstrip('\x00')

        # Observe the event duration inside our Prometheus Histogram
        WACKER_OFF_CPU_HIST.labels(process_name=proc_name).observe(event.off_cpu_ns)

    return process_kernel_event


def main():
    print("🚀 Wacker-Watch: Loading eBPF program into kernel...")
    b = BPF(text=ebpf_program)

    event_type = resolve_event_type(b)
    table = b["latency_events"]
    table.open_perf_buffer(make_event_decoder(table, event_type))

    # Start Prometheus HTTP metrics server
    start_http_server(METRICS_PORT)
    print(f"📊 Prometheus Metrics Server active at http://localhost:{METRICS_PORT}/metrics")
    print(f"   event struct: {event_type.__name__} "
          f"({ctypes.sizeof(event_type)} bytes)")
    print("Monitoring filtered off-CPU duration. Press Ctrl+C to terminate.")

    # Main engine execution loop
    try:
        while True:
            b.perf_buffer_poll()
    except KeyboardInterrupt:
        print("\nStopping Wacker-Watch.")


if __name__ == '__main__':
    main()
