# Operational Scripts

Lightweight Python and Bash tooling for operating and validating the platform.

## Service monitoring (Python)

| Script | Purpose |
|--------|---------|
| `check_service_health.py` | Poll the API health endpoint and alert on failure |
| `check_api_latency.py` | Measure API response latency in a loop |
| `check_kafka_lag.py` | Detect consumer lag against a threshold |

## Validation (Bash)

| Script | Purpose |
|--------|---------|
| `health-check.sh` | Validate container status, health endpoints, API responsiveness, metrics availability |
| `smoke-test.sh` | Basic endpoint, dependency, and service reachability checks |
| `wacker-watch-smoke-test.sh` | Verify the eBPF agent's files, Python deps, BPF source, and metrics port |
| `collect-debug-data.sh` | Collect a debug bundle during an incident |

Run them via the Makefile from the repository root:

```bash
make doctor      # health-check.sh + VM diagnostics
make test        # smoke-test.sh + wacker-watch-smoke-test.sh
make agent-smoke # wacker-watch smoke test only
```

These scripts model the type of automation commonly used in production support
environments.


## Priority 1 local operations

- `setup-local.py`: creates private initial Grafana credentials; `make up` runs it.
- `local_config.py`: reads those credentials for host-side checks without shell evaluation.
- `evidence.py`: common provenance and unique/latest JSON report storage.
- `verify-persistence.py`: controlled stateful-container recreation and workload restoration.

Run `make acceptance` on the Docker host for the sequential local acceptance
workflow. See [Priority 1 operations](../docs/operations/priority-1.md) for the
state migration, credential, storage, access and evidence contracts.

## Priority 2 correctness

- `replay-check.py`: real C# fixture replay, repeat/independent state comparison
  and abrupt exits before/after local checkpoints; Docker by default or `--dotnet`.
- `correctness-suite.py`: separate Kafka topic/group/volume and strategy process
  for both crash boundaries, with a fixed test clock. The main pipeline is untouched.

Run `make priority2-acceptance`; see [Priority 2 operations](../docs/operations/priority-2.md).
