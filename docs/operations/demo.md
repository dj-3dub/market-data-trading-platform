# Local demo guide

## Start and verify

Requires Docker Compose, Python 3, curl, and Make. From the repository root:

```bash
make setup
make up
python3 scripts/verify-pipeline.py
make doctor test
```

The acceptance check waits for fresh ticks and metrics (up to 90 seconds per
phase). On a slow first start, inspect `docker compose logs --tail=100` and retry.
`make doctor` and `make test` return nonzero if a required check fails.

Open:

- Frontend: <http://localhost:8082>
- Grafana: <http://localhost:3000> (username `admin`; password generated in `.env`)
- API schema: <http://localhost:8000/docs>
- Prometheus alerts: <http://localhost:9090/alerts>

Use the **Trading Platform** latency dashboard and **Trading Overview** dashboard.
The frontend continuously requests API data, keeping API latency panels active.
Without API traffic, rate-based API latency panels can show no data after their
five-minute window expires; the market-data and strategy stream still runs.

Port overrides work without rebuilding browser configuration:

```bash
WEB_PORT=8090 API_PORT=8091 make up
WEB_PORT=8090 API_PORT=8091 make doctor test
```

Pass the same overrides to subsequent commands. The frontend uses `/api/` through
Nginx, so it also works through SSH forwarding. Published ports are loopback-only.

## What the pipeline does

1. Market data publishes one tick per second across `FAKE`, `FAKE2`, and `FAKE3` in round-robin order and waits for Kafka
   acknowledgement. It retries connection and publication failures.
2. Strategy consumes `ticks-v1` as `strategy-engine-v1`, measures generation-
   to-processing latency, and emits a simulated BUY signal when the price rises
   more than 0.1% relative to the previous tick; otherwise it reports HOLD.
3. `/price` returns the latest acknowledged market tick. `/strategy` returns
   processed state, original timestamp, freshness, processed count, and signal.
4. `/health` is process liveness; `/ready` returns 503 when dependencies or data
   freshness are degraded. Strategy data becomes stale after 10 seconds.
5. Prometheus scrapes every five seconds. Grafana's provisioned panels use the
   actual exported metrics.

`strategy_tick_latency_seconds` ends at strategy processing, not at the browser.
API request latency is measured separately. All prices, signals, and trade
counters are simulated. Strategy state and simulated decisions use a local SQLite checkpoint and event
ledger. This lab has no real order execution.

## Reproducible incident: consumer outage

Keep the frontend, latency dashboard, and Prometheus alerts open, then run:

```bash
make incident
```

The script verifies a healthy baseline, pauses the strategy container while
market data continues publishing, waits up to 60 seconds for the selected
outage condition and firing alert, and checks:

- API readiness returns 503.
- `TradingServiceDown` fires for the strategy.
- Kafka consumer lag becomes positive.
- After unpausing, fresh strategy data resumes, lag falls to 10 or less (normal
  offset-commit delay), and the outage alert clears.

The fault runner attempts to unpause the container if the exercise fails or is
interrupted and writes traceable evidence in `artifacts/`.
For manual recovery after a killed terminal/process:

```bash
docker compose unpause strategy-engine
python3 scripts/verify-pipeline.py
```

The latency histogram will include delayed backlog ticks during recovery. Its
five-minute percentiles can stay elevated after freshness has recovered.

Rules in `monitoring/prometheus/alerts.yml` also detect stale strategy data and
consumer backlog. Alerts are visible in Prometheus; notification delivery is
not configured.

## Optional kernel signal

On a compatible native Linux host:

```bash
make agent-up
make agent-stress
```

Open the Wacker-Watch Off-CPU Duration dashboard alongside application latency. A down
optional agent target is skipped by the default health checks. Both host and
container scrape addresses are configured; when both reach the same agent,
aggregate event rates double-count it. Use one scrape address when measuring
absolute event rates. See the [agent guide](../../agents/wacker-watch/README.md).

## Acceptance evidence and shutdown

`make test` verifies Kafka connectivity, frontend proxying, application metrics,
Grafana datasource queries, live strategy progress, and all application
dashboard queries. CI runs this workflow and the consumer incident on a fresh
Compose stack. Kernel loading is host-dependent and is outside portable CI.

```bash
make validate
docker compose exec -T prometheus promtool check config /etc/prometheus/prometheus.yml
make down
```

`make down` stops the default stack. Stop the optional agent with `make agent-down`.
Named volumes retain Kafka records/committed offsets, ZooKeeper state, Grafana
state and Prometheus history across container recreation. Producer and strategy state use dedicated SQLite volumes. Run `make test-persistence` to verify storage behavior on your host.
`make down` preserves volumes; `docker compose down -v` and `make clean` delete
them. See [Priority 1 operations](priority-1.md) for upgrade instructions.


## Open the VM demo from your P720

On the P720, replace the address below if your Debian VM has moved:

```bash
ssh -N -L 8082:127.0.0.1:8082 -L 3000:127.0.0.1:3000 \
  -L 8000:127.0.0.1:8000 -L 9090:127.0.0.1:9090 \
  -L 8081:127.0.0.1:8081 tim@192.168.122.240
```

Keep that terminal open and use the localhost URLs above on your P720.
Choose different local ports if the P720 already uses them. Run validation and
fault commands on the VM, where Docker and all published endpoints are local.
