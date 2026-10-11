# Priority 2 implementation validation

Validated in the development environment on 2026-10-09:

- Python unit suite: 30 tests passed.
- C# unit suite: 18 tests passed with .NET SDK 10.0.401.
- Native deterministic replay matched the fixture: 7 accepted, 3 simulated
  trades, 2 duplicates, 2 out-of-order observations, 1 gap, 4 quarantined,
  and 1 stale tick.
- Replaying the same state did not change outcomes; independent replay matched.
- Actual abrupt process exits before and after checkpoint commit recovered to
  the identical final snapshot.
- Microsoft.Data.Sqlite 10.0.12 dependency scan reported no known vulnerable
  packages, including transitive dependencies, at validation time.

## Workstation acceptance: passed 2026-10-08 (America/Chicago)

The P720 run used a Xeon Gold 6148, 40 logical CPUs, approximately 64 GB RAM,
Docker 29.8.2 and Compose 5.6.0. Prometheus was mapped to port 9091 because
Cockpit uses host port 9090. Results below were supplied from the workstation;
the raw JSON reports remain in its `artifacts/` directory.

- Live Kafka-to-strategy-to-API pipeline passed; all 19 application dashboard
  queries returned finite data. Health checks: 28 passed, 0 failed; 4 optional
  eBPF checks skipped.
- Consumer outage detection and recovery passed.
- Kafka records, consumer offsets, a saved Grafana dashboard and Prometheus
  history survived stateful container recreation.
- Deterministic replay and both abrupt checkpoint crash checks passed.
- Live Kafka crash before checkpoint: passed, run `8e63a88546bc4de79f28d44f025c9d68`.
- Live Kafka crash after checkpoint, before offset commit: passed, run
  `4ce2c265c3154ed69d374431eec099b5`.
- Each isolated Kafka experiment restarted once, matched all fixture totals,
  and confirmed no duplicate simulated BUY. Final live pipeline check passed.

The initial Kafka checker timed out because ASP.NET HTTP JSON uses camelCase
while replay output preserves C# property names. The checker normalizes HTTP
keys, and its orchestration regression tests exercise camelCase responses.
The two successful reruns above followed that correction.

The broader six-scenario failure suite, native eBPF loading, and live AWS
application persistence are not included in this Priority 2 workstation result.

These tests demonstrate synthetic analytical effects and local recovery; they do
not certify financial trading, high throughput, distributed availability, or AWS
persistent application state.
