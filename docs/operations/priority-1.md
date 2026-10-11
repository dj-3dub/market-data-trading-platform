# Priority 1: trustworthy local deployment

> Historical Priority 1 baseline. For the current tick contract and application
> state recovery, see [Priority 2](priority-2.md).

## Implemented

- Corrected Wacker-Watch to `wacker_watch_off_cpu_duration_ns` and an Off-CPU
  Duration dashboard, retaining UID `wacker-watch`. Intervals at or below 50 µs
  are excluded. Sleep, I/O blocking and runnable wait are not distinguished.
- Moved the old Fargate scaffold to `infra/terraform/archive/aws-fargate`.
  Make and CI validate only the active managed AWS environment.
- Added named volumes for Kafka records/committed offsets, ZooKeeper snapshots
  and transaction logs, and Grafana state. Prometheus retains its named volume.
- Set `unless-stopped` on all long-running services. This handles process exit
  and daemon restart, not unhealthy-but-running processes or deliberate stops.
- Bound every Compose-published port to IPv4 loopback. Kafka keeps an internal
  listener at `kafka:9092` and advertises a separate localhost host listener.
- Added `make setup` to generate an ignored `.env` with a unique initial Grafana
  password and mode 0600. Existing settings/passwords are preserved. `make up`
  runs setup automatically. Health and smoke checks read the same password.
- Added unique fault reports with UTC times, commit/dirty status when available,
  source SHA256, host resources, runtime versions and scenario/workload settings.
- Added a volume persistence experiment and a sequential acceptance target.

## Apply on an existing VM

The source archive is not a Git checkout. Apply the supplied changes to your
existing checkout so future reports can record its commit and dirty status.
Do not replace your `.git`, `.env`, personal Terraform inputs, or running data.

**Before recreating the old containers:** decide whether their existing lab data
needs to be retained. New named volumes do not automatically import data from
the old container filesystems or anonymous volumes.

To preserve the old data, stop the old stack and copy the stopped state before
applying this update. Run these from the old checkout:

```bash
docker compose stop
mkdir -p state-backup/kafka state-backup/zookeeper-data state-backup/zookeeper-log state-backup/grafana
docker cp mdp-kafka:/var/lib/kafka/data/. state-backup/kafka/
docker cp mdp-zookeeper:/var/lib/zookeeper/data/. state-backup/zookeeper-data/
docker cp mdp-zookeeper:/var/lib/zookeeper/log/. state-backup/zookeeper-log/
docker cp mdp-grafana:/var/lib/grafana/. state-backup/grafana/
```

Keep the Kafka and ZooKeeper backups together. Retain the existing
`prometheus-data` volume and the same Compose project name. Backups may contain
Grafana credentials; keep them private and outside the source archive. Restore
the stopped Kafka/ZooKeeper directories into their corresponding new named
volumes **before** starting the updated containers, preserving ownership:

```bash
# Read the existing project label while the old stopped containers still exist.
lab_project=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' mdp-kafka)
test -n "$lab_project"
restore_volume() {
  docker run --rm \
    --mount "type=bind,src=$PWD/state-backup/$1,dst=/backup,readonly" \
    --mount "type=volume,src=${lab_project}_$2,dst=/restore" \
    python:3.12-slim sh -ec \
    'test -z "$(ls -A /restore)" || { echo "Destination is not empty; refusing to overwrite"; exit 1; }; cp -a /backup/. /restore/'
}
restore_volume kafka kafka-data
restore_volume zookeeper-data zookeeper-data
restore_volume zookeeper-log zookeeper-log
restore_volume grafana grafana-data
```

Stop if a restore command fails. This is a manual migration; the persistence
test validates the new volume layout, not an old-to-new migration. For a
disposable lab, start with empty new volumes and retain the backup until the
updated demo is accepted.

