from fastapi import FastAPI, Request
import httpx
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import PlainTextResponse
import time

app = FastAPI(title="Trading API Gateway")

MARKET_DATA_URL = "http://market-data:7001"

origins = [
    "http://localhost:8080",
    "http://127.0.0.1:8080",
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

UPSTREAM_ERRORS = Counter(
    "api_upstream_errors_total",
    "Total number of upstream (market data / strategy) errors",
    ["upstream"],
)


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
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{MARKET_DATA_URL}/tick", params={"symbol": symbol})
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError:
            UPSTREAM_ERRORS.labels(upstream="market-data").inc()
            # You could also raise HTTPException here for proper status codes
            return {"error": "Failed to fetch market data"}

    return await track_request(request, handler, endpoint_name="/price")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    data = generate_latest()
    return PlainTextResponse(data, media_type=CONTENT_TYPE_LATEST)
