#!/usr/bin/env bash
# Sequential long-run queue for the section-14 experiment. One backtest at a
# time (an 18-month run peaks near the machine's commit limit), FT_LOWMEM on,
# up to 2 retries when a run leaves no result zip (MemoryError).
cd /d/NostalgiaForInfinity || exit 1
export FT_LOWMEM=1

run() {  # run <TIMERANGE> <UNIVERSE> <TAG> <STRATEGY>
  local dir="user_data/backtest_results/stopgrid-${3:+$3-}$4"
  for attempt in 1 2 3; do
    TIMERANGE="$1" UNIVERSE="$2" TAG="$3" bash scripts/run_stop_grid.sh "$4"
    ls "$dir"/backtest-result-*.zip > /dev/null 2>&1 && return 0
    echo "--- no result for $4 [$3] (attempt $attempt)"
  done
  echo "--- GAVE UP $4 [$3]"
}

for S in X7SafeOtherStop20 X7SafeOtherStop25 X7SafeOtherNoStop; do run 20250216-20260816 survB "" "$S"; done
for S in X7SafeStopHonored X7SafeRebuyDoom15; do run 20250216-20260816 live w4 "$S"; done
for S in X7SafeOtherStop20 X7SafeOtherStop25 X7SafeOtherNoStop; do run 20250216-20261017 survB ext "$S"; done
echo "=== QUEUE FINISHED"
