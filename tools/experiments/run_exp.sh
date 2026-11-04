#!/usr/bin/env bash
# reports/EXPERIMENTS_2026-11-03.md: one backtest at a time. usage: run_exp.sh smoke|all
cd /d/NostalgiaForInfinity || exit 1
export PYTHONUTF8=1 PYTHONPATH="$(cygpath -w "$PWD/pypatches")" FT_LOWMEM=1
export TEMP='D:\NostalgiaForInfinity\scratch\tmp' TMP='D:\NostalgiaForInfinity\scratch\tmp'
PY=.venv/Scripts/python.exe
BASE=(--user-data-dir=./user_data --config=configs/exampleconfig.json --config=configs/exampleconfig_secret.json --config=configs/trading_mode-spot.json --config=configs/local-overrides-safe.json)
LIVE=(--config=configs/blacklist-binance.json --config=configs/pairlist-backtest-static-binance-spot-usdt.json)
SURV=(--config=configs/blacklist-survivorship-test.json --config=configs/pairlist-survivorship-B-real-universe.json)
MAIN=(--config=configs/blacklist-binance.json --config=configs/pairlist-mainstream14.json)
OURS=user_data/strategies; X8S=user_data/strategies_x8s
gate() { for i in $(seq 1 120); do F=$(powershell.exe -NoProfile -Command "[math]::Floor((Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory/1MB)" | tr -d '\r'); [ "${F:-0}" -ge 19 ] && break; sleep 30; done; }
nfi() { # name strategy path universe window
  local dir="user_data/backtest_results/exp-$1"; local -n uni=$4
  case $5 in P) r=20261025-20261103;; R) r=20260830-20261103;; L) r=20250216-20261103;; esac
  gate; mkdir -p "$dir"; echo "=== START $1 free=${F}GB $(date +%T)"
  "$PY" scripts/ft_delisted.py backtesting --strategy="$2" --strategy-path="$3" --timerange="$r" "${BASE[@]}" "${uni[@]}" \
    --enable-protections --breakdown month --export trades --cache none --backtest-directory="$dir" > "logs_exp_$1.log" 2>&1
  echo "=== DONE $1 rc=$? errs=$(grep -c ' - ERROR - ' "logs_exp_$1.log") $(date +%T)"
}
trend() { # name window
  local dir="user_data/backtest_results/exp-$1"; mkdir -p "$dir"; echo "=== START $1 $(date +%T)"
  "$PY" -m freqtrade backtesting --strategy=TrendDonchian --strategy-path=user_data/strategies_trend --timerange="$2" \
    --user-data-dir=./user_data --datadir=user_data/data_long/binance --config=configs/trend-backtest.json \
    --timeframe=1d --breakdown year --export trades --cache none --backtest-directory="$dir" > "logs_exp_$1.log" 2>&1
  echo "=== DONE $1 rc=$? errs=$(grep -c ' - ERROR - ' "logs_exp_$1.log") $(date +%T)"
}
if [ "$1" = smoke ]; then
  nfi smoke-OURS-S X7SafeSlip $OURS LIVE P
  nfi smoke-X8S X8SafeStopHonored $X8S LIVE P
  nfi smoke-X8S-S X8SafeSlip $X8S LIVE P
  "$PY" -m freqtrade download-data --user-data-dir=./user_data --datadir=user_data/data_long/binance --config=configs/trend-backtest.json --timeframes 1d --timerange 20200101-20261104 > logs_exp_dl.log 2>&1; echo "dl rc=$?"
  trend smoke-T1 20261025-20261103
else
  nfi OURS-S-comm-L X7SafeSlip $OURS SURV L
  nfi OURS-S-comm-R X7SafeSlip $OURS LIVE R
  nfi OURS-S-main-L X7SafeSlip $OURS MAIN L
  nfi X8S-comm-L X8SafeStopHonored $X8S SURV L
  nfi X8S-comm-R X8SafeStopHonored $X8S LIVE R
  nfi X8S-main-L X8SafeStopHonored $X8S MAIN L
  nfi X8S-main-R X8SafeStopHonored $X8S MAIN R
  nfi X8S-S-comm-L X8SafeSlip $X8S SURV L
  nfi X8S-S-comm-R X8SafeSlip $X8S LIVE R
  nfi X8N-comm-L X8SafeNoDoom $X8S SURV L
  nfi X8N-comm-R X8SafeNoDoom $X8S LIVE R
  nfi X8N-main-L X8SafeNoDoom $X8S MAIN L
  nfi X8-S-comm-L X8CommSlip $X8S SURV L
  nfi X8-S-comm-R X8CommSlip $X8S LIVE R
  trend T1-L 20250216-20261103
  trend T1-R 20260830-20261103
  trend T1-W5 20210101-20261103
  echo "=== ALL DONE $(date +%T)"
fi
