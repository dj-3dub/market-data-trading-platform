#!/usr/bin/env python3
"""
Prometheus Doctor

Quickly inspects a Prometheus server and reports:
- Server reachability & version
- Target health for key jobs (market-data, strategy-engine, api-gateway)
- Whether key metrics (strategy_last_price, api_requests_total) have samples

Usage:
  PROM_URL=http://localhost:9091 python3 prometheus_doctor.py
  # or just:
  python3 prometheus_doctor.py          # defaults to http://localhost:9091
"""

import json
import os
import sys
import urllib.request
import urllib.error
from typing import Any, Dict, List


def http_get_json(url: str) -> Dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = resp.read()
        return json.loads(data.decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"[ERROR] Failed to GET {url}: {e}")
        return {}
    except json.JSONDecodeError:
        print(f"[ERROR] Failed to parse JSON from {url}")
        return {}


def print_header(title: str):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main():
    base_url = os.getenv("PROM_URL", "http://localhost:9091")
    print_header(f"Prometheus Doctor - Target: {base_url}")

    # 1) Check basic server status
    status_url = f"{base_url}/api/v1/status/runtimeinfo"
    status = http_get_json(status_url)
    if not status or status.get("status") != "success":
        print("[FATAL] Could not reach Prometheus or bad response from /status/runtimeinfo")
        sys.exit(1)

    data = status.get("data", {})
    start_time = data.get("startTime", "unknown")
    version = data.get("version", "unknown")

    print(f"[OK] Prometheus reachable.")
    print(f"     Version    : {version}")
    print(f"     Start time : {start_time}")

    # 2) Inspect active targets
    print_header("Active Targets")

    targets_url = f"{base_url}/api/v1/targets"
    targets_resp = http_get_json(targets_url)
    active_targets: List[Dict[str, Any]] = targets_resp.get("data", {}).get("activeTargets", [])

    if not active_targets:
        print("[WARN] No active targets found. Prometheus isn't scraping anything.")
    else:
        for t in active_targets:
            labels = t.get("labels", {})
            job = labels.get("job", "unknown")
            instance = labels.get("instance", "unknown")
            health = t.get("health", "unknown")
            last_scrape = t.get("lastScrape", "unknown")
            last_error = t.get("lastError", "")

            print(f"- job={job} instance={instance} health={health} lastScrape={last_scrape}")
            if last_error:
                print(f"  lastError: {last_error}")

    # 3) Check specific jobs we care about
    print_header("Key Jobs Health (using `up` metric)")

    jobs_of_interest = ["market-data", "strategy-engine", "api-gateway"]

    for job in jobs_of_interest:
        query = f"up{{job=\"{job}\"}}"
        url = f"{base_url}/api/v1/query?query={urllib.parse.quote(query)}"
        resp = http_get_json(url)

        results = resp.get("data", {}).get("result", [])
        if not results:
            print(f"[WARN] job={job} -> no 'up' series found. Not being scraped or misconfigured target.")
            continue

        # Ideally there is one series per instance
        for r in results:
            metric = r.get("metric", {})
            value = r.get("value", [])
            instance = metric.get("instance", "unknown")
            status_val = value[1] if len(value) > 1 else "?"
            if status_val == "1":
                print(f"[OK] job={job} instance={instance} is UP (up=1).")
            else:
                print(f"[WARN] job={job} instance={instance} is DOWN (up={status_val}).")

    # 4) Check for key metrics: strategy_last_price & api_requests_total
    print_header("Key Metrics Presence")

    key_metrics = [
        "strategy_last_price",
        "strategy_trades_total",
        "api_requests_total",
        "api_request_duration_seconds_bucket",
    ]

    for metric in key_metrics:
        query = metric
        url = f"{base_url}/api/v1/query?query={urllib.parse.quote(query)}"
        resp = http_get_json(url)
        results = resp.get("data", {}).get("result", [])

        if not results:
            print(f"[WARN] Metric `{metric}` -> no samples found.")
        else:
            samples = len(results)
            print(f"[OK] Metric `{metric}` has {samples} time series.")
            # Show one example
            example = results[0]
            metric_labels = example.get("metric", {})
            value = example.get("value", [])
            print(f"     Example labels: {metric_labels}")
            print(f"     Example value : {value}")

    print_header("Summary")
    print("If jobs show as [OK] and key metrics have samples, Prometheus is collecting data correctly.")
    print("If jobs are missing or metrics have no samples, check:")
    print("- docker-compose.yml: Prometheus service volume mounts and port mapping")
    print("- monitoring/prometheus/prometheus.yml: scrape_configs & target names")
    print("- Service containers: are they up and exposing /metrics on the expected ports?")
    print("- Docker network: Prometheus can reach 'market-data:7001', 'strategy-engine:7002', 'api-gateway:8000'")

    print("\nDone.")


if __name__ == "__main__":
    # urllib.parse is only needed at runtime, import here to avoid confusion above
    import urllib.parse  # noqa: E402
    main()
