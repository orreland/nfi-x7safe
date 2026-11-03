#!/usr/bin/env bash
# Section-26 rebuy stop grid queue (from queue_rebuy.sh) with a memory gate: one backtest at a time,
# FT_LOWMEM on, and each run waits until the machine has >= MIN_FREE_GB of
# free commit (an 18-month run peaks at ~35 GB against a ~39.6 GB limit; runs
# that succeeded earlier all started with ~20 GB free). Up to 2 retries when a
# run leaves no result zip.
cd /d/NostalgiaForInfinity || exit 1
export FT_LOWMEM=1
export TEMP="D:\NostalgiaForInfinity\scratch\tmp" TMP="D:\NostalgiaForInfinity\scratch\tmp"
MIN_FREE_GB=19

free_gb() {
  powershell.exe -NoProfile -Command \
    "[math]::Floor((Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory/1MB)" | tr -d '\r'
}

wait_for_memory() {
  local waited=0
  while :; do
    local f; f=$(free_gb)
    if [ "${f:-0}" -ge "$MIN_FREE_GB" ]; then
      echo "--- memory ok: ${f} GB free commit ($(date +%T))"
      return 0
    fi
    [ $((waited % 300)) -eq 0 ] && echo "--- waiting for memory: ${f} GB free < ${MIN_FREE_GB} GB ($(date +%T))"
    sleep 30; waited=$((waited + 30))
  done
}

run() {  # run <TIMERANGE> <UNIVERSE> <TAG> <STRATEGY>
  local dir="user_data/backtest_results/stopgrid-${3:+$3-}$4"
  for attempt in 1 2 3; do
    wait_for_memory
    TIMERANGE="$1" UNIVERSE="$2" TAG="$3" bash scripts/run_stop_grid.sh "$4"
    ls "$dir"/backtest-result-*.zip > /dev/null 2>&1 && return 0
    echo "--- no result for $4 [$3] (attempt $attempt)"
  done
  echo "--- GAVE UP $4 [$3]"
}

ARMS="X7SafeRebuyStop10 X7SafeRebuyStop12 X7SafeRebuyStop18 X7SafeRebuyStop20 X7SafeRebuyStop30 X7SafeRebuyStop40"
for S in $ARMS; do run 20260830-20261017 live r26p "$S"; done
for S in $ARMS; do run 20250216-20260816 survB r26 "$S"; done
for S in $ARMS; do run 20250216-20260816 live r26w4 "$S"; done
echo "=== QUEUE FINISHED"
