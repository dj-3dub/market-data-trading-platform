from fastapi import FastAPI, Request
import httpx
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import PlainTextResponse
import time
import os
from fastapi.responses import JSONResponse

app = FastAPI(title="Trading API Gateway")

MARKET_DATA_URL = os.getenv("MARKET_DATA_URL", "http://market-data:7001")
STRATEGY_URL = os.getenv("STRATEGY_URL", "http://strategy-engine:7002")

origins = [
    "http://localhost:8082",
    "http://127.0.0.1:8082",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Prometheus metrics ----
REQUEST_COUNT = Counter(
    "api_requests_total",
    "Total number of API requests",
    ["endpoint", "method", "status"],
)

REQUEST_LATENCY = Histogram(
    "api_request_duration_seconds",
    "Latency of API requests in seconds",
    ["endpoint", "method"],
)

SUCCESS_LATENCY = Histogram(
    "api_success_duration_seconds", "Latency of successful business requests",
    ["endpoint"], buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 3, 5),
)

UPSTREAM_ERRORS = Counter(
    "api_upstream_errors_total",
    "Total number of upstream (market data / strategy) errors",
    ["upstream"],
)

for endpoint in ("/price", "/strategy"):
    for status in ("200", "503"):
        REQUEST_COUNT.labels(endpoint=endpoint, method="GET", status=status)


async def track_request(request: Request, handler, endpoint_name: str):
    """Small helper to time & count a request."""
    method = request.method
    start = time.perf_counter()
    status_code = 500

    try:
        response = await handler()
        status_code = getattr(response, "status_code", 200)
        return response
    finally:
        duration = time.perf_counter() - start
        if 200 <= status_code < 300:
            SUCCESS_LATENCY.labels(endpoint=endpoint_name).observe(duration)
        REQUEST_LATENCY.labels(endpoint=endpoint_name, method=method).observe(duration)
        REQUEST_COUNT.labels(
            endpoint=endpoint_name,
            method=method,
            status=str(status_code),
        ).inc()


@app.get("/price")
async def get_price(request: Request, symbol: str = "FAKE"):
    async def handler():
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"{MARKET_DATA_URL}/tick", params={"symbol": symbol})
                payload = resp.json()
                if resp.status_code >= 500:
                    UPSTREAM_ERRORS.labels(upstream="market-data").inc()
                return JSONResponse(payload, status_code=resp.status_code)
        except (httpx.HTTPError, ValueError):
            UPSTREAM_ERRORS.labels(upstream="market-data").inc()
            return JSONResponse({"error": "Failed to fetch market data"}, status_code=503)

    return await track_request(request, handler, endpoint_name="/price")


@app.get("/strategy")
async def strategy(request: Request, symbol: str = "FAKE"):
    async def handler():
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"{STRATEGY_URL}/state", params={"symbol": symbol})
                payload = resp.json()
                if resp.status_code >= 500:
                    UPSTREAM_ERRORS.labels(upstream="strategy-engine").inc()
                return JSONResponse(payload, status_code=resp.status_code)
        except (httpx.HTTPError, ValueError):
            UPSTREAM_ERRORS.labels(upstream="strategy-engine").inc()
            return JSONResponse({"error": "Strategy unavailable"}, status_code=503)
    return await track_request(request, handler, endpoint_name="/strategy")


@app.get("/ready")
async def ready():
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            for url in (MARKET_DATA_URL, STRATEGY_URL):
                response = await client.get(f"{url}/ready")
                response.raise_for_status()
        return {"status": "ready"}
    except httpx.HTTPError:
        return JSONResponse({"status": "degraded"}, status_code=503)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    data = generate_latest()
    return PlainTextResponse(data, media_type=CONTENT_TYPE_LATEST)


@app.get("/integrity")
async def integrity():
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(f"{STRATEGY_URL}/integrity")
            return JSONResponse(response.json(), status_code=response.status_code)
    except (httpx.HTTPError, ValueError):
        return JSONResponse({"error": "Integrity state unavailable"}, status_code=503)


@app.get("/quarantine")
async def quarantine(limit: int = 20):
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(f"{STRATEGY_URL}/quarantine", params={"limit": max(1, min(100, limit))})
            return JSONResponse(response.json(), status_code=response.status_code)
    except (httpx.HTTPError, ValueError):
        return JSONResponse({"error": "Quarantine unavailable"}, status_code=503)
