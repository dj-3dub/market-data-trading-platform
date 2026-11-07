# Automated Market-Data Incident Validation

This lab validates market-data reliability through controlled
failure injection, Prometheus alerting, and recovery verification.

## Validated scenarios

| Scenario | Checks | Result |
|---|---|---|
| Sequence-gap detection and replay | 11/11 | PASS |
| Stale-feed detection and recovery | 10/10 | PASS |

These results were obtained during local testing on November 1, 2026.
They are not continuous availability guarantees.

## Prerequisites

- The market-data receiver is running.
- Prometheus is available at http://127.0.0.1:9090.
- The market-data-network scrape target is healthy.
- The market-data alert rules are loaded.

Start the receiver if it is not already running:

    python3 -u labs/market-data-network/feed_receiver.py

Run the following validation commands from another terminal.

## Scenario 1: Sequence-gap recovery

    python3 scripts/incident-validation.py \
      --mode gap-replay \
      --prometheus http://127.0.0.1:9090 \
      --timeout 90

The test verifies that a missing sequence number triggers
an alert and that replay resolves the gap.

## Scenario 2: Stale-feed recovery

    python3 scripts/incident-validation.py \
      --mode stale-recovery \
      --prometheus http://127.0.0.1:9090 \
      --pause-seconds 20 \
      --rate 10 \
      --timeout 90

The test pauses market-data transmission, verifies that the
stale-feed alert fires, resumes transmission, and verifies recovery.

## Evidence

The validator writes JSON reports to:

    artifacts/incidents/

Evidence includes validation checkpoints and the final result.
Stale-recovery reports additionally include injected sender events,
session correlation, and observed detection and recovery timing.

Observed timing includes monitoring and validation polling delays.

## Known limitation: Test isolation

Gap-replay requires a clean baseline with no unresolved sequence gaps.

Previous experiments can leave unresolved gaps in the receiver's
in-memory state. This can cause a precondition failure even when
the validator itself is working correctly.

Automated test isolation is planned.

## Operational runbooks

See the runbooks in ../runbooks/ for investigation and recovery
procedures.
