"""Bounded live acceptance checks using only the Python standard library."""
import json
import math
import os
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import urlopen

API = f"http://localhost:{os.getenv('API_PORT', '8000')}"
PROM = f"http://localhost:{os.getenv('PROMETHEUS_PORT', '9090')}"
_deadline = None


def get(url):
    remaining = 8 if _deadline is None else min(8, _deadline - time.monotonic())
    if remaining <= 0:
        raise TimeoutError("Check deadline reached")
    with urlopen(url, timeout=remaining) as response:
        return json.load(response)


def eventually(check, timeout=90):
    global _deadline
    deadline = time.monotonic() + timeout
    error = None
    previous_deadline = _deadline
    _deadline = deadline
    try:
        while time.monotonic() < deadline:
            try:
                return check()
            except (AssertionError, OSError, ValueError, KeyError) as exc:
                error = exc
                time.sleep(min(2, max(0, deadline - time.monotonic())))
    finally:
        _deadline = previous_deadline
    raise RuntimeError(f"Acceptance check timed out: {error}")


def query(expression):
    data = get(PROM + "/api/v1/query?" + urlencode({"query": expression}))
    assert data["status"] == "success", expression
    return data["data"]["result"]


def main():
    started = time.time()

    def fresh_state():
        state = get(API + "/strategy")
        assert state["timestamp"] >= started, "Strategy has not consumed a new tick"
        assert state["status"] == "ok" and state["ageSeconds"] < 10, state
        assert state["processedTicks"] > 0, state
        return state

    baseline = eventually(fresh_state)

    def advancing():
        state = fresh_state()
        assert state["timestamp"] > baseline["timestamp"], "Strategy timestamp is frozen"
        assert state["processedTicks"] > baseline["processedTicks"], "Consumer is not advancing"
        get(API + "/ready")
        tick = get(API + "/price")
        assert tick["timestamp"] >= started and tick["symbol"] == state["lastSymbol"], tick
    eventually(advancing)
    print("PASS: Kafka-acknowledged ticks continuously reach the strategy and API")

    dashboards = Path(__file__).resolve().parents[1] / "monitoring/grafana/dashboards"
    expressions = []
    for path in sorted(dashboards.glob("trading-*.json")):
        dashboard = json.loads(path.read_text())
        for panel in dashboard["panels"]:
            for target in panel.get("targets", []):
                if target.get("expr"):
                    expressions.append(target["expr"])

    def metrics_present():
        get(API + "/price")
        get(API + "/strategy")
        for job in ("market-data", "strategy-engine", "api-gateway", "kafka"):
            values = query(f'up{{job="{job}"}}')
            assert values and all(float(x["value"][1]) == 1 for x in values), job
        for expr in expressions:
            values = query(expr)
            assert values and all(math.isfinite(float(x["value"][1])) for x in values), expr
    eventually(metrics_present)
    print(f"PASS: {len(expressions)} application dashboard queries return finite data")

    def supporting_services():
        get(f"http://localhost:{os.getenv('GRAFANA_PORT', '3000')}/api/health")
        for port in (os.getenv("KAFKA_UI_PORT", "8081"), os.getenv("WEB_PORT", "8082")):
            with urlopen(f"http://localhost:{port}/", timeout=min(8, max(0.01, _deadline - time.monotonic()))) as response:
                assert response.status == 200
    eventually(supporting_services)
    print("PASS: frontend, Grafana and Kafka UI are ready")


if __name__ == "__main__":
    main()
