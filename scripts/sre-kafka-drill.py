#!/usr/bin/env python3
"""Run a bounded SRE Kafka failure drill and persist consolidated evidence.

Run only against a disposable local Compose lab. Requires a healthy live stack.
The underlying failure-suite restores the broker in a finally block.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = [
    ("baseline", [sys.executable, "scripts/verify-pipeline.py"]),
    ("broker_outage", [sys.executable, "scripts/failure-suite.py", "broker"]),
    ("post_recovery_pipeline", [sys.executable, "scripts/verify-pipeline.py"]),
    ("post_recovery_persistence", [sys.executable, "scripts/verify-persistence.py"]),
]


def main():
    if os.environ.get("SRE_DRILL_ACK") != "local-lab":
        print("Refusing fault injection. Set SRE_DRILL_ACK=local-lab on a disposable local lab.", file=sys.stderr)
        return 2
    started = datetime.now(timezone.utc).isoformat()
    steps = []
    result = {"schema_version": 1, "scenario": "kafka-dependency-recovery",
              "started_at_utc": started, "passed": False, "steps": steps,
              "notes": "Single broker Compose lab; restoration, not automatic broker failover. "
                       "See fault-broker artifact for alert and recovery timings."}
    output = ROOT / "artifacts" / "sre-kafka-drill.json"
    output.parent.mkdir(exist_ok=True)
    try:
        for name, command in COMMANDS:
            print(f"\n=== {name}: {' '.join(command)} ===", flush=True)
            completed = subprocess.run(command, cwd=ROOT, check=False)
            steps.append({"name": name, "exit_code": completed.returncode,
                          "passed": completed.returncode == 0})
            if completed.returncode:
                break
        result["passed"] = len(steps) == len(COMMANDS) and all(s["passed"] for s in steps)
    except (OSError, KeyboardInterrupt) as error:
        result["error"] = str(error)
    finally:
        result["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"\nEvidence: {output}", flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
