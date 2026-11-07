# Runbook: Market Data Feed Stale

**Severity:** Warning; escalate if trading decisions are affected.

**Alert:** MarketDataFeedStale

**Owner:** Market-data / trading-systems on-call

## Detection

The receiver marks the feed stale after approximately
2 seconds without a valid packet, after initial traffic.

Prometheus fires the alert when:

    feed_stale{job="market-data-network"} == 1

remains true for 5 seconds.

## Investigation

Check feed freshness:

```bash
curl -fsS http://127.0.0.1:9108/metrics \
  | grep -E '^feed_(stale|packets_received_total) '
```

Check Prometheus target health:

```bash
curl -fsS -G http://127.0.0.1:9090/api/v1/query \
  --data-urlencode 'query=up{job="market-data-network"}'
```

Check sender and receiver processes:

```bash
pgrep -af 'feed_(sender|receiver)\.py' || true
```

Check multicast socket:

```bash
sudo ss -lunp | grep ':50010' || true
```

If available, inspect loopback multicast traffic:

```bash
sudo tcpdump -ni lo \
  'udp and dst host 239.192.0.10 and dst port 50010'
```

Determine whether the sender stopped, traffic was
interrupted, or packets were invalid.

## Recovery

Restore the original feed source whenever possible.

For a controlled lab recovery:

```bash
python3 labs/market-data-network/feed_sender.py \
  --continuous --rate 10 --duration 60
```

Do not restart the receiver merely to clear the stale
condition; doing so loses its in-memory integrity state.

## Verification

```bash
curl -fsS http://127.0.0.1:9108/metrics \
  | grep '^feed_stale '
```

Expected:

    feed_stale 0

Check the alert:

```bash
curl -fsS http://127.0.0.1:9090/api/v1/rules \
  | python3 -c '
import json,sys
for group in json.load(sys.stdin)["data"]["groups"]:
    for rule in group["rules"]:
        if rule.get("name") == "MarketDataFeedStale":
            print(rule["name"], rule["state"], rule["health"])
'
```

Expected state: inactive
Expected health: ok

Also check for unresolved sequence gaps.

## Escalation

Escalate when:
- Trading strategies may consume stale prices.
- Feed recovery fails.
- Multiple symbols or sessions are affected.
- Integrity alerts remain active after traffic resumes.

Production systems should follow approved trading-risk
and strategy-isolation procedures.

## Evidence

Record incident timestamps, affected sessions,
receiver logs, metrics, alert transitions, cause,
mitigation, and recovery duration.
