#!/usr/bin/env bash
#
# Service health check for the market data trading platform.
#
# Validates every running component: container state, HTTP endpoints,
# Prometheus scrape targets and Grafana dashboard provisioning.
#
# Exits non-zero when any check fails, so it is usable in CI. Components
# that are genuinely optional (the eBPF agent) are reported as SKIP rather
# than FAIL, so `make doctor` does not nag about a profile you did not start.
#
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 2

# Keep in sync with the defaults in docker-compose.yml
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-8082}"
GRAFANA_PORT="${GRAFANA_PORT:-3000}"
PROMETHEUS_PORT="${PROMETHEUS_PORT:-9090}"
KAFKA_UI_PORT="${KAFKA_UI_PORT:-8081}"
KAFKA_EXPORTER_PORT="${KAFKA_EXPORTER_PORT:-9308}"
AGENT_PORT="${AGENT_PORT:-8001}"
GRAFANA_USER="${GRAFANA_USER:-admin}"
GRAFANA_PASS="$(python3 scripts/local_config.py --grafana-password)" || exit 2

PASS=0
FAIL=0
SKIP=0

green() { printf '\033[0;32m%s\033[0m' "$1"; }
red()   { printf '\033[0;31m%s\033[0m' "$1"; }
yellow() { printf '\033[0;33m%s\033[0m' "$1"; }

section() { printf '\n\033[1m%s\033[0m\n' "$1"; }

record() { # record <status> <name> <detail>
  case "$1" in
    PASS) PASS=$((PASS + 1)); printf '  %s  %-28s %s\n' "$(green PASS)" "$2" "$3" ;;
    FAIL) FAIL=$((FAIL + 1)); printf '  %s  %-28s %s\n' "$(red FAIL)" "$2" "$3" ;;
    SKIP) SKIP=$((SKIP + 1)); printf '  %s  %-28s %s\n' "$(yellow SKIP)" "$2" "$3" ;;
  esac
}

http_code() { # http_code <url> [curl args...]
  local url="$1"; shift
  curl -s -o /dev/null -w '%{http_code}' --max-time 8 "$@" "$url" 2>/dev/null
}

# ---------------------------------------------------------------- containers
section "Containers"
if ! docker compose ps >/dev/null 2>&1; then
  record FAIL "docker compose" "cannot talk to Docker - is the daemon running?"
else
  for svc in zookeeper kafka market-data strategy-engine api-gateway \
             web-frontend prometheus grafana kafka-exporter kafka-ui; do
    # -a so a stopped container is reported as stopped, not as missing
    cid="$(docker compose ps -aq "$svc" 2>/dev/null || true)"
    if [ -z "$cid" ]; then
      record FAIL "$svc" "container not created (run: make up)"
      continue
    fi
    state="$(docker inspect -f '{{.State.Status}}' "$cid" 2>/dev/null || echo unknown)"
    if [ "$state" = "running" ]; then
      record PASS "$svc" "running"
    elif [ "$state" = "exited" ]; then
      record FAIL "$svc" "stopped/exited - logs: docker compose logs $svc"
    else
      record FAIL "$svc" "state=$state"
    fi
  done

  # eBPF agent lives behind an opt-in profile
  agent_cid="$(docker compose --profile ebpf ps -aq wacker-watch 2>/dev/null || true)"
  if [ -n "$agent_cid" ]; then
    state="$(docker inspect -f '{{.State.Status}}' "$agent_cid" 2>/dev/null || echo unknown)"
    if [ "$state" = "running" ]; then
      record PASS "wacker-watch" "running"
    else
      record FAIL "wacker-watch" "state=$state (eBPF needs privileged + host kernel access)"
    fi
  else
    record SKIP "wacker-watch" "not started (optional profile: make agent-up)"
  fi
fi

