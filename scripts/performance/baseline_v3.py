
#!/usr/bin/env python3
"""Read-only, scrape-aware Prometheus performance baseline collector."""

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


REQUIRED_COUNTERS = {
    "producer_messages": "market_data_messages_published_total",
    "consumer_ticks": "strategy_ticks_total",
    "strategy_errors": "strategy_errors_total",
    "producer_errors": "market_data_publish_errors_total",
}

# Verify these names against application instrumentation.
# Missing optional metrics are reported, never interpreted as zero.
OPTIONAL_COUNTERS = {
    "strategy_stale": "strategy_stale_ticks_total",
    "strategy_duplicates": "strategy_duplicate_ticks_total",
    "strategy_gaps": "strategy_sequence_gaps_total",
}

HISTOGRAMS = {
    "producer_latency": "price_tick_latency_seconds_bucket",
    "end_to_end_latency": "strategy_tick_latency_seconds_bucket",
    "processing_latency": "strategy_processing_time_seconds_bucket",
}

LAG_METRIC = "kafka_consumergroup_lag"


def utc(timestamp):
    return datetime.fromtimestamp(
        timestamp, timezone.utc
    ).isoformat()


def prometheus_query(base, expression, start, end, step):
    params = urlencode({
        "query": expression,
        "start": start,
        "end": end,
        "step": step,
    })

    url = (
        base.rstrip("/")
        + "/api/v1/query_range?"
        + params
    )

    with urlopen(url, timeout=30) as response:
        payload = json.load(response)

    if payload.get("status") != "success":
        raise RuntimeError(
            f"Prometheus query failed: {expression}: "
            f"{payload.get('error', 'unknown error')}"
        )

    return payload["data"]["result"]


def series_key(labels):
    """Match Prometheus series using identifying labels.

    PromQL timestamp() drops the metric-name label, so
    __name__ must not participate in the series key.
    """
    return tuple(sorted(
        (key, value)
        for key, value in labels.items()
        if key != "__name__"
    ))


def scrape_samples(base, expression, start, end, step):
    """
    Pair query_range values with timestamp(metric) values.

    query_range timestamps are evaluation times.
    timestamp(metric) exposes the underlying scrape times.

    Duplicate evaluations of the same scrape are removed.
    """
    values = prometheus_query(
        base, expression, start, end, step
    )

    timestamps = prometheus_query(
        base,
        f"timestamp({expression})",
        start,
        end,
        step,
    )

    time_lookup = {
        series_key(item["metric"]): item["values"]
        for item in timestamps
    }

    output = {}

    for item in values:
        labels = item["metric"]
        key = series_key(labels)

        if key not in time_lookup:
            raise RuntimeError(
                f"Missing scrape timestamps for {expression}: {labels}"
            )

        raw_values = item["values"]
        raw_times = time_lookup[key]

        if len(raw_values) != len(raw_times):
            raise RuntimeError(
                f"Sample alignment mismatch: {expression}"
            )

        unique = {}

        for value_sample, time_sample in zip(
            raw_values, raw_times
        ):
            evaluation_time, value_text = value_sample
            time_evaluation, scrape_text = time_sample

            if abs(evaluation_time - time_evaluation) > 0.001:
                raise RuntimeError(
                    f"Evaluation timestamp mismatch: {expression}"
                )

            scrape_time = float(scrape_text)
            value = float(value_text)

            if not math.isfinite(value):
                raise RuntimeError(
                    f"Non-finite metric value: {expression}"
                )

            if not math.isfinite(scrape_time):
                raise RuntimeError(
                    f"Invalid scrape timestamp: {expression}"
                )

            # Keep only scrapes inside the requested window.
            if not start <= scrape_time <= end:
                continue

            if scrape_time in unique and unique[scrape_time] != value:
                raise RuntimeError(
                    f"Conflicting scrape values: {expression}"
                )

            unique[scrape_time] = value

        samples = sorted(unique.items())

        if len(samples) >= 2:
            output[key] = {
                "labels": labels,
                "samples": samples,
            }

    return output


