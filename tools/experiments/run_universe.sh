#!/usr/bin/env bash
# reports/UNIVERSE_VOLUME_2026-11-06.md: one backtest at a time, skips finished runs. usage: run_universe.sh smoke|all|sweep
cd "$(dirname "$0")/../.." || exit 1
export PYTHONUTF8=1 PYTHONPATH="$(cygpath -w "$PWD/pypatches")" FT_LOWMEM=1
export TEMP='D:\NostalgiaForInfinity\scratch\tmp' TMP='D:\NostalgiaForInfinity\scratch\tmp'
BASE=(--user-data-dir=./user_data --config=configs/exampleconfig.json --config=configs/exampleconfig_secret.json --config=configs/trading_mode-spot.json --config=configs/local-overrides-safe.json)
LIVE=(--config=configs/blacklist-binance.json --config=configs/pairlist-backtest-static-binance-spot-usdt.json)
SURV=(--config=configs/blacklist-survivorship-test.json --config=configs/pairlist-survivorship-B-real-universe.json)
MAIN=(--config=configs/blacklist-binance.json --config=configs/pairlist-mainstream14.json)
FAILED=""
run() { # name strategy universe range min_free_gb
  local dir="user_data/backtest_results/univ-$1" rc=1; local -n uni=$3
  ls "$dir"/backtest-result-*.zip >/dev/null 2>&1 && { echo "=== SKIP $1 already done"; return; }
  for attempt in 1 2 3; do
    # never start below the gate: a long run below it fails with MemoryError
    i=0; while :; do F=$(powershell.exe -NoProfile -Command "[math]::Floor((Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory/1MB)" | tr -d '\r'); [ "${F:-0}" -ge "$5" ] && break
      [ $((i % 20)) = 0 ] && echo "... $1 waiting for ${5}GB free, now ${F}GB $(date +%T)"; i=$((i + 1)); sleep 30; done
    mkdir -p "$dir"; echo "=== START $1 try=$attempt free=${F}GB $(date +%T)"
    .venv/Scripts/python.exe scripts/ft_delisted.py backtesting --strategy="$2" --strategy-path=user_data/strategies --timerange="$4" "${BASE[@]}" "${uni[@]}" \
      --enable-protections --breakdown month --export trades --cache none --backtest-directory="$dir" > "logs_univ_$1.log" 2>&1
    rc=$?; echo "=== DONE $1 rc=$rc $(grep -E 'UNIVERSE (table|\{)' "logs_univ_$1.log" | tail -1 | sed 's/.*UNIVERSE //') $(date +%T)"
    [ $rc = 0 ] && break
  done
  [ $rc = 0 ] || FAILED="$FAILED $1"
}
L=20250216-20261103; R=20260830-20261103
if [ "$1" = sweep ]; then  # reports/UNIVERSE_SWEEP_2026-11-07.md
  for a in "V30 X7SafeVol30" "V50 X7SafeVol50" "V60 X7SafeVol60" "V80 X7SafeVol80"; do set -- $a
    run "$1-L" "$2" SURV $L 36
    run "$1-R" "$2" LIVE $R 25
  done
elif [ "$1" = smoke ]; then
  run smoke-V40T-P X7SafeVol40Trend LIVE 20261025-20261103 20
else
  run S14-L X7SafeEntryChase MAIN $L 20
  run S14-R X7SafeEntryChase MAIN $R 20
  for a in "V20 X7SafeVol20" "V40 X7SafeVol40" "V40T X7SafeVol40Trend"; do set -- $a
    run "$1-L" "$2" SURV $L 36
    run "$1-R" "$2" LIVE $R 25
  done
fi
echo "=== ALL DONE failed=[$FAILED ] $(date +%T)"
[ -z "$FAILED" ]