# ----------------------------------------------------------------- endpoints
section "HTTP endpoints"
for entry in \
  "web-frontend|http://localhost:${WEB_PORT}|static site" \
  "api-gateway|http://localhost:${API_PORT}/health|health endpoint" \
  "pipeline readiness|http://localhost:${API_PORT}/ready|fresh upstream data" \
  "api-gateway/metrics|http://localhost:${API_PORT}/metrics|prometheus exposition" \
  "kafka-ui|http://localhost:${KAFKA_UI_PORT}|broker UI" \
  "kafka-exporter|http://localhost:${KAFKA_EXPORTER_PORT}/metrics|broker metrics" \
  "prometheus|http://localhost:${PROMETHEUS_PORT}/-/ready|scrape readiness" \
  "grafana|http://localhost:${GRAFANA_PORT}/api/health|grafana health" ; do
  name="${entry%%|*}"; rest="${entry#*|}"
  url="${rest%%|*}"; desc="${rest#*|}"
  code="$(http_code "$url")"
  case "$code" in
    200|302) record PASS "$name" "$desc (HTTP $code)" ;;
    000)     record FAIL "$name" "$desc - unreachable at $url" ;;
    *)       record FAIL "$name" "$desc - HTTP $code from $url" ;;
  esac
done

# the agent publishes on the host even when it runs in a container
if [ "$(http_code "http://localhost:${AGENT_PORT}/metrics")" = "200" ]; then
  record PASS "wacker-watch metrics" "HTTP 200 on :${AGENT_PORT}"
else
  record SKIP "wacker-watch metrics" "not listening on :${AGENT_PORT}"
fi

# ---------------------------------------------------- prometheus scrape jobs
section "Prometheus targets"
targets_json="$(curl -s --max-time 8 "http://localhost:${PROMETHEUS_PORT}/api/v1/targets" 2>/dev/null || true)"
if [ -z "$targets_json" ]; then
  record FAIL "targets API" "no response from :${PROMETHEUS_PORT}"
else
  while IFS=$'\t' read -r job url health err; do
    [ -z "$job" ] && continue
    if [ "$health" = "up" ]; then
      record PASS "$job" "$url"
    elif [ "$url" = "http://host.docker.internal:8001/metrics" ] \
         || [ "$url" = "http://wacker-watch:8001/metrics" ]; then
      # one of the two agent paths is up whenever the other is
      record SKIP "$job" "$url is down (optional agent path)"
    else
      record FAIL "$job" "$url is ${health}: ${err:-no error reported}"
    fi
  done < <(printf '%s' "$targets_json" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)["data"]["activeTargets"]
except Exception:
    print("targets API\tPrometheus\tinvalid\tMalformed targets response")
    sys.exit(0)
required = {"prometheus", "market-data", "strategy-engine", "api-gateway", "kafka", "reliability-probe"}
found = {t["labels"].get("job") for t in data}
for job in sorted(required - found):
    print(f"{job}\tPrometheus\tmissing\tRequired scrape job absent")
for t in sorted(data, key=lambda x: (x["labels"].get("job", ""), x["scrapeUrl"])):
    print("\t".join([
        t["labels"].get("job", "?"),
        t["scrapeUrl"],
        t["health"],
        (t.get("lastError") or "").replace("\t", " ")[:120],
    ]))
' 2>/dev/null)
fi

# ------------------------------------------------------- grafana dashboards
section "Grafana dashboards"
dash_json="$(curl -s --max-time 8 -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
  "http://localhost:${GRAFANA_PORT}/api/search?type=dash-db" 2>/dev/null || true)"
if [ -z "$dash_json" ]; then
  record FAIL "dashboard search" "no response - check credentials or :${GRAFANA_PORT}"
else
  expected="trading-overview trading-platform-latency wacker-watch reliability"
  found="$(printf '%s' "$dash_json" | python3 -c '
import json, sys
try:
    print(" ".join(x["uid"] for x in json.load(sys.stdin)))
except Exception:
    pass
' 2>/dev/null)"
  if [ -z "$found" ]; then
    record FAIL "dashboards" "Grafana returned no dashboards"
  else
    for uid in $expected; do
      case " $found " in
        *" $uid "*) record PASS "dashboard:$uid" "provisioned" ;;
        *)           record FAIL "dashboard:$uid" "missing (check provisioning dir mount)" ;;
      esac
    done
  fi
fi

# --------------------------------------------------------------------- tally
printf '\n\033[1mSummary\033[0m: %s passed, %s failed, %s skipped\n' \
  "$(green "$PASS")" \
  "$([ "$FAIL" -gt 0 ] && red "$FAIL" || echo 0)" \
  "$([ "$SKIP" -gt 0 ] && yellow "$SKIP" || echo 0)"

if [ "$FAIL" -gt 0 ]; then
  printf '\n%s\n' "$(red 'Health check FAILED')"
  exit 1
fi
printf '\n%s\n' "$(green 'All required components healthy')"
exit 0
