#!/usr/bin/env bash
#
# VM Doctor
# Quick health check for CPU, memory, swap, disk, and Docker containers.
#
# Usage:
#   ./vm_doctor.sh
#

set -o errexit
set -o nounset
set -o pipefail

# ---- Colors ----
RED="\e[31m"
YELLOW="\e[33m"
GREEN="\e[32m"
CYAN="\e[36m"
RESET="\e[0m"

ok()    { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
crit()  { echo -e "${RED}[CRIT]${RESET}  $*"; }
info()  { echo -e "${CYAN}[INFO]${RESET}  $*"; }

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

print_header() {
  echo
  echo "============================================================"
  echo "$1"
  echo "============================================================"
}

# ---- 1. Basic system info ----
print_header "VM Doctor - System Info"

HOSTNAME=$(hostname)
KERNEL=$(uname -r)
UPTIME_STR=$(uptime -p 2>/dev/null || uptime)

info "Host      : ${HOSTNAME}"
info "Kernel    : ${KERNEL}"
info "Uptime    : ${UPTIME_STR}"

# ---- 2. CPU Load ----
print_header "CPU Load"

# 1-minute load average
LOAD1=$(awk '{print $1}' /proc/loadavg)
CORES=$(nproc 2>/dev/null || echo 1)
# Compute load per core (rough)
LOAD_PER_CORE=$(awk -v l="$LOAD1" -v c="$CORES" 'BEGIN { printf "%.2f", l/c }')

info "Cores     : ${CORES}"
info "Load (1m) : ${LOAD1}"
info "Load/core : ${LOAD_PER_CORE}"

# Thresholds: <0.7 OK, 0.7–1.0 WARN, >1.0 CRIT
load_status="OK"
if awk "BEGIN {exit !($LOAD_PER_CORE > 1.0)}"; then
  crit "CPU load per core is high (${LOAD_PER_CORE}). System may be CPU-bound."
  load_status="CRIT"
elif awk "BEGIN {exit !($LOAD_PER_CORE > 0.7)}"; then
  warn "CPU load per core is moderately high (${LOAD_PER_CORE})."
  load_status="WARN"
else
  ok "CPU load per core is healthy (${LOAD_PER_CORE})."
fi

# ---- 3. Memory & Swap ----
print_header "Memory & Swap"

if have_cmd free; then
  free -h
fi

MEM_AVAIL_MB=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
MEM_TOTAL_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)

info "Mem total : ${MEM_TOTAL_MB} MiB"
info "Mem avail : ${MEM_AVAIL_MB} MiB"

if [ "$MEM_AVAIL_MB" -lt 512 ]; then
  crit "Available RAM < 512 MiB. High risk of OOM / thrashing."
elif [ "$MEM_AVAIL_MB" -lt 1024 ]; then
  warn "Available RAM < 1 GiB. Keep an eye on heavy workloads."
else
  ok "Available RAM looks healthy (>= 1 GiB)."
fi

# Swap info
if have_cmd swapon; then
  SWAP_SUMMARY=$(swapon --show --noheadings --bytes 2>/dev/null | awk '{total+=$3; used+=$4} END {print total, used}')
  if [ -n "$SWAP_SUMMARY" ]; then
    SWAP_TOTAL_BYTES=$(echo "$SWAP_SUMMARY" | awk '{print $1}')
    SWAP_USED_BYTES=$(echo "$SWAP_SUMMARY" | awk '{print $2}')
    SWAP_TOTAL_MB=$((SWAP_TOTAL_BYTES / 1024 / 1024))
    SWAP_USED_MB=$((SWAP_USED_BYTES / 1024 / 1024))

    info "Swap total: ${SWAP_TOTAL_MB} MiB"
    info "Swap used : ${SWAP_USED_MB} MiB"

    if [ "$SWAP_TOTAL_MB" -eq 0 ]; then
      warn "No swap configured. Bursty workloads may hit OOM faster."
    elif [ "$SWAP_USED_MB" -gt 512 ]; then
      warn "Swap usage > 512 MiB. System may be under memory pressure."
    else
      ok "Swap usage is low."
    fi
  else
    warn "No active swap devices reported."
  fi
else
  warn "swapon command not found; skipping swap details."
fi

# ---- 4. Disk Usage & I/O ----
print_header "Disk Usage"

if have_cmd df; then
  df -h /
else
  warn "df command not found; skipping disk usage."
fi

if have_cmd iostat; then
  info "Disk I/O (iostat -xz 1 1):"
  iostat -xz 1 1
else
  info "iostat not installed. Install sysstat package to see detailed I/O stats."
fi

# ---- 5. Docker Containers ----
print_header "Docker Containers"

if have_cmd docker; then
  if docker info >/dev/null 2>&1; then
    info "Docker is running. Top container resource usage (snapshot):"
    # Show top 5 containers by memory
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | head -n 6
  else
    warn "Docker is installed but not running or not accessible."
  fi
else
  info "Docker not installed; skipping container checks."
fi

# ---- 6. Top processes by memory ----
print_header "Top Processes by Memory"

if have_cmd ps; then
  ps aux --sort=-%mem | head -n 10
else
  warn "ps command not found; skipping process list."
fi

# ---- 7. Summary ----
print_header "Summary"

echo "CPU load status : ${load_status}"
if [ "$MEM_AVAIL_MB" -lt 512 ]; then
  echo "Memory status   : CRIT (low available RAM)"
elif [ "$MEM_AVAIL_MB" -lt 1024 ]; then
  echo "Memory status   : WARN (moderate available RAM)"
else
  echo "Memory status   : OK"
fi

echo
echo "Tips:"
echo "- If CPU load per core is high, consider stopping heavy containers (Kafka, Zookeeper, Grafana, Prometheus) while running Terraform or builds."
echo "- If memory is low, increase VM RAM or reduce parallel containers."
echo "- If disk I/O is saturated (via iostat), move Kafka data to faster storage or reduce Kafka/Zookeeper usage during heavy tasks."
echo
echo "VM Doctor check complete."
