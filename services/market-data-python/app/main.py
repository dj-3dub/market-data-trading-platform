from contextlib import asynccontextmanager
from random import random
from threading import Event, Lock, Thread
import logging
import json
import os
import re
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from kafka import KafkaProducer
from prometheus_client import Counter, Histogram, CONTENT_TYPE_LATEST, generate_latest

# Works both in the image package and the import-based host contract tests.
try:
    from .journal import Journal
except ImportError:
    from journal import Journal

log = logging.getLogger("uvicorn.error")
published = Counter("market_data_messages_published_total", "Ticks acknowledged by Kafka")
errors = Counter("market_data_publish_errors_total", "Failed publication attempts")
latency = Histogram("price_tick_latency_seconds", "Tick preparation and publication latency")
interval = float(os.getenv("TICK_INTERVAL_SECONDS", "1"))
symbols = tuple(os.getenv("MARKET_SYMBOLS", "FAKE,FAKE2,FAKE3").split(","))
if interval <= 0 or interval * len(symbols) >= 10 or not symbols or len(set(symbols)) != len(symbols) or any(
    not re.fullmatch(r"FAKE[0-9]*", symbol) for symbol in symbols
):
    raise ValueError("Use distinct FAKE symbols and a positive interval with one full round under 10 seconds")
lock = Lock()
latest = {}
last_published = {}
stop = Event()
worker_failure = None


def open_journal():
    return Journal(os.path.join(os.getenv("PRODUCER_STATE_DIR", "/data"), "producer.sqlite"), symbols)


def close_producer(producer, timeout):
    try:
        producer.close(timeout=timeout)
    except Exception:
        log.exception("Kafka producer cleanup failed")


def publish_loop():
    global worker_failure
    producer = None
    journal = None
    index = 0
    try:
        journal = open_journal()
        while not stop.is_set():
            started = time.monotonic()
            # Persist before publication; storage errors stop the worker rather
            # than advancing sequence numbers or generating a replacement event.
            tick = journal.prepare(symbols[index % len(symbols)], time.time(), (random() - 0.5) * 0.5)
            try:
                if producer is None:
                    producer = KafkaProducer(
                        bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
                        security_protocol=os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT"),
                        value_serializer=lambda value: json.dumps(value, allow_nan=False).encode(),
                        key_serializer=lambda value: value.encode(),
                        acks="all", max_block_ms=3000, request_timeout_ms=3000,
                        max_in_flight_requests_per_connection=1,
                    )
                producer.send(os.getenv("KAFKA_TICKS_TOPIC", "ticks-v1"),
                              key=tick["symbol"], value=tick).get(timeout=5)
            except Exception:
                errors.inc()
                log.exception("Kafka publication failed; exact pending tick will be retried")
                if producer is not None:
                    close_producer(producer, timeout=0)
                    producer = None
            else:
                journal.acknowledge(tick)
                with lock:
                    latest[tick["symbol"]] = tick
                    last_published[tick["symbol"]] = time.monotonic()
                index = (symbols.index(tick["symbol"]) + 1) % len(symbols)
                published.inc()
                latency.observe(time.monotonic() - started)
            stop.wait(interval)
    except Exception as error:
        worker_failure = str(error)
        log.exception("Producer worker stopped; durable state requires attention")
    finally:
        if producer is not None:
            close_producer(producer, timeout=2)
        if journal is not None:
            journal.close()


@asynccontextmanager
async def lifespan(app):
    global worker_failure
    worker_failure = None
    stop.clear()
    worker = Thread(target=publish_loop, daemon=True)
    worker.start()
    yield
    stop.set()
    worker.join(timeout=12)


app = FastAPI(title="Market Data Service", lifespan=lifespan)


@app.get("/tick")
def get_price_tick(symbol: str = "FAKE"):
    if symbol not in symbols:
        return JSONResponse({"error": "Unsupported simulated symbol"}, status_code=404)
    with lock:
        tick = latest.get(symbol)
        if worker_failure or tick is None or not -2 <= time.time() - tick["timestamp"] < 10:
            return JSONResponse({"error": "No fresh Kafka-acknowledged tick available"}, status_code=503)
        return dict(tick)


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})


@app.get("/health")
def health():
    if worker_failure:
        return JSONResponse({"status": "worker-failed"}, status_code=503)
    return {"status": "ok"}


@app.get("/ready")
def ready():
    for symbol in symbols:
        result = get_price_tick(symbol)
        if isinstance(result, JSONResponse):
            return result
    return {"status": "ready"}
