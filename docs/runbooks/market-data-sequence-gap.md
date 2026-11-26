# Runbook: Market Data Sequence Gap

**Severity:** Critical

**Alert:** MarketDataUnresolvedGap

**Owner:** Market-data / trading-systems on-call

## Detection

Prometheus fires when:

    feed_unresolved_gaps{job="market-data-network"} > 0

remains true for 10 seconds.

Inspect receiver metrics:

```bash
curl -fsS http://127.0.0.1:9108/metrics \
  | grep -E '^feed_(sequence_gaps_total|gap_recoveries_total|unresolved_gaps) '
```

## Investigation

1. Identify the original full session ID.
2. Identify the symbol and missing sequence number.
3. Check receiver logs for GAP and OUT_OF_ORDER.
4. Check duplicate and invalid-packet counters.
5. Determine whether the receiver has restarted.
6. Assess downstream strategy consistency.

The receiver may log only the first eight characters
of a session ID. Obtain the full ID from the sender
or another trusted source.

## Reproduce in the lab

```bash
python3 labs/market-data-network/feed_sender.py \
  --continuous --rate 10 --duration 30 \
  --drop-sequence 5
```

Capture the printed SESSION_ID.

Expected metrics for a fresh receiver:

    feed_sequence_gaps_total 1
    feed_gap_recoveries_total 0
    feed_unresolved_gaps 1

Wait for the alert to enter firing state.

## Recovery

Replay the missing sequence using the SAME original
session ID and symbol:

```bash
python3 labs/market-data-network/feed_sender.py \
  --replay \
  --session-id REPLACE_WITH_ORIGINAL_FULL_SESSION_ID \
  --symbol FAKE \
  --sequence 5
```

Expected receiver status:

    GAP_RECOVERED

This is controlled synthetic replay, not an
exchange-certified retransmission mechanism.

## Verification

```bash
curl -fsS http://127.0.0.1:9108/metrics \
  | grep -E '^feed_(sequence_gaps_total|gap_recoveries_total|unresolved_gaps) '
```

Expected after recovery of the only missing sequence:

    feed_sequence_gaps_total 1
    feed_gap_recoveries_total 1
    feed_unresolved_gaps 0

Check the Prometheus alert:

```bash
curl -fsS http://127.0.0.1:9090/api/v1/rules \
  | python3 -c '
import json,sys
for group in json.load(sys.stdin)["data"]["groups"]:
    for rule in group["rules"]:
        if rule.get("name") == "MarketDataUnresolvedGap":
            print(rule["name"], rule["state"], rule["health"])
'
```

Expected state: inactive
Expected health: ok

Verify downstream state separately.

## Escalation

Escalate if the original session ID is unavailable,
the missing packet cannot be recovered, the session
has changed, or downstream strategy state is uncertain.

Never fabricate live market data to resolve a
production feed integrity incident.

## Evidence

Record session ID, symbol, missing sequence range,
detection time, replay time, recovery time,
counter changes, alert state, and downstream impact.
