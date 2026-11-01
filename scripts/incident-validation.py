#!/usr/bin/env python3

import argparse
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid

ALERTS = (
    "MarketDataFeedStale",
    "MarketDataUnresolvedGap",
    "MarketDataExporterDown",
)

METRICS = (
    "feed_sequence_gaps_total",
    "feed_gap_recoveries_total",
    "feed_unresolved_gaps",
    "feed_packets_received_total",
    "feed_sessions_total",
    "feed_stale",
)


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def get_json(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.load(response)


def prom_query(base, query):
    url = base.rstrip("/") + "/api/v1/query?" + urllib.parse.urlencode(
        {"query": query}
    )
    payload = get_json(url)
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {payload}")
    result = payload["data"]["result"]
    return float(result[0]["value"][1]) if len(result) == 1 else None


def alert_states(base):
    payload = get_json(base.rstrip("/") + "/api/v1/rules")
    found = {}
    for group in payload["data"]["groups"]:
        for rule in group["rules"]:
            name = rule.get("name")
            if name in ALERTS:
                found[name] = {
                    "state": rule.get("state"),
                    "health": rule.get("health"),
                }
    return found


def snapshot(base):
    return {
        "at_utc": utcnow(),
        "up": prom_query(base, 'up{job="market-data-network"}'),
        "metrics": {
            key: prom_query(base, f'{key}{{job="market-data-network"}}')
            for key in METRICS
        },
        "alerts": alert_states(base),
    }


def wait_until(predicate, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if predicate():
                return True
        except (OSError, ValueError, KeyError, RuntimeError):
            pass
        time.sleep(2)
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--mode",
        choices=("health", "gap-replay", "stale-recovery"),
        default="health",
    )

    parser.add_argument(
        "--prometheus",
        default="http://127.0.0.1:9090",
    )

    parser.add_argument(
        "--sender",
        default="labs/market-data-network/feed_sender.py",
    )

    parser.add_argument(
        "--output-dir",
        default="artifacts/incidents",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=90,
    )

    parser.add_argument(
        "--pause-seconds",
        type=int,
        default=20,
    )

    parser.add_argument(
        "--rate",
        type=int,
        default=10,
    )

    args = parser.parse_args()

    report = {
        "schema_version": 1,
        "run_id": str(uuid.uuid4()),
        "mode": args.mode,
        "started_at_utc": utcnow(),
        "passed": False,
        "steps": [],
        "error": None,
    }

    def record(name, ok, details=None):
        report["steps"].append({
            "name": name,
            "passed": bool(ok),
            "at_utc": utcnow(),
            "details": details,
        })
        print(f'{"PASS" if ok else "FAIL"} {name}', flush=True)
        if not ok:
            raise RuntimeError(f"Validation failed: {name}")

    try:
        initial = snapshot(args.prometheus)
        report["initial"] = initial

        record(
            "prometheus_target_up",
            initial["up"] == 1,
            initial["up"],
        )

        record(
            "alert_rules_present_and_healthy",
            all(
                initial["alerts"].get(name, {}).get("health") == "ok"
                for name in ALERTS
            ),
            initial["alerts"],
        )

        if args.mode == "gap-replay":
            record(
                "no_existing_unresolved_gaps",
                initial["metrics"]["feed_unresolved_gaps"] == 0,
                initial["metrics"]["feed_unresolved_gaps"],
            )

            record(
                "gap_alert_initially_inactive",
                initial["alerts"]["MarketDataUnresolvedGap"]["state"]
                == "inactive",
            )

            sender = pathlib.Path(args.sender)
            record("sender_exists", sender.is_file(), str(sender))

            cmd = [
                sys.executable, str(sender),
                "--continuous", "--rate", "10",
                "--duration", "30",
                "--drop-sequence", "5",
            ]

            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=50
            )

            report["sender"] = {
                "command": cmd,
                "returncode": proc.returncode,
                "stdout": proc.stdout[-12000:],
                "stderr": proc.stderr[-4000:],
            }

            record("sender_completed", proc.returncode == 0)

            match = re.search(r"SESSION_ID=([\w-]+)", proc.stdout)
            record("sender_session_captured", match is not None)

            session_id = match.group(1)
            record(
                "drop_injected",
                "INJECTED_DROP seq=5" in proc.stdout,
            )

            gap_seen = wait_until(
                lambda: (
                    prom_query(
                        args.prometheus,
                        'feed_unresolved_gaps{job="market-data-network"}',
                    ) == 1
                    and alert_states(args.prometheus)
                    .get("MarketDataUnresolvedGap", {})
                    .get("state") == "firing"
                ),
                args.timeout,
            )

            report["gap_detected"] = snapshot(args.prometheus)
            record(
                "critical_gap_alert_firing",
                gap_seen,
                report["gap_detected"],
            )

            replay = [
                sys.executable, str(sender),
                "--replay",
                "--session-id", session_id,
                "--symbol", "FAKE",
                "--sequence", "5",
            ]

            result = subprocess.run(
                replay, capture_output=True, text=True, timeout=15
            )

            report["replay"] = {
                "command": replay,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }

            record(
                "replay_sent",
                result.returncode == 0
                and "REPLAY_SENT" in result.stdout,
            )

            base_recoveries = initial["metrics"][
                "feed_gap_recoveries_total"
            ]

            recovered = wait_until(
                lambda: (
                    prom_query(
                        args.prometheus,
                        'feed_unresolved_gaps{job="market-data-network"}',
                    ) == 0
                    and (
                        prom_query(
                            args.prometheus,
                            'feed_gap_recoveries_total{job="market-data-network"}',
                        ) or 0
                    ) > base_recoveries
                    and alert_states(args.prometheus)
                    .get("MarketDataUnresolvedGap", {})
                    .get("state") == "inactive"
                ),
                args.timeout,
            )

            report["recovered"] = snapshot(args.prometheus)
            record(
                "gap_recovered_and_alert_resolved",
                recovered,
                report["recovered"],
            )

        if args.mode == "stale-recovery":
            sender = pathlib.Path(args.sender)
            record("sender_exists", sender.is_file(), str(sender))

            record(
                "valid_sender_parameters",
                args.rate > 0 and args.pause_seconds >= 20,
                {
                    "rate": args.rate,
                    "pause_seconds": args.pause_seconds,
                },
            )

            # Allow enough time for Prometheus to observe
            # the healthy baseline, interruption, and recovery.
            duration = args.pause_seconds + 60
            pause_after = args.rate * 15

            cmd = [
                sys.executable, "-u", str(sender),
                "--continuous",
                "--rate", str(args.rate),
                "--duration", str(duration),
                "--pause-after", str(pause_after),
                "--pause-seconds", str(args.pause_seconds),
            ]

            report["sender_command"] = cmd

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            try:
                baseline = initial["metrics"]["feed_packets_received_total"]

                healthy = wait_until(
                    lambda: (
                        prom_query(
                            args.prometheus,
                            'feed_packets_received_total{job="market-data-network"}',
                        ) > baseline
                        and prom_query(
                            args.prometheus,
                            'feed_stale{job="market-data-network"}',
                        ) == 0
                        and alert_states(args.prometheus)
                        .get("MarketDataFeedStale", {})
                        .get("state") == "inactive"
                    ),
                    args.timeout,
                )

                report["healthy"] = snapshot(args.prometheus)
                record(
                    "healthy_feed_established",
                    healthy,
                    report["healthy"],
                )

                stale_detected = wait_until(
                    lambda: (
                        prom_query(
                            args.prometheus,
                            'feed_stale{job="market-data-network"}',
                        ) == 1
                        and alert_states(args.prometheus)
                        .get("MarketDataFeedStale", {})
                        .get("state") == "firing"
                    ),
                    args.timeout,
                )

                report["stale_detected"] = snapshot(args.prometheus)
                record(
                    "stale_feed_alert_firing",
                    stale_detected,
                    report["stale_detected"],
                )

                recovery_baseline = report["stale_detected"][
                    "metrics"
                ]["feed_packets_received_total"]

                recovered = wait_until(
                    lambda: (
                        prom_query(
                            args.prometheus,
                            'feed_packets_received_total{job="market-data-network"}',
                        ) > recovery_baseline
                        and prom_query(
                            args.prometheus,
                            'feed_stale{job="market-data-network"}',
                        ) == 0
                        and alert_states(args.prometheus)
                        .get("MarketDataFeedStale", {})
                        .get("state") == "inactive"
                    ),
                    args.timeout,
                )

                report["recovered"] = snapshot(args.prometheus)
                record(
                    "stale_feed_recovered_and_alert_resolved",
                    recovered,
                    report["recovered"],
                )

            finally:
                if proc.poll() is None:
                    proc.terminate()

                try:
                    stdout, stderr = proc.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    stdout, stderr = proc.communicate()

                report["sender"] = {
                    "returncode": proc.returncode,
                    "stdout": stdout[-12000:],
                    "stderr": stderr[-4000:],
                }

                # Extract timestamped sender events.
                from datetime import datetime

                events = {}

                for line in stdout.splitlines():
                    if line.startswith(("INJECTED_PAUSE", "INJECTED_RESUME")):
                        match = re.search(
                            r"timestamp=([0-9.]+).*session_id=([^\s]+)",
                            line,
                        )

                        if match:
                            name = (
                                "pause"
                                if line.startswith("INJECTED_PAUSE")
                                else "resume"
                            )
                            events[name] = {
                                "timestamp": float(match.group(1)),
                                "session_id": match.group(2),
                            }

                report["injection_events"] = events

                if "pause" in events and "resume" in events:
                    report["session_correlated"] = (
                        events["pause"]["session_id"]
                        == events["resume"]["session_id"]
                    )

                    firing = next(
                        (
                            s for s in report["steps"]
                            if s["name"] == "stale_feed_alert_firing"
                        ),
                        None,
                    )

                    recovered = next(
                        (
                            s for s in report["steps"]
                            if s["name"]
                            == "stale_feed_recovered_and_alert_resolved"
                        ),
                        None,
                    )

                    if firing and recovered:
                        firing_ts = datetime.fromisoformat(
                            firing["at_utc"]
                        ).timestamp()

                        recovered_ts = datetime.fromisoformat(
                            recovered["at_utc"]
                        ).timestamp()

                        report["incident_timing"] = {
                            "observed_detection_latency_seconds": round(
                                firing_ts - events["pause"]["timestamp"], 3
                            ),
                            "observed_recovery_latency_seconds": round(
                                recovered_ts - events["resume"]["timestamp"], 3
                            ),
                            "injected_pause_duration_seconds": round(
                                events["resume"]["timestamp"]
                                - events["pause"]["timestamp"], 3
                            ),
                        }

        if args.mode == "stale-recovery":
            events = report.get("injection_events", {})
            timing = report.get("incident_timing", {})

            record(
                "injection_events_captured",
                "pause" in events and "resume" in events,
                events,
            )

            record(
                "sender_session_correlated",
                report.get("session_correlated") is True,
                events,
            )

            detection = timing.get("observed_detection_latency_seconds")
            recovery = timing.get("observed_recovery_latency_seconds")
            duration = timing.get("injected_pause_duration_seconds")

            record(
                "incident_timing_valid",
                all(
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and 0 <= value <= args.timeout
                    for value in (detection, recovery)
                )
                and isinstance(duration, (int, float))
                and not isinstance(duration, bool)
                and abs(duration - args.pause_seconds) <= 1.0,
                timing,
            )

        report["passed"] = True

    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        print("ERROR:", report["error"], file=sys.stderr)

    finally:
        report["finished_at_utc"] = utcnow()
        output = pathlib.Path(args.output_dir)
        output.mkdir(parents=True, exist_ok=True)

        filename = output / (
            f'{args.mode}-'
            f'{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}-'
            f'{report["run_id"][:8]}.json'
        )

        filename.write_text(json.dumps(report, indent=2) + "\n")
        print(f"EVIDENCE={filename}")
        print(f'RESULT={"PASS" if report["passed"] else "FAIL"}')

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
