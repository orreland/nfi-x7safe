#!/usr/bin/env bash
# Section-16 segment consistency check: 10 consecutive ~61-day segments x
# {baseline, N25, N0}, survB universe, one backtest at a time, FT_LOWMEM on,
# memory gate (short windows need far less than an 18-month run).
cd /d/NostalgiaForInfinity || exit 1
export FT_LOWMEM=1
MIN_FREE_GB=10

free_gb() {
  powershell.exe -NoProfile -Command \
    "[math]::Floor((Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory/1MB)" | tr -d '\r'
}

wait_for_memory() {
  local waited=0
  while :; do
    local f; f=$(free_gb)
    [ "${f:-0}" -ge "$MIN_FREE_GB" ] && return 0
    [ $((waited % 300)) -eq 0 ] && echo "--- waiting for memory: ${f} GB free < ${MIN_FREE_GB} GB ($(date +%T))"
    sleep 30; waited=$((waited + 30))
  done
}

SEGS=(20250216-20250418 20250418-20250618 20250618-20250817 20250817-20251017 20251017-20251217
      20251217-20260216 20260216-20260418 20260418-20260617 20260617-20260817 20260817-20261017)
i=0
for TR in "${SEGS[@]}"; do
  i=$((i + 1)); TAG=$(printf "seg%02d" "$i")
  for S in X7SafeStopHonored X7SafeOtherStop25 X7SafeOtherNoStop; do
    dir="user_data/backtest_results/stopgrid-$TAG-$S"
    for attempt in 1 2 3; do
      wait_for_memory
      TIMERANGE="$TR" UNIVERSE=survB TAG="$TAG" bash scripts/run_stop_grid.sh "$S" | grep -a "==="
      ls "$dir"/backtest-result-*.zip > /dev/null 2>&1 && break
      echo "--- no result for $S [$TAG] (attempt $attempt)"
    done
  done
done
echo "=== QUEUE FINISHED"
