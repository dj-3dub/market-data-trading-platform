from fastapi import FastAPI
from prometheus_client import Counter, Histogram, generate_latest
from random import random
from time import time
from fastapi.responses import PlainTextResponse
from kafka import KafkaProducer
import json
import os

app = FastAPI(title="Market Data Service")

price_tick_counter = Counter("price_ticks_total", "Total number of price ticks generated")
price_latency_hist = Histogram("price_tick_latency_seconds", "Latency for generating price ticks")

LAST_PRICE = 100.0

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TICKS_TOPIC = os.getenv("KAFKA_TICKS_TOPIC", "ticks")

producer = None

def get_producer():
    global producer
    if producer is None:
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            print(f"[KAFKA] Connected to {KAFKA_BOOTSTRAP_SERVERS}, topic={KAFKA_TICKS_TOPIC}")
        except Exception as e:
            print(f"[KAFKA] Failed to create producer: {e}")
            producer = None
    return producer


@app.on_event("startup")
def startup_event():
    # Try to initialize producer early
    get_producer()


@app.get("/tick")
def get_price_tick(symbol: str = "FAKE"):
    global LAST_PRICE
    start = time()

    # simple random walk
    change = (random() - 0.5) * 0.5
    LAST_PRICE = max(1.0, LAST_PRICE + change)

    price_tick_counter.inc()
    price_latency_hist.observe(time() - start)

    payload = {
        "symbol": symbol,
        "price": round(LAST_PRICE, 4),
        "source": "market-data-python",
    }

    # Fire-and-forget send to Kafka
    p = get_producer()
    if p is not None:
        try:
            p.send(KAFKA_TICKS_TOPIC, payload)
        except Exception as e:
            print(f"[KAFKA] Failed to send tick: {e}")

    return payload


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    return generate_latest()


@app.get("/health")
def health():
    return {"status": "ok"}
