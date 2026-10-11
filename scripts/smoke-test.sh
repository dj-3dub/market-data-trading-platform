#!/usr/bin/env bash
#
# End-to-end smoke test for the market data trading platform.
#
# Unlike health-check.sh (is everything up?) this verifies the data path
# actually works: market data produces ticks, the API serves them, the
# metrics land in Prometheus, and Grafana can query them.
#
# Exits non-zero when any link fails so CI catches regressions.
#
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 2

API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-8082}"
GRAFANA_PORT="${GRAFANA_PORT:-3000}"
PROMETHEUS_PORT="${PROMETHEUS_PORT:-9090}"
GRAFANA_USER="${GRAFANA_USER:-admin}"
GRAFANA_PASS="$(python3 scripts/local_config.py --grafana-password)" || exit 2

green()  { printf '\033[0;32m%s\033[0m' "$1"; }
red()    { printf '\033[0;31m%s\033[0m' "$1"; }

FAILED=0
ok()   { printf '  %s  %s\n' "$(green 'PASS')" "$1"; }
bad()  { printf '  %s  %s\n' "$(red 'FAIL')" "$1"; FAILED=$((FAILED + 1)); }
info() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# prom <query> -> prints result count
prom_count() {
  curl -s --max-time 8 --get --data-urlencode "query=$1" \
    "http://localhost:${PROMETHEUS_PORT}/api/v1/query" 2>/dev/null \
  | python3 -c '
import json, sys
try:
    print(len(json.load(sys.stdin)["data"]["result"]))
except Exception:
    print(0)
'
}

printf '\033[1m=== market data trading platform :: smoke test ===\033[0m\n'

# ------------------------------------------------------------- 1. broker up
info "1. Kafka accepts connections"
if docker compose exec -T kafka \
   kafka-broker-api-versions --bootstrap-server localhost:9092 >/dev/null 2>&1; then
  ok "broker responds to kafka-broker-api-versions"
else
  bad "broker unreachable from inside the kafka container"
fi

# ------------------------------------------------------ 2. market data path
info "2. market-data-python serves prices"
price_body="$(curl -s --max-time 8 "http://localhost:${API_PORT}/price" 2>/dev/null || true)"
if printf '%s' "$price_body" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    assert isinstance(d.get("price"), (int, float))
    assert d.get("symbol")
except Exception:
    sys.exit(1)
' 2>/dev/null; then
  ok "GET /price -> ${price_body}"
else
  bad "GET /price did not return a usable price payload: ${price_body:0:120}"
fi

# ---------------------------------------------------------- 3. api gateway
info "3. api-gateway health and metrics"
if [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 \
      "http://localhost:${API_PORT}/health")" = "200" ]; then
  ok "GET /health -> 200"
else
  bad "GET /health did not return 200"
fi

api_metrics="$(curl -s --max-time 8 "http://localhost:${API_PORT}/metrics" 2>/dev/null || true)"
if printf '%s' "$api_metrics" | grep -qE '^api_(requests_total|request_duration_seconds)'; then
  n="$(printf '%s' "$api_metrics" | grep -cE '^api_(requests_total|request_duration_seconds)')"
  ok "api-gateway exposes ${n} custom metric series"
else
  bad "api-gateway /metrics has no api_* custom metrics"
fi

# -------------------------------------------------------- 4. frontend works
info "4. web-frontend is served and references the API"
page="$(curl -s --max-time 8 "http://localhost:${WEB_PORT}/" 2>/dev/null || true)"
if [ -n "$page" ] && printf '%s' "$page" | grep -qi '</html>'; then
  ok "GET / returns an HTML document"
else
  bad "GET / did not return HTML"
fi
if curl -fsS --max-time 8 "http://localhost:${WEB_PORT}/api/price" >/dev/null; then
  ok "frontend same-origin API proxy serves prices"
else
  bad "frontend API proxy failed"
fi

# ------------------------------------------------- 5. prometheus has ingested
info "5. Prometheus has scraped the platform"
for pair in \
  "api-gateway|api_request_duration_seconds_count" \
  "market-data|market_data_.*" \
  "strategy-engine|strategy_tick_latency.*" \
  "kafka|kafka_brokers" ; do
  job="${pair%%|*}"; metric="${pair#*|}"
  n="$(prom_count "{job=\"${job}\",__name__=~\"${metric}\"}")"
  if [ "${n:-0}" -gt 0 ]; then
    ok "Prometheus holds ${n} series matching ${metric}"
  else
    bad "Prometheus has no series matching ${metric} (job ${job} never scraped?)"
  fi
done

# ---------------------------------------------------------- 6. grafana usable
info "6. Grafana can query Prometheus through the provisioned datasource"
ds_uid="$(curl -s --max-time 8 -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
  "http://localhost:${GRAFANA_PORT}/api/datasources" 2>/dev/null \
  | python3 -c '
import json, sys
try:
    print(next(x["uid"] for x in json.load(sys.stdin) if x["type"] == "prometheus"))
except Exception:
    print("")
')"
if [ -z "$ds_uid" ]; then
  bad "no Prometheus datasource provisioned in Grafana"
elif [ "$ds_uid" != "prometheus" ]; then
  bad "datasource uid is '${ds_uid}', expected the pinned 'prometheus' uid"
else
  ok "datasource uid is the pinned 'prometheus'"
  q="$(curl -s --max-time 10 -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
        --get --data-urlencode 'query=api_request_duration_seconds_count' \
        "http://localhost:${GRAFANA_PORT}/api/datasources/proxy/uid/${ds_uid}/api/v1/query" 2>/dev/null || true)"
  if printf '%s' "$q" | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("status") == "success" and d["data"]["result"] else 1)'; then
    ok "Grafana proxy query to Prometheus succeeded"
  else
    bad "Grafana could not query Prometheus: ${q:0:160}"
  fi
fi

# Verify newly generated ticks actually cross Kafka and reach the strategy API.
info "7. Live end-to-end pipeline"
if python3 scripts/verify-pipeline.py; then
  ok "fresh ticks reach strategy; all dashboard queries return data"
else
  bad "pipeline or dashboard validation failed"
fi

# ------------------------------------------------------------------ verdict
printf '\n'
if [ "$FAILED" -gt 0 ]; then
  printf '%s\n\n' "$(red "Smoke test FAILED: ${FAILED} check(s) did not pass")"
  exit 1
fi
printf '%s\n\n' "$(green 'Smoke test passed - full data path verified')"
exit 0