def require_one_series(series, name):
    if len(series) != 1:
        raise RuntimeError(
            f"Expected one series for {name}; found {len(series)}"
        )

    return next(iter(series.values()))["samples"]


def validate_samples(samples, name, step):
    if len(samples) < 2:
        raise RuntimeError(
            f"Insufficient samples: {name}"
        )

    for previous, current in zip(samples, samples[1:]):
        if current[0] <= previous[0]:
            raise RuntimeError(
                f"Non-increasing timestamps: {name}"
            )

        # Conservative gap threshold for the configured
        # five-second scrape cadence.
        if current[0] - previous[0] > max(step * 2.5, 15):
            raise RuntimeError(
                f"Scrape gap detected: {name}"
            )


def counter_result(samples, name, step):
    validate_samples(samples, name, step)

    for previous, current in zip(samples, samples[1:]):
        if current[1] < previous[1]:
            raise RuntimeError(
                f"Counter reset detected: {name}"
            )

    first_time, first_value = samples[0]
    last_time, last_value = samples[-1]

    elapsed = last_time - first_time
    delta = last_value - first_value

    return {
        "delta": delta,
        "elapsed_seconds": elapsed,
        "rate_per_second": delta / elapsed,
        "sample_count": len(samples),
        "first_sample_utc": utc(first_time),
        "last_sample_utc": utc(last_time),
    }


def collect_counter(
    base, name, metric, start, end, step
):
    series = scrape_samples(
        base, metric, start, end, step
    )

    samples = require_one_series(series, name)

    return counter_result(samples, name, step)


def histogram_quantile(buckets, quantile):
    ordered = sorted(
        (
            (
                math.inf if boundary == "+Inf"
                else float(boundary),
                count,
            )
            for boundary, count in buckets.items()
        ),
        key=lambda item: item[0],
    )

    total = ordered[-1][1]

    if total <= 0:
        return None

    rank = total * quantile
    previous_count = 0.0
    previous_upper = 0.0

    for upper, count in ordered:
        if count >= rank:
            # The final bucket is unbounded.
            # Do not fabricate a finite quantile.
            if math.isinf(upper):
                return None

            bucket_population = count - previous_count

            if bucket_population <= 0:
                return upper * 1000

            fraction = (
                rank - previous_count
            ) / bucket_population

            return (
                previous_upper
                + fraction * (upper - previous_upper)
            ) * 1000

        previous_count = count
        previous_upper = upper

    return None


def collect_histogram(
    base, name, metric, start, end, step
):
    series = scrape_samples(
        base, metric, start, end, step
    )

    if not series:
        raise RuntimeError(
            f"Missing histogram: {metric}"
        )

    buckets = {}

    for item in series.values():
        labels = item["labels"]

        if "le" not in labels:
            raise RuntimeError(
                f"Histogram bucket missing le: {metric}"
            )

        boundary = labels["le"]

        if boundary in buckets:
            raise RuntimeError(
                f"Multiple series for bucket {boundary}: {metric}"
            )

        samples = item["samples"]
        validate_samples(
            samples, f"{name}:{boundary}", step
        )

        buckets[boundary] = samples

    if "+Inf" not in buckets:
        raise RuntimeError(
            f"Missing +Inf bucket: {metric}"
        )

    # All buckets must cover the same scrape timestamps.
    reference_times = [
        timestamp for timestamp, _ in buckets["+Inf"]
    ]

    for boundary, samples in buckets.items():
        times = [timestamp for timestamp, _ in samples]

        if times != reference_times:
            raise RuntimeError(
                f"Histogram scrape mismatch: {metric}:{boundary}"
            )

    deltas = {}

    for boundary, samples in buckets.items():
        result = counter_result(
            samples, f"{name}:{boundary}", step
        )
        deltas[boundary] = result["delta"]

    ordered = sorted(
        deltas.items(),
        key=lambda item: (
            math.inf if item[0] == "+Inf"
            else float(item[0])
        ),
    )

    previous_count = 0.0

    for boundary, count in ordered:
        if count < previous_count:
            raise RuntimeError(
                f"Invalid cumulative histogram: {metric}:{boundary}"
            )

        previous_count = count

    observations = deltas["+Inf"]

    return {
        "observations": observations,
        "p50_ms": histogram_quantile(deltas, 0.50),
        "p95_ms": histogram_quantile(deltas, 0.95),
        "p99_ms": histogram_quantile(deltas, 0.99),
        "first_sample_utc": utc(reference_times[0]),
        "last_sample_utc": utc(reference_times[-1]),
        "bucket_deltas": deltas,
    }


