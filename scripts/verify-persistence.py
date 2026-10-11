"""Verify Kafka records/offsets, Grafana state and Prometheus history survive recreation.

Run only in the local lab. This briefly stops the producer/strategy and recreates
the stateful containers; volumes are retained and applications are restored.
"""
import json
from pathlib import Path
import signal
import subprocess
import time
import urllib.parse
import urllib.request
import base64
import os

from evidence import compose_workload, new_report, save_report
from local_config import grafana_password

ROOT = Path(__file__).resolve().parents[1]
GRAFANA = f"http://localhost:{os.getenv('GRAFANA_PORT', '3000')}"
PROM = f"http://localhost:{os.getenv('PROMETHEUS_PORT', '9090')}"
API = f"http://localhost:{os.getenv('API_PORT', '8000')}"


def compose(*args, input=None):
    result = subprocess.run(["docker", "compose", *args], cwd=ROOT, input=input,
                            capture_output=True, text=True, check=True, timeout=90)
    return result.stdout.strip()


def kafka(tool, *args, input=None):
    return compose("exec", "-T", "kafka", tool, "--bootstrap-server", "kafka:9092",
                   *args, input=input)


def http(url, data=None, grafana=False, method=None):
    headers = {}
    if grafana:
        credentials = f"{os.getenv('GRAFANA_USER', 'admin')}:{grafana_password(ROOT)}"
        headers["Authorization"] = "Basic " + base64.b64encode(credentials.encode()).decode()
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                     headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.load(response)


def eventually(check, timeout=120):
    deadline = time.monotonic() + timeout
    last = "condition not met"
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            last = str(error)
        time.sleep(2)
    raise TimeoutError(last)


def offsets():
    description = kafka("kafka-consumer-groups", "--group", "strategy-engine-v1", "--describe")
    result = {}
    for line in description.splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[0] == "strategy-engine-v1" and fields[2].isdigit() and fields[3].isdigit():
            result[f"{fields[1]}:{fields[2]}"] = int(fields[3])
    if not result:
        raise ValueError("No committed strategy offsets found")
    return result


def historical_sample(timestamp):
    query = urllib.parse.urlencode({"query": 'up{job="api-gateway"}', "time": timestamp})
    return http(PROM + "/api/v1/query?" + query)["data"]["result"]


def interrupted(signum, frame):
    raise KeyboardInterrupt(f"signal {signum}")


def main():
    report = new_report(ROOT, "container-recreation", {
        "recreated_services": ["zookeeper", "kafka", "grafana", "prometheus"],
        "paused_workload_services": ["market-data", "strategy-engine"],
        "volumes_removed": False, "poll_interval_seconds": 2,
    })
    report["workload"] = compose_workload(ROOT)
    topic = "persistence-check-" + report["run_id"][:12]
    uid = "persistence-" + report["run_id"][:12]
    marker = report["run_id"]
    stopped = False
    topic_created = False
    dashboard_created = False
    try:
        eventually(lambda: http(API + "/ready").get("status") == "ready")
        eventually(lambda: http(GRAFANA + "/api/health").get("database") == "ok")
        eventually(lambda: historical_sample(time.time()))
        timestamp = time.time()
        sample_before = historical_sample(timestamp)
        topic_created = True
        kafka("kafka-topics", "--create", "--topic", topic, "--partitions", "1", "--replication-factor", "1")
        kafka("kafka-console-producer", "--topic", topic, input=marker + "\n")
        dashboard_created = True
        http(GRAFANA + "/api/dashboards/db", {"dashboard": {
            "uid": uid, "title": "Temporary persistence verification", "schemaVersion": 39,
            "panels": []}, "overwrite": False}, grafana=True)

        stopped = True
        compose("stop", "market-data", "strategy-engine")
        offsets_before = eventually(offsets)
        report["offsets_before"] = offsets_before
        compose("up", "-d", "--force-recreate", "zookeeper", "kafka", "grafana", "prometheus")
        eventually(lambda: kafka("kafka-broker-api-versions"))
        record = eventually(lambda: kafka("kafka-console-consumer", "--topic", topic,
                                         "--from-beginning", "--max-messages", "1", "--timeout-ms", "10000"))
        if record != marker:
            raise RuntimeError("Kafka marker did not survive recreation")
        offsets_after = eventually(offsets)
        report["offsets_after"] = offsets_after
        if offsets_before != offsets_after:
            raise RuntimeError("Committed consumer offsets changed while the consumer was stopped")
        dashboard = eventually(lambda: http(GRAFANA + f"/api/dashboards/uid/{uid}", grafana=True))
        if dashboard["dashboard"]["uid"] != uid:
            raise RuntimeError("Grafana saved dashboard did not survive recreation")
        sample_after = eventually(lambda: historical_sample(timestamp))
        if sample_before != sample_after:
            raise RuntimeError("Prometheus historical sample did not survive recreation")
        report["checks"] = {"kafka_record": True, "consumer_offsets": True,
                            "grafana_saved_dashboard": True, "prometheus_history": True}
        compose("start", "market-data", "strategy-engine")
        stopped = False
        previous = eventually(lambda: http(API + "/strategy"))["timestamp"]
        eventually(lambda: http(API + "/strategy")["timestamp"] > previous)
        report["passed"] = True
    except BaseException as error:
        report["error"] = str(error)
        raise
    finally:
        cleanup_errors = []
        for needed, action in (
            (stopped, lambda: compose("start", "market-data", "strategy-engine")),
            (topic_created, lambda: kafka("kafka-topics", "--delete", "--topic", topic)),
            (dashboard_created, lambda: http(GRAFANA + f"/api/dashboards/uid/{uid}", grafana=True, method="DELETE")),
        ):
            if needed:
                try:
                    action()
                except Exception as error:
                    cleanup_errors.append(str(error))
        if cleanup_errors:
            report["cleanup_errors"] = cleanup_errors
            report["passed"] = False
        save_report(ROOT, report, "persistence")
        print(json.dumps(report))
        if cleanup_errors:
            raise RuntimeError("Persistence experiment cleanup needs attention; see report")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    main()
