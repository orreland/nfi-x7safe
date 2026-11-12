"""Daily check for V40: does the live top-40 list match the backtest ranking table?

reports/PLAN_V40_SPEEDUP_2026-11-10.md section 2.3: more than 2 coins different -> find out why before trusting it.

Usage:
  python tools/v40_list_check.py --log <freqtrade log> [--day 2026-11-10] [--datadir user_data/data/binance]

It reads the last "Whitelist with N pairs: [...]" line of the log for that UTC day (or --live "A/USDT,B/USDT")
and compares it with two rankings built from local 1d candles of the 30 finished days before the day:
  close   - volume x close, what X7SafeUniverse.allowed_table uses in backtests;
  typical - volume x (high+low+close)/3, what freqtrade's VolumePairList uses live.
Coins with open trades are added to the live whitelist by freqtrade, so a few extra live coins can be normal;
they are listed separately. Read-only; needs 1d data downloaded up to the day before --day.
"""

import argparse
import ast
import json
import re
import sys
from pathlib import Path

import pandas as pd



def load_pairs(static_file, blacklist_file):
  def read(f):
    txt = Path(f).read_text(encoding="utf-8")
    txt = re.sub(r"^\s*//.*$", "", txt, flags=re.M)
    return json.loads(txt)

  pairs = read(static_file)["exchange"]["pair_whitelist"]
  bl = read(blacklist_file)["exchange"].get("pair_blacklist", []) if blacklist_file else []
  pats = [re.compile(b) for b in bl]
  return [p for p in pairs if not any(r.fullmatch(p) for r in pats)]


def rank(pairs, datadir, day, top_n, price):
  vals = {}
  for p in pairs:
    f = Path(datadir) / f"{p.replace('/', '_')}-1d.feather"
    if not f.exists():
      continue
    d = pd.read_feather(f).set_index("date")
    d = d[d.index < day]  # finished days only
    if len(d) < 30 or d.index[-1] < day - pd.Timedelta(days=1):
      continue  # missing recent data: same as "no row" in the backtest table
    px = d["close"] if price == "close" else (d["high"] + d["low"] + d["close"]) / 3
    vals[p] = float((d["volume"] * px).iloc[-30:].sum())
  s = pd.Series(vals).sort_values(ascending=False, kind="stable")
  return list(s.index[:top_n]), s


def live_list(log, day):
  last = None
  for line in Path(log).read_text(encoding="utf-8", errors="replace").splitlines():
    m = re.match(r"(?:.*?freqtrade\[\d+\]: )?(\d{4}-\d\d-\d\d) .*Whitelist with \d+ pairs: (\[.*\])", line)
    if m and m.group(1) == day.strftime("%Y-%m-%d"):
      last = ast.literal_eval(m.group(2))
  return last


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--log")
  ap.add_argument("--live", help="comma separated list instead of --log")
  ap.add_argument("--day", default=pd.Timestamp.now("UTC").strftime("%Y-%m-%d"))
  ap.add_argument("--datadir", default="user_data/data/binance")
  ap.add_argument("--static", default="configs/pairlist-backtest-static-binance-spot-usdt.json")
  ap.add_argument("--blacklist", default="configs/blacklist-binance.json")
  ap.add_argument("--top", type=int, default=40)
  a = ap.parse_args()

  day = pd.Timestamp(a.day, tz="UTC")
  pairs = load_pairs(a.static, a.blacklist)
  bt, s_close = rank(pairs, a.datadir, day, a.top, "close")
  ty, _ = rank(pairs, a.datadir, day, a.top, "typical")
  print(f"day {day.date()}  pairs ranked {len(s_close)} of {len(pairs)}  window {(day - pd.Timedelta(days=30)).date()} .. {(day - pd.Timedelta(days=1)).date()}")
  print(f"close vs typical ranking: {len(set(bt) ^ set(ty)) // 2} coin(s) differ  close-only {sorted(set(bt) - set(ty))}  typical-only {sorted(set(ty) - set(bt))}")

  live = a.live.split(",") if a.live else (live_list(a.log, day) if a.log else None)
  if not live:
    print("no live list for that day (give --log with a 'Whitelist with' line, or --live)")
    return 2
  extra = sorted(set(live) - set(bt))
  missing = sorted(set(bt) - set(live))
  diff = len(missing)
  print(f"live list {len(live)} coins")
  print(f"  backtest top-{a.top} missing from live: {missing}")
  print(f"  live coins not in backtest top-{a.top}: {extra} (coins with open trades are kept by freqtrade)")
  verdict = "OK" if diff <= 2 else "CHECK: more than 2 coins differ"
  print(f"result: {diff} coin(s) differ -> {verdict}")
  return 0 if diff <= 2 else 1


if __name__ == "__main__":
  sys.exit(main())
