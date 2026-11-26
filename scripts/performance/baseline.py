#!/usr/bin/env python3
"""Capture a read-only Prometheus performance baseline."""

import argparse
import json
import math
import os
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


QUERIES = {
    "producer_messages_per_second":
        "sum(rate(market_data_messages_published_total[5m]))",
    "consumer_ticks_per_second":
        "sum(rate(strategy_ticks_total[5m]))",
    "producer_p95_ms":
        "1000 * histogram_quantile(0.95, sum by (le) (rate(price_tick_latency_seconds_bucket[5m])))",
    "end_to_end_p95_ms":
        "1000 * histogram_quantile(0.95, sum by (le) (rate(strategy_tick_latency_seconds_bucket[5m])))",
    "processing_p95_ms":
        "1000 * histogram_quantile(0.95, sum by (le) (rate(strategy_processing_time_seconds_bucket[5m])))",
    "kafka_consumer_lag":
        'sum(kafka_consumergroup_lag{topic="ticks-v1"})',
    "strategy_errors_per_second":
        "sum(rate(strategy_errors_total[5m]))",
}


def query_prometheus(base_url, expression, timestamp):
    params = urlencode({"query": expression, "time": timestamp})
    url = f"{base_url.rstrip('/')}/api/v1/query?{params}"

    with urlopen(url, timeout=15) as response:
        payload = json.load(response)

    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {expression}")

    results = payload.get("data", {}).get("result", [])
    if len(results) != 1:
        return None

    value = float(results[0]["value"][1])
    return value if math.isfinite(value) else None


def git_revision():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prometheus",
        default="http://localhost:9090",
    )
    parser.add_argument("--duration", type=int, default=300)
    parser.add_argument("--interval", type=int, default=15)
    parser.add_argument(
        "--output-dir",
        default="artifacts/performance",
    )
    args = parser.parse_args()

    if args.duration <= 0 or args.interval <= 0:
        parser.error("duration and interval must be positive")

    started = datetime.now(timezone.utc)
    samples = []
    start_monotonic = time.monotonic()
    next_sample = start_monotonic

    print("Starting read-only performance baseline")
    print(f"Duration: {args.duration}s")
    print(f"Sampling interval: {args.interval}s")
    
    while True:
        now = time.monotonic()
        if now >= start_monotonic + args.duration:
            break

        if now < next_sample:
            time.sleep(next_sample - now)

        if time.monotonic() >= start_monotonic + args.duration:
            break


        timestamp = time.time()
        values = {}

        for name, expression in QUERIES.items():
            try:
                values[name] = query_prometheus(
                    args.prometheus,
                    expression,
                    timestamp,
                )
            except Exception as exc:
                print(f"WARN {name}: {exc}")
                values[name] = None

        samples.append({
            "timestamp_utc": datetime.fromtimestamp(
                timestamp, timezone.utc
            ).isoformat(),
            "metrics": values,
        })

        print(
            f"sample={len(samples)} "
            f"producer={values['producer_messages_per_second']} "
            f"consumer={values['consumer_ticks_per_second']} "
            f"lag={values['kafka_consumer_lag']}"
        )

        next_sample += args.interval

    summary = {}
    for name in QUERIES:
        observed = [
            sample["metrics"][name]
            for sample in samples
            if sample["metrics"][name] is not None
        ]
        summary[name] = {
            "sample_count": len(observed),
            "min": min(observed) if observed else None,
            "max": max(observed) if observed else None,
            "mean": (
                sum(observed) / len(observed)
                if observed else None
            ),
        }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    output = output_dir / f"baseline-{run_id}.json"

    report = {
        "schema_version": 1,
        "run_id": run_id,
        "started_at_utc": started.isoformat(),
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": args.duration,
        "sample_interval_seconds": args.interval,
        "prometheus": args.prometheus,
        "git_commit": git_revision(),
        "host": {
            "hostname": platform.node(),
            "kernel": platform.release(),
            "cpu_count": os.cpu_count(),
        },
        "summary": summary,
        "samples": samples,
    }

    output.write_text(json.dumps(report, indent=2) + "\n")

    print(f"\nBaseline saved: {output}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
