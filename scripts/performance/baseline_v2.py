#!/usr/bin/env python3
"""Read-only performance baseline using Prometheus counter deltas."""

import argparse
import json
import math
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


COUNTERS = {
    "producer_messages": "market_data_messages_published_total",
    "consumer_ticks": "strategy_ticks_total",
    "strategy_errors": "strategy_errors_total",
    "producer_errors": "market_data_publish_errors_total",
}

HISTOGRAMS = {
    "producer_latency": "price_tick_latency_seconds_bucket",
    "end_to_end_latency": "strategy_tick_latency_seconds_bucket",
    "processing_latency": "strategy_processing_time_seconds_bucket",
}


def api_query(base, expression):
    url = base.rstrip("/") + "/api/v1/query?" + urlencode({
        "query": expression,
    })

    with urlopen(url, timeout=15) as response:
        payload = json.load(response)

    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {expression}")

    return payload["data"]["result"]


def scalar(base, expression):
    result = api_query(base, expression)

    if len(result) != 1:
        raise RuntimeError(f"Missing or ambiguous metric: {expression}")

    value = float(result[0]["value"][1])

    if not math.isfinite(value):
        raise RuntimeError(f"Non-finite metric: {expression}")

    return value


def histogram(base, metric):
    result = api_query(base, f"sum by (le) ({metric})")

    buckets = {}

    for item in result:
        label = item["metric"]["le"]
        buckets[label] = float(item["value"][1])

    if "+Inf" not in buckets:
        raise RuntimeError(f"Missing +Inf bucket: {metric}")

    return buckets


def snapshot(base):
    counters = {
        name: scalar(base, f"sum({metric})")
        for name, metric in COUNTERS.items()
    }

    histograms = {
        name: histogram(base, metric)
        for name, metric in HISTOGRAMS.items()
    }

    lag = scalar(
        base,
        'sum(kafka_consumergroup_lag{topic="ticks-v1"})',
    )

    return {
        "time": time.time(),
        "counters": counters,
        "histograms": histograms,
        "kafka_lag": lag,
    }


def quantile_from_buckets(start, end, quantile):
    buckets = []

    for boundary, final_count in end.items():
        if boundary not in start:
            raise RuntimeError(f"Missing initial bucket {boundary}")

        delta = final_count - start[boundary]

        if delta < 0:
            raise RuntimeError("Histogram bucket counter reset detected")

        upper = (
            math.inf if boundary == "+Inf" else float(boundary)
        )

        buckets.append((upper, delta))

    buckets.sort(key=lambda item: item[0])

    total = buckets[-1][1]

    if total <= 0:
        return None

    rank = quantile * total
    previous_count = 0.0
    previous_upper = 0.0

    for upper, count in buckets:
        if count >= rank:
            if math.isinf(upper):
                return previous_upper * 1000

            bucket_count = count - previous_count

            if bucket_count <= 0:
                return upper * 1000

            fraction = (rank - previous_count) / bucket_count

            return (
                previous_upper
                + (upper - previous_upper) * fraction
            ) * 1000

        previous_count = count
        previous_upper = upper

    return None


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
    parser.add_argument(
        "--output-dir",
        default="artifacts/performance",
    )
    args = parser.parse_args()

    if args.duration <= 0:
        parser.error("duration must be positive")

    print("Capturing initial performance counters...")
    before = snapshot(args.prometheus)

    print(f"Observing workload for {args.duration} seconds...")
    time.sleep(args.duration)

    print("Capturing final performance counters...")
    after = snapshot(args.prometheus)

    elapsed = after["time"] - before["time"]

    counter_deltas = {}
    for name in COUNTERS:
        delta = (
            after["counters"][name]
            - before["counters"][name]
        )

        if delta < 0:
            raise RuntimeError(f"Counter reset: {name}")

        counter_deltas[name] = delta

    latency = {
        name: {
            "p50_ms": quantile_from_buckets(
                before["histograms"][name],
                after["histograms"][name],
                0.50,
            ),
            "p95_ms": quantile_from_buckets(
                before["histograms"][name],
                after["histograms"][name],
                0.95,
            ),
            "p99_ms": quantile_from_buckets(
                before["histograms"][name],
                after["histograms"][name],
                0.99,
            ),
        }
        for name in HISTOGRAMS
    }

    report = {
        "schema_version": 2,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_revision(),
        "host": {
            "hostname": platform.node(),
            "kernel": platform.release(),
        },
        "elapsed_seconds": elapsed,
        "counter_deltas": counter_deltas,
        "throughput": {
            "producer_messages_per_second":
                counter_deltas["producer_messages"] / elapsed,
            "consumer_ticks_per_second":
                counter_deltas["consumer_ticks"] / elapsed,
        },
        "latency": latency,
        "kafka_lag": {
            "initial": before["kafka_lag"],
            "final": after["kafka_lag"],
        },
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    output = output_dir / f"baseline-v2-{run_id}.json"
    output.write_text(json.dumps(report, indent=2) + "\n")

    print(json.dumps(report, indent=2))
    print(f"\nSaved: {output}")


if __name__ == "__main__":
    main()
