import time
import requests

SERVICE_URL = "http://localhost:8000/health"

while True:
    try:
        r = requests.get(SERVICE_URL, timeout=2)
        if r.status_code != 200:
            print("ALERT: Service unhealthy")
        else:
            print("OK")
    except Exception:
        print("ALERT: Service unreachable")

    time.sleep(5)