def collect_lag(base, topic, start, end, step):
    expression = (
        f'{LAG_METRIC}{{topic="{topic}"}}'
    )

    series = scrape_samples(
        base, expression, start, end, step
    )

    if not series:
        raise RuntimeError(
            f"Kafka lag metric unavailable: {expression}"
        )

    # Preserve partition-level series and aggregate
    # by scrape timestamp.
    totals = {}

    for item in series.values():
        samples = item["samples"]
        validate_samples(samples, "kafka_lag", step)

        for timestamp, value in samples:
            if value < 0:
                raise RuntimeError(
                    "Negative Kafka lag observed"
                )

            totals[timestamp] = totals.get(
                timestamp, 0.0
            ) + value

    # Require every partition series to have the
    # same timestamps before aggregation.
    timestamp_sets = [
        set(t for t, _ in item["samples"])
        for item in series.values()
    ]

    if any(s != timestamp_sets[0] for s in timestamp_sets):
        raise RuntimeError(
            "Kafka lag partition scrape mismatch"
        )

    values = [
        value for _, value in sorted(totals.items())
    ]

    return {
        "initial": values[0],
        "final": values[-1],
        "maximum": max(values),
        "mean": sum(values) / len(values),
        "sample_count": len(values),
        "series_count": len(series),
    }