The new Grafana volume initially uses the password from `.env`. If importing an
old Grafana database, its existing login password survives: the initialization
environment variable does not reset an existing account. Update the `.env`
password to match or use Grafana's password reset procedure before running the
authenticated checks. Likewise, later changing `.env` does not rotate an
existing Grafana account. `make setup` never silently rotates a password.

## New checkout or disposable local lab

```bash
make setup
make acceptance
```

Setup requires Python 3; acceptance also requires Docker Compose, Make and curl.
Open `.env` privately to retrieve the generated Grafana password; username is
`admin`. Do not paste that file or resolved `docker compose config` output into
reports. `docker compose config --quiet` validates without printing credentials.
The password is passed through the container environment, so users with Docker
administrative access can inspect it; this is local lab credential handling.

The local `.env` password contract supports a plain URL-safe value (generated
by setup) or a simply quoted literal. Do not use Compose interpolation in that
password. Environment variable `GRAFANA_ADMIN_PASSWORD` overrides the file for
CI or an external secret manager. Pass port overrides consistently to host-side
commands, for example `API_PORT=8091 WEB_PORT=8090 make acceptance`.

From your P720, use the [SSH forwarding instructions](demo.md#open-the-vm-demo-from-your-p720).

## Storage contract

| State | Container restart/recreation with volumes | `down -v` / `make clean` |
|---|---|---|
| Kafka records and committed consumer offsets | Retained in `kafka-data` | Deleted |
| ZooKeeper snapshots and transaction logs | Retained in `zookeeper-data` / `zookeeper-log` | Deleted |
| Grafana users and saved dashboards | Retained in `grafana-data` | Deleted |
| Prometheus samples | Retained in `prometheus-data`, subject to 35-day retention | Deleted |
| Strategy prices, counters and signals | Reset on strategy restart | Reset |
| Producer's latest tick and price walk | Reset on producer restart | Reset |

Keep the same Compose project name so Compose reuses the same named volumes.
This single-broker lab provides persistence, not broker high availability,
host-loss recovery, exactly-once processing, or durable strategy state.

## Acceptance checklist

- [ ] On the VM, run `make acceptance` and keep its successful output.
- [ ] Run `make test-failures` to repeat all six faults with traceable reports.
- [ ] Verify Grafana login with the generated password and all four dashboards.
- [ ] Confirm loopback bindings with `docker compose ps` and `ss -ltn`.
- [ ] On a compatible host, rebuild/run `make agent-up` and verify the renamed
  metric and dashboard. Kernel loading remains outside portable CI.

`make acceptance` starts/builds the stack, checks advancing data and dashboards,
runs health/smoke checks, exercises the consumer fault, recreates the stateful
containers, and checks the recovered pipeline again. It leaves the lab running.
`make test-persistence` briefly stops producer/strategy, writes a private test
topic and temporary dashboard, recreates Kafka/ZooKeeper/Grafana/Prometheus,
verifies records, committed offsets, the dashboard and a historical sample,
then restores the application and removes its test objects. Interruption attempts
restoration; after a hard kill, run `docker compose start market-data strategy-engine`.
No volume deletion is used by either check.

## Evidence contract

Each fault, AWS restart, and persistence run writes `schema_version: 2`, a unique
run ID, UTC start/finish times and source/host/runtime metadata. Unique report
files are retained, with a familiar latest filename for tooling compatibility.
When `.git` is absent, `git_commit` and `git_dirty` are null; the tree SHA256
identifies the uploaded source snapshot. Local secrets, build caches, runtime
reports, private Terraform inputs and state files are excluded from that digest.
Workload metadata includes the resolved tick interval, topic and service image/
resource configuration, not arbitrary environment values or Grafana passwords.

Detection timings include the selected firing alert and HTTP condition. Recovery
timings include alert clearance, backlog checks where applicable and sustained
fresh progress. They are not pure process startup or message latency timings.
Existing schema-less reports in the archive are historical evidence from the
prior project; they do not validate this revision. AWS deployment and native
eBPF loading remain host/account-specific checks.
