"""Isolated Kafka lab: duplicate/gap handling and crash after checkpoint before commit.

Uses a unique topic, consumer group, state volume and one-off strategy container.
Does not inject into the normal ticks-v1 pipeline or remove its volumes.
"""
import json
import argparse
from pathlib import Path
import signal
import subprocess
import time
from evidence import compose_workload, new_report, save_report

ROOT = Path(__file__).resolve().parents[1]


def command(args, input=None):
    return subprocess.run(args, cwd=ROOT, input=input, capture_output=True, text=True,
                          check=True, timeout=90).stdout.strip()


def eventually(check, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            pass
        time.sleep(2)
    raise TimeoutError("Correctness experiment did not reach the expected state")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boundary", choices=["before", "after"], default="after")
    args = parser.parse_args()
    report = new_report(ROOT, "kafka-correctness", {"crash_boundary": args.boundary, "fixed_test_clock": 1000})
    report["workload"] = compose_workload(ROOT)
    token = report["run_id"][:12]
    topic, container, volume = "correctness-" + token, "correctness-" + token, "correctness-" + token
    created_topic = created_container = created_volume = False
    expected = json.loads((ROOT / "fixtures/replay-v1.expected.json").read_text())
    stream = "00000000000000000000000000000001"
    # Fixture seq2 causes a BUY then an abrupt process exit before Kafka commit.
    crash_id = f"{stream}:FAKE:2"
    kafka = ["docker", "compose", "exec", "-T", "kafka"]
    try:
        created_topic = True
        command(kafka + ["kafka-topics", "--bootstrap-server", "kafka:9092", "--create", "--topic", topic,
                         "--partitions", "1", "--replication-factor", "1"])
        created_volume = True
        command(["docker", "volume", "create", volume])
        created_container = True
        command(["docker", "compose", "run", "-d", "--no-deps", "--name", container,
                 "-e", f"KAFKA_TICKS_TOPIC={topic}", "-e", f"KAFKA_CONSUMER_GROUP={topic}",
                 "-e", "STRATEGY_STATE_DIR=/experiment", "-e", f"STRATEGY_CRASH_EVENT_ID={crash_id}",
                 "-e", "STRATEGY_TEST_MODE=1", "-e", "STRATEGY_TEST_CLOCK_SECONDS=1000",
                 "-e", f"STRATEGY_CRASH_BOUNDARY={args.boundary}",
                 "-v", f"{volume}:/experiment", "strategy-engine"])
        command(["docker", "update", "--restart=unless-stopped", container])

        def state():
            raw = json.loads(command(["docker", "exec", container, "curl", "-fsS", "--max-time", "5",
                                       "http://localhost:7002/integrity"]))
            # ASP.NET HTTP JSON uses camelCase; native replay preserves C# names.
            return {key[:1].upper() + key[1:]: value for key, value in raw.items()}
        eventually(state)
        # Fixed clock makes business outcomes independent of restart duration.
        # The normal application pipeline continues using real wall time.
        lines = []
        for line in (ROOT / "fixtures/replay-v1.jsonl").read_text().splitlines():
            row = json.loads(line)
            lines.append(row["key"] + "|" + row["payload"])
        command(kafka + ["kafka-console-producer", "--bootstrap-server", "kafka:9092", "--topic", topic,
                         "--property", "parse.key=true", "--property", "key.separator=|"], input="\n".join(lines) + "\n")
        def complete():
            current = state()
            return current if current["Offsets"].get(topic + ":0") == len(lines) - 1 else None
        final = eventually(complete)
        for key, value in expected.items():
            if final[key] != value:
                raise AssertionError(f"{key}: expected {value}, received {final[key]}")
        restarts = int(command(["docker", "inspect", "-f", "{{.RestartCount}}", container]))
        if restarts < 1:
            raise AssertionError("Checkpoint crash hook did not cause a process restart")
        report.update(passed=True, totals={key: final[key] for key in expected}, restart_count=restarts,
                      checks={"fixture_outcomes": True, "checkpoint_crash_recovery": True, "no_duplicate_buy": True})
    except BaseException as error:
        report["error"] = str(error)
        raise
    finally:
        cleanup_errors = []
        for needed, cleanup_args in (
            (created_container, ["docker", "rm", "-f", container]),
            (created_volume, ["docker", "volume", "rm", volume]),
            (created_topic, kafka + ["kafka-topics", "--bootstrap-server", "kafka:9092", "--delete", "--topic", topic]),
        ):
            if needed:
                try:
                    command(cleanup_args)
                except Exception as error:
                    cleanup_errors.append(str(error))
        if cleanup_errors:
            report.update(passed=False, cleanup_errors=cleanup_errors)
        save_report(ROOT, report, f"correctness-{args.boundary}")
        print(json.dumps(report))
        if cleanup_errors:
            raise RuntimeError("Experiment cleanup needs attention; see correctness report")


if __name__ == "__main__":
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    main()
