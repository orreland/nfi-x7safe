#!/usr/bin/env bash
# reports/PARITY_COMMUNITY_2026-11-03.md: one queue, one backtest at a time.
cd /d/NostalgiaForInfinity || exit 1
export PYTHONUTF8=1 PYTHONPATH="$(cygpath -w "$PWD/pypatches")" FT_LOWMEM=1
export TEMP='D:\NostalgiaForInfinity\scratch\tmp' TMP='D:\NostalgiaForInfinity\scratch\tmp'
LIVE=(--config=configs/blacklist-binance.json --config=configs/pairlist-backtest-static-binance-spot-usdt.json)
SURV=(--config=configs/blacklist-survivorship-test.json --config=configs/pairlist-survivorship-B-real-universe.json)
BASE=(--user-data-dir=./user_data --config=configs/exampleconfig.json --config=configs/exampleconfig_secret.json --config=configs/trading_mode-spot.json --config=configs/local-overrides-safe.json)
echo "=== DOWNLOAD $(date +%T)"
.venv/Scripts/python.exe scripts/ft_delisted.py download-data "${BASE[@]}" "${LIVE[@]}" --timeframes 5m 15m 1h 4h 1d > logs_comm_dl_live.log 2>&1; echo "live rc=$?"
.venv/Scripts/python.exe scripts/ft_delisted.py download-data "${BASE[@]}" "${SURV[@]}" --timeframes 5m 15m 1h 4h 1d > logs_comm_dl_surv.log 2>&1; echo "surv rc=$?"
run() { # name strategy path timerange universe
  local name=$1 s=$2 p=$3 tr=$4 u=$5 dir="user_data/backtest_results/comm-$1"
  local -n uni=$u
  for i in $(seq 1 120); do F=$(powershell.exe -NoProfile -Command "[math]::Floor((Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory/1MB)" | tr -d '\r'); [ "${F:-0}" -ge 19 ] && break; sleep 30; done
  mkdir -p "$dir"; echo "=== START $name free=${F}GB $(date +%T)"
  .venv/Scripts/python.exe scripts/ft_delisted.py backtesting --strategy="$s" --strategy-path="$p" --timerange="$tr" "${BASE[@]}" "${uni[@]}" \
    --enable-protections --breakdown month --export trades --cache none --backtest-directory="$dir" > "logs_comm_$name.log" 2>&1
  echo "=== DONE $name rc=$? $(date +%T)"; grep -A3 "STRATEGY SUMMARY" "logs_comm_$name.log" | tail -1 | cut -c1-110
}
OURS=user_data/strategies; COMM=user_data/strategies_comm
for w in "P 20261025-20261103 LIVE" "R 20260830-20261103 LIVE" "L 20250216-20261103 SURV"; do set -- $w
  run "$1-OURS" X7SafeStopHonored $OURS "$2" "$3"
  run "$1-X7" NostalgiaForInfinityX7 $COMM "$2" "$3"
  run "$1-X8" NostalgiaForInfinityX8 $COMM "$2" "$3"
done
echo "=== ALL DONE $(date +%T)"
