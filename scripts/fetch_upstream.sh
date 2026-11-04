#!/usr/bin/env bash
# Fetch the exact upstream strategy files this repo was tested against. They are
# not redistributed here. Every file is checked against a pinned sha256 prefix,
# so a moved upstream cannot silently change the strategy under test.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d nfi_repo/.git ] || git clone https://github.com/iterativv/NostalgiaForInfinity.git nfi_repo
git -C nfi_repo fetch -q origin
get() { # commit source target sha256-prefix
  mkdir -p "$(dirname "$3")"
  git -C nfi_repo show "$1:$2" > "$3"
  local h
  h=$(sha256sum "$3" | cut -c1-${#4})
  [ "$h" = "$4" ] || { echo "HASH MISMATCH $3: got $h, want $4" >&2; exit 1; }
  echo "ok $3 ($1)"
}
get 296b962 NostalgiaForInfinityX7.py user_data/strategies/NostalgiaForInfinityX7.py bfe78d11c1560a44    # v17.4.543, base of the deployed X7Safe
get 3015bed NostalgiaForInfinityX7.py user_data/strategies_up/NostalgiaForInfinityX7.py c8a4f38b69697e4f # v17.5.185, reports/UPSTREAM_EVAL_2026-10-26.md
get 3f0df18 NostalgiaForInfinityX7.py user_data/strategies_comm/NostalgiaForInfinityX7.py e78c7c5e3226d1b9 # v17.5.206, community comparison
get 3f0df18 NostalgiaForInfinityX8.py user_data/strategies_comm/NostalgiaForInfinityX8.py a29beba0887ba4ca # v18.0.195, community comparison
get 3f0df18 NostalgiaForInfinityX8.py user_data/strategies_x8s/NostalgiaForInfinityX8.py a29beba0887ba4ca  # base of X8 + safety layer, reports/EXPERIMENTS_2026-11-03.md
