"""Read actual Kafka consumer lag from Prometheus; nonzero on missing/excess lag."""
import argparse
import json
import math
import os
from urllib.parse import urlencode
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=float, default=10)
    args = parser.parse_args()
    url = f"http://localhost:{os.getenv('PROMETHEUS_PORT', '9090')}/api/v1/query?"
    expression = 'sum(kafka_consumergroup_lag{consumergroup="strategy-engine-v1"})'
    try:
        with urlopen(url + urlencode({"query": expression}), timeout=5) as response:
            rows = json.load(response)["data"]["result"]
        lag = float(rows[0]["value"][1])
        if not math.isfinite(lag) or lag < 0:
            raise ValueError("invalid lag")
        print(json.dumps({"lag": lag, "threshold": args.threshold}))
        return int(lag > args.threshold)
    except (OSError, ValueError, KeyError, IndexError) as error:
        print(f"Lag unavailable: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
