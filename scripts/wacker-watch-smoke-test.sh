#!/usr/bin/env bash
set -euo pipefail

# Wacker-Watch agent smoke test.
# Verifies the eBPF collector is present and its host prerequisites are met.
# This does NOT load the eBPF program; it only checks the pieces around it.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENT_DIR="$REPO_ROOT/agents/wacker-watch"

echo "Wacker-Watch agent smoke test"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "FAIL: smoke test must run on Linux (eBPF requires a native Linux kernel)"
  exit 1
fi

echo "- Checking required files"
test -f "$AGENT_DIR/bpf/wacker_watch.bpf.c" \
  || { echo "FAIL: bpf/wacker_watch.bpf.c missing"; exit 2; }
test -f "$AGENT_DIR/cmd/wacker_watch.py" \
  || { echo "FAIL: cmd/wacker_watch.py missing"; exit 2; }

echo "- Checking python3"
command -v python3 >/dev/null || { echo "FAIL: python3 not found"; exit 3; }

echo "- Verifying collector script parses"
python3 -m py_compile "$AGENT_DIR/cmd/wacker_watch.py" \
  || { echo "FAIL: wacker_watch.py does not compile"; exit 3; }

echo "- Verifying python dependencies can be imported"
python3 - <<'PY'
import sys
try:
    import bcc
    import prometheus_client
except Exception as e:
    print("FAIL: missing Python package:", e)
    print("      run 'make agent-deps' to install")
    sys.exit(4)
print("OK: Python dependencies importable")
PY

echo "- Quick BPF source sanity checks"
if ! grep -q "TRACEPOINT_PROBE" "$AGENT_DIR/bpf/wacker_watch.bpf.c"; then
  echo "WARN: wacker_watch.bpf.c does not contain TRACEPOINT_PROBE; verify probe logic"
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "NOTE: not running as root; actual eBPF load will require privileges (sudo or capabilities)"
else
  echo "OK: running as root (you can load eBPF programs)"
fi

echo "- Checking the metrics port is free"
AGENT_METRICS_PORT="${WACKER_METRICS_PORT:-8001}"
if command -v ss >/dev/null && ss -ltn "sport = :$AGENT_METRICS_PORT" 2>/dev/null | grep -q LISTEN; then
  echo "NOTE: port $AGENT_METRICS_PORT is already in use (agent may already be running)"
else
  echo "OK: port $AGENT_METRICS_PORT is available"
fi

echo "Smoke test completed. Run the collector with 'make agent-run' or 'sudo python3 agents/wacker-watch/cmd/wacker_watch.py'"

exit 0
