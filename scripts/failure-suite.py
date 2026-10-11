#!/usr/bin/env python3
"""Bounded Compose fault exercises with restoration and JSON evidence."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from evidence import compose_workload, new_report, save_report

ROOT = Path(__file__).resolve().parents[1]
API = f"http://localhost:{os.getenv('API_PORT', '8000')}"
PROM = f"http://localhost:{os.getenv('PROMETHEUS_PORT', '9090')}"


def compose(*args):
    subprocess.run(["docker", "compose", *args], cwd=ROOT, check=True, timeout=45)


def request(url):
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, None


def query(expression):
    status, body = request(PROM + "/api/v1/query?" + urllib.parse.urlencode({"query": expression}))
    if status != 200 or body.get("status") != "success":
        raise RuntimeError("Prometheus query failed")
    return body["data"]["result"]


def eventually(check, timeout):
    deadline = time.monotonic() + timeout
    last = "condition not met"
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
            last = str(error)
        time.sleep(2)
    raise TimeoutError(last)


def interrupted(signum, frame):
    raise KeyboardInterrupt(f"signal {signum}")


def run(scenario):
    if scenario == "malformed-tick":
        return malformed_tick()
    service = {"consumer": "strategy-engine", "producer": "market-data", "broker": "kafka",
               "strategy-restart": "strategy-engine", "scrape-loss": "reliability-probe"}[scenario]
    alert = ('ALERTS{alertname="StaleStrategyData",alertstate="firing"}' if scenario != "consumer"
             else 'ALERTS{alertname="TradingServiceDown",job="strategy-engine",alertstate="firing"}')
    if scenario == "strategy-restart":
        alert = 'ALERTS{alertname="TradingServiceDown",job="strategy-engine",alertstate="firing"}'
    if scenario == "scrape-loss":
        alert = 'ALERTS{alertname="ReliabilityProbeMissing",alertstate="firing"}'
    restore_action = "start" if scenario == "strategy-restart" else "unpause"
    report = new_report(ROOT, scenario, {
        "injection": "stop/start" if scenario == "strategy-restart" else "pause/unpause",
        "service": service,
        "baseline_timeout_seconds": 120,
        "detection_timeout_seconds": 180 if scenario == "scrape-loss" else 60,
        "recovery_timeout_seconds": 120,
        "poll_interval_seconds": 2,
        "lag_threshold": 10,
        "sustained_recovery_samples": 3,
        "timing_semantics": "Detection includes HTTP degradation and firing alert; recovery includes alert clearance and sustained fresh progress",
    })
    report["workload"] = compose_workload(ROOT)
    changed = False
    try:
        eventually(lambda: request(API + "/ready")[0] == 200, 120)
        started = time.monotonic()
        # Mark before issuing the command so an interrupted command is restored too.
        changed = True
        compose("stop" if scenario == "strategy-restart" else "pause", service)
        expected_status = 200 if scenario == "scrape-loss" else 503
        eventually(lambda: request(API + "/ready")[0] == expected_status and bool(query(alert)),
                   180 if scenario == "scrape-loss" else 60)
        report["detection_seconds"] = round(time.monotonic() - started, 2)
        if scenario == "consumer":
            request_started = time.monotonic()
            if request(API + "/strategy")[0] != 503:
                raise RuntimeError("Paused upstream must return a controlled failure")
            report["upstream_timeout_seconds"] = time.monotonic() - request_started
            if report["upstream_timeout_seconds"] > 5:
                raise RuntimeError("Upstream timeout exceeded the five-second request bound")
            eventually(lambda: any(float(row["value"][1]) > 0 for row in query(
                'sum(kafka_consumergroup_lag{consumergroup="strategy-engine-v1"})')), 30)
            report["observed_lag_at_detection"] = float(query(
                'sum(kafka_consumergroup_lag{consumergroup="strategy-engine-v1"})')[0]["value"][1])
        compose(restore_action, service)
        changed = False
        started = time.monotonic()
        eventually(lambda: request(API + "/ready")[0] == 200 and not query(alert), 120)
        if scenario == "consumer":
            eventually(lambda: any(float(row["value"][1]) <= 10 for row in query(
                'sum(kafka_consumergroup_lag{consumergroup="strategy-engine-v1"})')), 30)
        # Require advancing source timestamps, not just a healthy HTTP process.
        _, state = request(API + "/strategy")
        previous = state["timestamp"]
        for _ in range(3):
            eventually(lambda: request(API + "/strategy")[1]["timestamp"] > previous, 30)
            time.sleep(2)
            status, state = request(API + "/strategy")
            if status != 200 or state["ageSeconds"] >= 10:
                raise RuntimeError("Recovery did not remain fresh")
            previous = state["timestamp"]
        report["recovery_seconds"] = round(time.monotonic() - started, 2)
        report["passed"] = True
    except BaseException as error:
        report["error"] = str(error)
        raise
    finally:
        try:
            if changed:
                try:
                    compose(restore_action, service)
                except BaseException as restore_error:
                    report["passed"] = False
                    report["restoration_error"] = str(restore_error)
                    raise
        finally:
            save_report(ROOT, report, f"fault-{scenario}")
            print(json.dumps(report))


def malformed_tick():
    report = new_report(ROOT, "malformed-tick", {
        "injection": "publish-invalid-payloads", "topic": "ticks-v1",
        "payloads": ["not-json", "null"], "expected_new_errors": 2,
        "baseline_timeout_seconds": 120, "detection_timeout_seconds": 30,
        "poll_interval_seconds": 2,
    })
    report["workload"] = compose_workload(ROOT)
    try:
        eventually(lambda: request(API + "/ready")[0] == 200, 120)
        before_errors = float(query("sum(strategy_errors_total)")[0]["value"][1])
        _, state = request(API + "/strategy")
        before_timestamp = state["timestamp"]
        subprocess.run(["docker", "compose", "exec", "-T", "kafka", "kafka-console-producer",
                        "--bootstrap-server", "kafka:9092", "--topic", "ticks-v1"],
                       input="not-json\nnull\n", text=True, cwd=ROOT, check=True, timeout=30)
        eventually(lambda: float(query("sum(strategy_errors_total)")[0]["value"][1]) >= before_errors + 2, 30)
        eventually(lambda: request(API + "/strategy")[1]["timestamp"] > before_timestamp, 30)
        report["passed"] = True
    except BaseException as error:
        report["error"] = str(error)
        raise
    finally:
        save_report(ROOT, report, "fault-malformed-tick")
        print(json.dumps(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    scenarios = ["consumer", "producer", "broker", "strategy-restart", "malformed-tick", "scrape-loss"]
    parser.add_argument("scenario", choices=[*scenarios, "all"])
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    for name in (scenarios if args.scenario == "all" else [args.scenario]):
        run(name)
