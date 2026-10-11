"""Independent, fixed-cadence business-path probe; failures remain observable."""
import json
import math
import os
import time
import urllib.request

from prometheus_client import Gauge, start_http_server

success = Gauge("reliability_probe_success", "Latest scheduled business probe succeeded")
last_run = Gauge("reliability_probe_timestamp_seconds", "Last completed probe")


def check(url):
    with urllib.request.urlopen(url, timeout=4) as response:
        state = json.load(response)
    timestamp = state["timestamp"]
    return (state["lastSymbol"] == "FAKE" and state["processedTicks"] > 0
            and state.get("allSymbolsFresh", True) is True
            and math.isfinite(timestamp) and -2 <= time.time() - timestamp < 10)


def main():
    start_http_server(8010)
    url = os.getenv("PROBE_URL", "http://api-gateway:8000/strategy")
    while True:
        started = time.monotonic()
        try:
            success.set(int(check(url)))
        except Exception:
            success.set(0)
        last_run.set(time.time())
        time.sleep(max(0, 5 - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
