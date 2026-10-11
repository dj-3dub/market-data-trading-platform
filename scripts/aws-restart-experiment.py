#!/usr/bin/env python3
"""Restart one ECS service task and verify replacement and public-path recovery."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.request

from evidence import new_report, save_report


def aws(*args):
    result = subprocess.run(["aws", "ecs", *args, "--output", "json"],
                            capture_output=True, text=True, check=True, timeout=30)
    return json.loads(result.stdout)


def fresh(url):
    with urllib.request.urlopen(url.rstrip("/") + "/strategy", timeout=5) as response:
        state = json.load(response)
    if state["lastSymbol"] != "FAKE" or not -2 <= time.time() - state["timestamp"] < 10:
        raise ValueError("Strategy is not fresh")
    return state["timestamp"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster", required=True)
    parser.add_argument("--service", choices=["market-data", "strategy-engine", "api-gateway"], required=True)
    parser.add_argument("--url", required=True, help="Public HTTPS API base URL")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = new_report(root, "ecs-task-restart", {
        "cluster": args.cluster, "service": args.service,
        "url": args.url, "recovery_timeout_seconds": 180,
        "poll_interval_seconds": 5, "sustained_recovery_samples": 3,
        "timing_semantics": "Task replacement, service count and three advancing fresh public responses",
    })
    report["service"] = args.service
    try:
        baseline = fresh(args.url)
        service = aws("describe-services", "--cluster", args.cluster, "--services", args.service)["services"][0]
        if service["desiredCount"] < 1 or service["runningCount"] != service["desiredCount"]:
            raise RuntimeError("Service is not stable before injection")
        tasks = aws("list-tasks", "--cluster", args.cluster, "--service-name", args.service)["taskArns"]
        if not tasks:
            raise RuntimeError("No running task to inject")
        victim = tasks[0]
        report["stopped_task"] = victim
        started = time.monotonic()
        aws("stop-task", "--cluster", args.cluster, "--task", victim, "--reason", "Reliability recovery experiment")
        deadline = time.monotonic() + 180
        consecutive = 0
        while time.monotonic() < deadline:
            try:
                replacement = aws("list-tasks", "--cluster", args.cluster, "--service-name", args.service)["taskArns"]
                state = aws("describe-services", "--cluster", args.cluster, "--services", args.service)["services"][0]
                timestamp = fresh(args.url)
                healthy = (victim not in replacement and bool(set(replacement) - set(tasks))
                           and state["runningCount"] == state["desiredCount"] and timestamp > baseline)
                consecutive = consecutive + 1 if healthy else 0
                baseline = timestamp
                if consecutive >= 3:
                    report.update(passed=True, recovery_seconds=round(time.monotonic() - started, 2))
                    return
            except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                consecutive = 0
            time.sleep(5)
        raise TimeoutError("ECS replacement and sustained freshness did not recover")
    except BaseException as error:
        report["error"] = str(error)
        raise
    finally:
        save_report(root, report, f"aws-restart-{args.service}")
        print(json.dumps(report))


if __name__ == "__main__":
    main()
