"""U20 universe (reports/V3_ROUND2_2026-10-26.md 1.2): top 20 pairs by mean daily
quote volume in 2025-01 (before the backtest window), delisted pairs included,
structural exclusions from blacklist-survivorship-test.json. Writes configs/v3-backtest-u20.json."""
import glob
import json
import os
import re

import pandas as pd

ROOT = r"D:\NostalgiaForInfinity"


def load(p):
    return json.loads(re.sub(r"(?m)^\s*//.*$", "", open(p, encoding="utf-8").read()))


patterns = load(os.path.join(ROOT, "configs", "blacklist-survivorship-test.json"))["exchange"]["pair_blacklist"]
rows = []
for f in glob.glob(os.path.join(ROOT, "user_data", "data", "binance", "*_USDT-5m.feather")):
    pair = os.path.basename(f).replace("-5m.feather", "").replace("_", "/")
    if any(re.fullmatch(p, pair) for p in patterns):
        continue
    df = pd.read_feather(f, columns=["date", "close", "volume"])
    jan = df[(df["date"] >= "2025-01-01") & (df["date"] < "2025-02-01")]
    if len(jan) < 0.9 * 31 * 288:  # need (almost) the whole month
        continue
    rows.append((pair, float((jan["close"] * jan["volume"]).sum() / 31)))

rows.sort(key=lambda r: -r[1])
top = [p for p, _ in rows[:20]]
print("candidates:", len(rows))
for i, (p, v) in enumerate(rows[:25], 1):
    print(f"{i:2d} {p:12s} {v / 1e6:10.1f} M USDT/day {'<- U20' if i <= 20 else ''}")
cfg = load(os.path.join(ROOT, "configs", "v3-backtest.json"))
cfg["exchange"]["pair_whitelist"] = top
cfg["//"] = "U20 universe for reports/V3_ROUND2_2026-10-26.md: top 20 by mean daily quote volume 2025-01."
json.dump(cfg, open(os.path.join(ROOT, "configs", "v3-backtest-u20.json"), "w", encoding="utf-8"), indent=2)
print("in original 8:", [p for p in top if p in cfg_orig] if (cfg_orig := load(os.path.join(ROOT, "configs", "v3-backtest.json"))["exchange"]["pair_whitelist"]) else [])
