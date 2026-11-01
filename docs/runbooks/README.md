# Market Data Reliability Runbooks

Operational procedures for the UDP multicast reliability lab.

Run commands from the repository root on the Debian VM.

| Incident | Alert | Threshold |
|---|---|---|
| Stale feed | MarketDataFeedStale | feed_stale == 1 for 5s |
| Sequence gap | MarketDataUnresolvedGap | feed_unresolved_gaps > 0 for 10s |
| Exporter failure | MarketDataExporterDown | up == 0 for 30s |

## Runbooks

- [Stale feed](market-data-feed-stale.md)
- [Sequence gap](market-data-sequence-gap.md)
- [Exporter down](market-data-exporter-down.md)

## Verified lab results

- Missing sequence detected and critical alert fired.
- Session-aware replay recovered the missing sequence.
- Unresolved gaps decreased from 1 to 0.
- MarketDataUnresolvedGap resolved automatically.
- Exporter shutdown produced up=0 and a firing alert.
- Receiver restart restored up=1 and resolved the alert.
- Stale-feed detection and recovery were previously tested.

## Limitations

- This is a synthetic multicast feed.
- Replay requires a known original session ID.
- Recovery is manual, not an automatic retransmission protocol.
- Receiver state is stored in memory and lost on restart.
- Restoring telemetry does not prove downstream trading correctness.

## Next improvements

Automated incident validation, timestamped evidence,
persistent sequence tracking, and downstream reconciliation.
