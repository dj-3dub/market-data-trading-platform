# Priority 2: data integrity and repeatable recovery

## Run on the P720

Leave the validated Priority 1 Debian deployment running. Download the new
`market-data-trading-platform-priority-2.zip` onto the workstation, then:

```bash
docker version
docker compose version
python3 --version
mkdir -p ~/projects/trading-priority-2
unzip ~/Downloads/market-data-trading-platform-priority-2.zip -d ~/projects/trading-priority-2
cd ~/projects/trading-priority-2/market-data-trading-platform
make priority2-acceptance
```

Docker must be running and accessible to your user. The workflow creates a fresh
`.env`, builds services, validates the pipeline and dashboards, checks persistence,
replays the fixture, and tests both Kafka consumer crash boundaries. Do not copy
credentials from the VM. If another local project uses the same ports, configure
port overrides before starting; see the Compose port variables. Access Grafana at
http://localhost:3000 with username admin and the password in `.env`.

Reports appear in `artifacts/`: pipeline, persistence, replay, and unique
correctness reports. Check `passed` and every `checks` entry. `make test-failures`
runs the broader fault suite separately. `make down` retains state; `make clean`
deletes volumes and is destructive. Native unit tests require Python test
requirements and .NET 10; Docker acceptance does not require a host .NET SDK.

## Contract and delivery

`contracts/tick-v1.schema.json` defines versioned ticks. Default symbols are FAKE,
FAKE2 and FAKE3. Each tick has a durable producer stream ID, per-symbol sequence,
matching event ID, timestamp, price, and symbol Kafka key. The new `ticks-v1`
topic and `strategy-engine-v1` group separate this contract from Priority 1.

The producer saves an event in a SQLite outbox before publishing. A retry after
failure or restart uses the same event identity and payload. Kafka acknowledgement
advances the producer sequence transactionally. This is at-least-once delivery.

The strategy saves analytical state, accepted identities, quarantine records,
and its next offset in one SQLite transaction before committing the Kafka offset.
On assignment it resumes from its local checkpoint, even if the broker commit
is ahead. Replayed events have no repeated trading effect. This provides durable
local effect deduplication with one active writer; it does not execute real orders
or provide distributed exactly-once processing. The SQLite writer lock prevents
two processes sharing this state from running concurrently.

Missing Kafka history fails closed. Never recreate a topic under the same name
while retaining its old checkpoint. Backup and restore Kafka history and local
state consistently. The local Compose volumes are `producer-state` and
`strategy-state`; stop their writers before copying SQLite files, including WAL
and shared-memory files. AWS Fargate deployment currently lacks these durable
application mounts, so these recovery guarantees are limited to local Compose.

## Invalid, duplicate, late and stale data

Malformed schema, wrong keys, conflicting event IDs, and sequence gaps enter a
durable quarantine with original key, payload, location and reason. A gap blocks
signals for that symbol. Supply the missing sequence and replay the rejected
later event in order to restore continuity; a later higher sequence alone does
not establish the missing history. Late identical events count as duplicates and
out-of-order input without changing accepted state. A source timestamp regression
is rejected. Stale valid ticks advance analytical history but cannot produce BUY.

```bash
curl -s http://localhost:8000/integrity
curl -s 'http://localhost:8000/quarantine?limit=20'
curl -s 'http://localhost:8000/strategy?symbol=FAKE2'
```

Readiness requires fresh data for every configured symbol. Blocked state prevents
successful strategy responses and exposes `strategy_symbol_sequence_blocked`; an alert
fires after five seconds. Grafana includes duplicate rate and blocked symbols.
The accepted-event ledger, receipts and quarantine grow without retention in this
lab; storage retention and multi-writer availability remain future work.

## Evidence scope

`make test-replay` executes the C# processor against committed fixtures, compares
expected results, repeats against the same database and an independent database,
and terminates real processes before and after checkpoints. Native alternative:

```bash
python3 scripts/replay-check.py --dotnet dotnet
```

`make test-correctness` uses separate Kafka topics, groups and state volumes. It
forces real consumer exits before checkpoint commit and after checkpoint commit
but before Kafka commit, then checks recovery. Test clocks and crash hooks require
explicit test mode; normal services use wall time. Isolated fixture checks prove
state correctness, while pipeline checks verify live freshness separately.
The experiment cleans up only its own objects. These Docker checks must be run
on the workstation; native validation results are documented in
[Priority 2 validation](../testing/priority-2-validation.md).
