#!/usr/bin/env bash
# reports/V3_STOP_BANDX_2026-11-10.md: all round-3 backtests, one at a time.
cd /d/NostalgiaForInfinity || exit 1
SEGS=(20250216-20250418 20250418-20250618 20250618-20250817 20250817-20251017 20251017-20251217
      20251217-20260216 20260216-20260418 20260418-20260617 20260617-20260817 20260817-20261017)
ARMS=(Combined_V3_B0T Combined_V3_S3 Combined_V3_S4 Combined_V3_S7 Combined_V3_S10 Combined_V3_S15 Combined_V3_CS Combined_V3_X Combined_V3_XN)
TAG=vn TIMERANGE=20261017-20261103 bash tools/experiments/run_v3.sh Combined_V3
for A in "${ARMS[@]}"; do
  TAG=v1 TIMERANGE=20250216-20261017 bash tools/experiments/run_v3.sh "$A"
  TAG=vp TIMERANGE=20260822-20261017 bash tools/experiments/run_v3.sh "$A"
  TAG=vn TIMERANGE=20261017-20261103 bash tools/experiments/run_v3.sh "$A"
  for i in "${!SEGS[@]}"; do TAG=$(printf seg%02d $((i + 1))) TIMERANGE=${SEGS[$i]} bash tools/experiments/run_v3.sh "$A"; done
done
echo "=== ALL DONE nonzero_rc=$(grep -c "rc=[1-9]" logs_v3r3_queue.log)"
