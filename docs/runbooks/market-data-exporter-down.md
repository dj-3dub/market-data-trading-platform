# Runbook: Market Data Exporter Down

**Severity:** Critical (loss of observability)

**Alert:** MarketDataExporterDown

**Owner:** Market-data / observability on-call

## Detection

Prometheus fires when:

    up{job="market-data-network"} == 0

remains true for 30 seconds.

The current lab uses a receiver metrics endpoint
on port 9108.

An exporter failure does not necessarily mean the
multicast feed itself has stopped.

## Investigation

Check Prometheus target status:

```bash
curl -fsS -G http://127.0.0.1:9090/api/v1/query \
  --data-urlencode 'query=up{job="market-data-network"}'
```

Check the receiver process:

```bash
pgrep -af 'feed_receiver\.py' || true
```

Check the metrics listener:

```bash
sudo ss -ltnp | grep ':9108' \
  || echo "Port 9108 is not listening"
```

Test the metrics endpoint:

```bash
curl --max-time 3 -fsS \
  http://127.0.0.1:9108/metrics
```

If the host endpoint works but Prometheus reports
up=0, inspect Docker networking, scrape errors,
target configuration, and scoped firewall rules.

```bash
curl -fsS http://127.0.0.1:9090/api/v1/targets \
  | python3 -m json.tool
```

The current lab target is 172.18.0.1:9108.
This Docker bridge gateway may change.

## Controlled failure injection

Stop feed_receiver.py with Ctrl+C.

Confirm port 9108 is no longer listening.

After the Prometheus scrape and alert evaluation
window, expect:

    up = 0
    MarketDataExporterDown = firing

## Recovery

Restart the receiver from the repository root:

```bash
python3 labs/market-data-network/feed_receiver.py
```

Investigate startup errors, port conflicts, or
network restrictions if the exporter stays down.

WARNING: Restarting the receiver discards its
in-memory sequence tracking state and counters.
This does not recover earlier missing packets.

## Verification

Check the metrics endpoint:

```bash
curl -fsS http://127.0.0.1:9108/metrics \
  | grep '^feed_packets_received_total'
```

Check the Prometheus target:

```bash
curl -fsS -G http://127.0.0.1:9090/api/v1/query \
  --data-urlencode 'query=up{job="market-data-network"}'
```

Expected: up=1

Check the alert:

```bash
curl -fsS http://127.0.0.1:9090/api/v1/rules \
  | python3 -c '
import json,sys
for group in json.load(sys.stdin)["data"]["groups"]:
    for rule in group["rules"]:
        if rule.get("name") == "MarketDataExporterDown":
            print(rule["name"], rule["state"], rule["health"])
'
```

Expected state: inactive
Expected health: ok

Independently verify actual feed integrity.

## Escalation

Escalate if telemetry cannot be restored, the
receiver repeatedly crashes, or observability loss
prevents safe operations.

## Evidence

Capture scrape errors, outage start and end times,
alert transitions, process logs, root cause,
recovery actions, and any lost integrity state.
