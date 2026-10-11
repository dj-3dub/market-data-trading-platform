#include <linux/sched.h>

BPF_HASH(start_times, u32, u64);
BPF_PERF_OUTPUT(latency_events);

struct event_t {
	u32 pid;
	u64 off_cpu_ns;
	char comm[TASK_COMM_LEN];
};

TRACEPOINT_PROBE(sched, sched_switch) {
	u32 prev_pid = args->prev_pid;
	u32 next_pid = args->next_pid;
	u64 ts = bpf_ktime_get_ns();

	if (prev_pid != 0) {
		start_times.update(&prev_pid, &ts);
	}

	u64 *tsp = start_times.lookup(&next_pid);
	if (tsp != 0) {
		u64 delta = ts - *tsp;

		if (delta > 50000) {
			struct event_t data = {};
			data.pid = next_pid;
			data.off_cpu_ns = delta;
			/* Use bpf_probe_read_str for broader kernel compatibility. */
			bpf_probe_read_str(&data.comm, sizeof(data.comm), args->next_comm);

			latency_events.perf_submit(args, &data, sizeof(data));
		}
		start_times.delete(&next_pid);
	}
	return 0;
}

