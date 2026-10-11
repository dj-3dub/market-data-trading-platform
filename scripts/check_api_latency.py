"""One-shot business endpoint latency check; errors never count as fast success."""
import argparse
import os
import time
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=f"http://localhost:{os.getenv('API_PORT', '8000')}/strategy")
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()
    started = time.monotonic()
    try:
        with urlopen(args.url, timeout=5) as response:
            response.read()
            if response.status != 200:
                raise ValueError(f"HTTP {response.status}")
        latency = time.monotonic() - started
        print(f"Successful request: {latency:.3f}s (limit {args.threshold}s)")
        return int(latency > args.threshold)
    except (OSError, ValueError) as error:
        print(f"API failed: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
