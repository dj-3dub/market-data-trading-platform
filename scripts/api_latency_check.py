import time
import requests

URL = "http://localhost:8000"

while True:
    start = time.time()
    try:
        requests.get(URL, timeout=2)
        latency = time.time() - start

        print(f"Latency: {latency:.3f}s")

        if latency > 0.5:
            print("ALERT: High latency detected")

    except Exception:
        print("ALERT: API unreachable")

    time.sleep(5)