def docker_metadata(container):
    try:
        raw = subprocess.check_output(
            [
                "docker", "inspect", container,
                "--format",
                "{{json .}}",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        )

        data = json.loads(raw)

        allowed = {
            "TICK_INTERVAL_SECONDS",
            "MARKET_SYMBOLS",
            "KAFKA_TICKS_TOPIC",
        }

        environment = {}

        for item in data["Config"]["Env"]:
            if "=" not in item:
                continue

            key, value = item.split("=", 1)

            if key in allowed:
                environment[key] = value

        host_config = data.get("HostConfig", {})

        return {
            "container": container,
            "image": data["Config"].get("Image"),
            "container_id": data.get("Id", "")[:12],
            "started_at": data["State"].get("StartedAt"),
            "restart_count": data.get("RestartCount"),
            "environment": environment,
            "resource_limits": {
                "memory_bytes": host_config.get("Memory"),
                "nano_cpus": host_config.get("NanoCpus"),
                "cpu_quota": host_config.get("CpuQuota"),
                "cpu_period": host_config.get("CpuPeriod"),
            },
        }

    except (
        OSError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
    ) as exc:
        return {
            "container": container,
            "status": "unavailable",
            "error": str(exc),
        }


def git_metadata():
    def git(*args):
        try:
            return subprocess.check_output(
                ["git", *args],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    status = git("status", "--porcelain")

    return {
        "commit": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "dirty": bool(status) if status is not None else None,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Scrape-aware performance baseline"
    )

    parser.add_argument(
        "--prometheus",
        default="http://localhost:9090",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=300,
    )
    parser.add_argument(
        "--step",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--container",
        default="mdp-market-data",
    )
    parser.add_argument(
        "--topic",
        default="ticks-v1",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/performance",
    )

    args = parser.parse_args()

    if args.duration < 30:
        parser.error(
            "duration must be at least 30 seconds"
        )

    if args.step <= 0:
        parser.error(
            "step must be positive"
        )

    print("Starting performance baseline v3")
    print(f"Duration: {args.duration}s")
    print(f"Query step: {args.step}s")
    print(f"Kafka topic: {args.topic}")

    workload_before = docker_metadata(args.container)

    started = time.time()

    print("Observing workload...")
    time.sleep(args.duration)

    finished = time.time()

    # Wait for the final requested interval to
    # become visible in Prometheus.
    time.sleep(max(7, args.step + 2))

    counters = {}
    unavailable_optional = {}

    print("Collecting counters...")

    for name, metric in REQUIRED_COUNTERS.items():
        counters[name] = collect_counter(
            args.prometheus,
            name,
            metric,
            started,
            finished,
            args.step,
        )

    for name, metric in OPTIONAL_COUNTERS.items():
        series = scrape_samples(
            args.prometheus,
            metric,
            started,
            finished,
            args.step,
        )

        if not series:
            counters[name] = None
            unavailable_optional[name] = metric

            print(
                f"WARN: Optional metric unavailable: {metric}"
            )
            continue

        samples = require_one_series(series, name)

        counters[name] = counter_result(
            samples, name, args.step
        )

    print("Collecting histograms...")

    histograms = {}

    for name, metric in HISTOGRAMS.items():
        histograms[name] = collect_histogram(
            args.prometheus,
            name,
            metric,
            started,
            finished,
            args.step,
        )

    print("Collecting Kafka lag...")

    lag = collect_lag(
        args.prometheus,
        args.topic,
        started,
        finished,
        args.step,
    )

    workload_after = docker_metadata(args.container)

    if (
        workload_before.get("container_id")
        and workload_after.get("container_id")
        and (
            workload_before.get("container_id")
            != workload_after.get("container_id")
            or workload_before.get("started_at")
            != workload_after.get("started_at")
            or workload_before.get("restart_count")
            != workload_after.get("restart_count")
        )
    ):
        raise RuntimeError(
            "Producer container restarted during benchmark"
        )

    producer = counters["producer_messages"]
    consumer = counters["consumer_ticks"]

    report = {
        "schema_version": 3,
        "measurement": {
            "started_at_utc": utc(started),
            "finished_at_utc": utc(finished),
            "requested_duration_seconds": args.duration,
            "query_step_seconds": args.step,
            "timestamp_source": "prometheus_scrape",
            "method": "observed_counter_deltas",
        },
        "git": git_metadata(),
        "host": {
            "hostname": platform.node(),
            "kernel": platform.release(),
            "cpu_count": __import__("os").cpu_count(),
        },
        "workload": workload_after,
        "throughput": {
            "producer_messages_per_second":
                producer["rate_per_second"],
            "consumer_ticks_per_second":
                consumer["rate_per_second"],
        },
        "counters": counters,
        "latency": histograms,
        "kafka_lag": lag,
        "unavailable_optional_metrics": unavailable_optional,
        "validation": {
            "required_metrics_present": True,
            "observed_counter_resets": False,
            "histogram_consistency": "passed",
            "producer_container_unchanged": (
                workload_before.get("container_id")
                == workload_after.get("container_id")
                and workload_before.get("started_at")
                == workload_after.get("started_at")
            ) if workload_before.get("container_id") else None,
            "status": "passed_with_limitations",
            "limitations": [
                "Counter resets between observed scrapes may be undetectable.",
                "Different metric families have independently scheduled scrape boundaries.",
                "Histogram quantiles are bucket-interpolated estimates.",
                "Counter values may include durable state restored before this run.",
            ],
        },
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    run_id = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")

    output = (
        output_dir
        / f"baseline-v3-{run_id}.json"
    )

    output.write_text(
        json.dumps(report, indent=2) + "\n"
    )

    print()
    print("=== Performance Baseline v3 ===")
    print(json.dumps({
        "throughput": report["throughput"],
        "latency": {
            name: {
                key: value
                for key, value in data.items()
                if key in (
                    "observations",
                    "p50_ms",
                    "p95_ms",
                    "p99_ms",
                )
            }
            for name, data in histograms.items()
        },
        "kafka_lag": lag,
        "unavailable_optional_metrics": unavailable_optional,
        "validation": report["validation"],
    }, indent=2))

    print(f"\nBaseline saved: {output}")


if __name__ == "__main__":
    main()
