import random
import time

THRESHOLD = 100

while True:
    lag = random.randint(0, 200)

    print(f"Current Lag: {lag}")

    if lag > THRESHOLD:
        print("ALERT: Consumer lag threshold exceeded")

    time.sleep(5)
