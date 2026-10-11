# Reliability foundation

## Objectives and accounting

Provisional objectives use a rolling **30-day** window. Validate latency against
an AWS baseline before using it as a release gate.

| SLO | Good / eligible | Target |
|---|---|---|
| API availability | 2xx / (2xx + 5xx), per `/price` and `/strategy` | 99.9% |
| API latency | Successful requests taking <=500 ms / successful requests | 99% |
| Strategy freshness | Good synthetic health samples / observed samples | 99.9% |

The probe calls `/strategy` every five seconds with a four-second timeout,
validates symbol, processed count and source timestamp, and exports its latest
outcome. SLO rules sample that outcome every 30 seconds. Fresh means source age
below ten seconds, allowing at most two seconds of future clock skew. This is a
**time-sampled health SLI**, not a count of every probe attempt. Its nominal
30-day allowance is 43.2 minutes. Brief faults between samples may be missed.

API metrics cover application-handled requests, excluding 4xx client errors,
health checks and metrics. They do not include requests lost before reaching
the gateway. In AWS the synthetic freshness probe traverses public DNS, TLS and
the ALB, providing a separate user-path signal. Request-based ingress accounting
from ALB logs is a follow-up before claiming complete user-request availability.

No traffic produces an undefined request ratio, not 100% availability. Missing
telemetry triggers coverage alerts. The freshness dashboard shows observed
30-second samples divided by the full 30-day expectation (86,400). Startup,
collector downtime and missing history lower coverage. A partial-history budget
must not be reported as a fully measured 30-day result. Prometheus evaluation
continues using recently scraped samples for its normal lookback period; consult
missing/stalled-probe alerts alongside the budget.

Budget remaining = `1 - bad_fraction / (1 - target)`; negative means exhausted.
API budgets are request counts, not downtime allowances. Local history persists
in the `prometheus-data` volume for 35 days; `docker compose down -v` deletes it.
AWS samples are remote-written to Amazon Managed Service for Prometheus (AMP).

## Error budget policy and runbook

- **Fast burn:** 14.4x sustainable consumption in both 1h and 5m windows,
  sustained for two minutes. Investigate the affected endpoint/SLO immediately.
- **Slow burn:** 6x in both 6h and 30m windows, sustained for 15 minutes.
  Prioritize a reliability issue with an owner and corrective action.
- **Exhausted budget:** pause feature promotion in that environment; prioritize
  restoration and reliability fixes. This is an operational policy, not an
  automated deployment lock.
- **Unknown coverage:** investigate collection before interpreting the budget.
- Failure experiments run in the local lab or a dedicated AWS test environment;
  their failures count against that environment's budget.

Triage: inspect the Reliability dashboard, then readiness, source freshness,
Kafka connectivity/backlog, ECS task events and logs. Roll back recent changes
if correlated. Verify advancing source timestamps and sustained fresh responses
after recovery. Record incident duration, budget impact, root cause and a
regression test. Alerts are dashboard-visible; external routing is not configured.

## Local verification

```sh
python3 -m venv .venv
.venv/bin/pip install -r tests/requirements.txt \
  -r services/api-gateway-python/requirements.txt \
  -r services/market-data-python/requirements.txt
.venv/bin/python -m pytest tests
dotnet test services/strategy-csharp/tests
make test-rules
docker compose up -d --build
python3 scripts/verify-pipeline.py
make doctor test
make test-failures
```

`test-failures` pauses the consumer, producer and broker in turn, restarts the
strategy process, injects malformed/null Kafka payloads and interrupts probe
scraping. The consumer fault also checks that a stalled upstream returns 503
within five seconds. Every outage scenario
checks baseline, expected degradation and a firing alert, restores the process,
and verifies fresh advancing data. Detection polling targets 60 seconds and
recovery 120 seconds (missing-scrape detection allows 180 seconds), with bounded individual HTTP/Compose operations. These are
lab exercise limits, not AWS recovery guarantees. Reports live in `artifacts/`.
Signals trigger best-effort restoration; after forced termination use
`docker compose unpause strategy-engine market-data kafka reliability-probe`
and `docker compose start strategy-engine` if interrupted during its restart.

CI runs unit tests and rule tests before live acceptance, exercises consumer
failure on PRs, and adds producer/broker outages, strategy restart, malformed
messages and scrape loss weekly and on manual dispatch.
Diagnostics and test reports are uploaded before teardown.

## Scope and next validation

Compose faults have local verification; an AWS task-restart adapter is also
provided. AWS FIS and fault-proxy experiments still need environment-specific
integration and measured recovery limits. Strategy tests cover durable local checkpoints, duplicate handling, sequencing
and crash/replay behavior. AWS state persistence still requires a separate
storage design and integration exercise. The SQLite processor is single-active
and local; this is not a highly available trading ledger. See [AWS deployment](../../infra/terraform/envs/aws-managed/README.md).
