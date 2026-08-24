#!/usr/bin/env python
"""fetch_delisted_data.py - recover OHLCV data for pairs that have since been
delisted from Binance spot, so the backtest universe can be reconstructed as it
looked at the START of the test window rather than at the end.

WHY THIS EXISTS
---------------
The static pairlist used by NFI's own CI contains 160 USDT pairs. After the
blacklist is applied, 120 remain and those are the only ones the 18-month
backtest ever sees. Checking the 40 excluded pairs against Binance's live
market list today gives a striking result:

    ALL 40 are now gone from Binance spot. Not one survived.

That means the blacklist is not primarily a risk filter - it is a survivorship
filter. Every coin it removed subsequently died, and `freqtrade download-data`
cannot fetch them at all ("No pairs available for download") precisely because
ccxt only sees currently-listed markets. The backtest universe is, by
construction, "the coins that made it".

Binance does still publish historical klines for delisted symbols as static
monthly ZIPs on data.binance.vision. This script pulls those, converts them to
the feather layout freqtrade expects, and derives the higher timeframes NFI
needs (15m/1h/4h/1d) by resampling the 5m series.

USAGE
  .venv\\Scripts\\python.exe scripts\\fetch_delisted_data.py --start 2025-02 --end 2026-08
  .venv\\Scripts\\python.exe scripts\\fetch_delisted_data.py --pairs OM/USDT MKR/USDT --dry-run

Downloads only. Read-only public archive, no API key, no account, no trading.
"""

from __future__ import annotations

import argparse
import io
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "user_data" / "data" / "binance"
BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"

# The 40 pairs present in the CI pairlist but excluded by the blacklist, all of
# which are delisted from Binance spot as of 2026-08-22.
DELISTED_PAIRS = [
  "ALPACA/USDT", "ALPHA/USDT", "BADGER/USDT", "BAKE/USDT", "BETA/USDT",
  "BNX/USDT", "BURGER/USDT", "DATA/USDT", "DEGO/USDT", "DF/USDT",
  "EOS/USDT", "ERN/USDT", "FARM/USDT", "FIS/USDT", "FLM/USDT",
  "FORTH/USDT", "FTM/USDT", "FUN/USDT", "FXS/USDT", "HARD/USDT",
  "HIGH/USDT", "IDEX/USDT", "KMD/USDT", "LINA/USDT", "LIT/USDT",
  "LRC/USDT", "LTO/USDT", "MBOX/USDT", "MDT/USDT", "MKR/USDT",
  "MLN/USDT", "NKN/USDT", "OM/USDT", "PERP/USDT", "POND/USDT",
  "STPT/USDT", "SXP/USDT", "TRU/USDT", "VIDT/USDT", "WING/USDT",
]

# Binance kline CSV column order (12 columns, no header).
KLINE_COLS = [
  "open_time", "open", "high", "low", "close", "volume",
  "close_time", "quote_volume", "trades", "taker_buy_base",
  "taker_buy_quote", "ignore",
]

# NFI needs these; 5m is downloaded, the rest are resampled from it.
DERIVED_TIMEFRAMES = {"15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}


def month_range(start: str, end: str) -> list[str]:
  """['2025-02', '2025-03', ...] inclusive of both endpoints."""
  sy, sm = (int(x) for x in start.split("-"))
  ey, em = (int(x) for x in end.split("-"))
  out, y, m = [], sy, sm
  while (y, m) <= (ey, em):
    out.append(f"{y:04d}-{m:02d}")
    m += 1
    if m > 12:
      y, m = y + 1, 1
  return out


def fetch_month(symbol: str, timeframe: str, month: str) -> pd.DataFrame | None:
  """Fetch one monthly ZIP. Returns None on 404 (symbol not listed that month)."""
  url = f"{BASE_URL}/{symbol}/{timeframe}/{symbol}-{timeframe}-{month}.zip"
  try:
    with urllib.request.urlopen(url, timeout=60) as resp:
      payload = resp.read()
  except urllib.error.HTTPError as exc:
    if exc.code == 404:
      return None
    raise
  with zipfile.ZipFile(io.BytesIO(payload)) as zf:
    name = zf.namelist()[0]
    with zf.open(name) as fh:
      head = fh.read(200)
    # Binance added a CSV header row to some archives partway through 2025.
    has_header = head.lstrip().lower().startswith(b"open_time")
    with zf.open(name) as fh:
      df = pd.read_csv(
        fh,
        header=0 if has_header else None,
        names=None if has_header else KLINE_COLS,
      )
  if has_header:
    df.columns = KLINE_COLS[: len(df.columns)]
  return df


def to_freqtrade_frame(raw: pd.DataFrame) -> pd.DataFrame:
  """Binance kline CSV -> freqtrade's (date, open, high, low, close, volume)."""
  ts = pd.to_numeric(raw["open_time"], errors="coerce")
  # Binance switched open_time from milliseconds to microseconds in 2025.
  unit = "us" if ts.max() > 1e15 else "ms"
  out = pd.DataFrame(
    {
      "date": pd.to_datetime(ts, unit=unit, utc=True),
      "open": pd.to_numeric(raw["open"], errors="coerce"),
      "high": pd.to_numeric(raw["high"], errors="coerce"),
      "low": pd.to_numeric(raw["low"], errors="coerce"),
      "close": pd.to_numeric(raw["close"], errors="coerce"),
      "volume": pd.to_numeric(raw["volume"], errors="coerce"),
    }
  )
  return out.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
  """Exact OHLCV downsample. Left-closed/left-labelled matches freqtrade."""
  g = df.set_index("date").resample(rule, label="left", closed="left")
  out = g.agg(
    {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
  ).dropna(subset=["open"])
  return out.reset_index()


def write_feather(df: pd.DataFrame, pair: str, timeframe: str) -> Path:
  DATA_DIR.mkdir(parents=True, exist_ok=True)
  path = DATA_DIR / f"{pair.replace('/', '_')}-{timeframe}.feather"
  df.reset_index(drop=True).to_feather(path, compression="lz4")
  return path


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--start", default="2025-01", help="first month, YYYY-MM (one month of warmup before the test window)")
  ap.add_argument("--end", default="2026-08", help="last month, YYYY-MM")
  ap.add_argument("--pairs", nargs="*", default=None, help="override the built-in delisted list")
  ap.add_argument("--dry-run", action="store_true", help="probe availability only, write nothing")
  args = ap.parse_args()

  pairs = args.pairs or DELISTED_PAIRS
  months = month_range(args.start, args.end)
  print(f"Recovering {len(pairs)} delisted pairs x {len(months)} months from data.binance.vision")
  print(f"  window: {months[0]} .. {months[-1]}")
  print(f"  target: {DATA_DIR}\n")

  summary = []
  for i, pair in enumerate(pairs, 1):
    symbol = pair.replace("/", "")
    frames, missing = [], 0
    for month in months:
      try:
        raw = fetch_month(symbol, "5m", month)
      except Exception as exc:  # noqa: BLE001
        print(f"  [{i:2d}/{len(pairs)}] {pair:14s} {month} ERROR {type(exc).__name__}: {exc}")
        missing += 1
        continue
      if raw is None:
        missing += 1
        continue
      frames.append(to_freqtrade_frame(raw))

    if not frames:
      print(f"  [{i:2d}/{len(pairs)}] {pair:14s} NO DATA (all {len(months)} months 404)")
      summary.append({"pair": pair, "candles": 0, "first": None, "last": None, "months_missing": missing})
      continue

    df = pd.concat(frames, ignore_index=True).drop_duplicates("date").sort_values("date").reset_index(drop=True)
    first, last = df["date"].iloc[0], df["date"].iloc[-1]
    print(
      f"  [{i:2d}/{len(pairs)}] {pair:14s} {len(df):7,d} candles  "
      f"{first:%Y-%m-%d} -> {last:%Y-%m-%d}  ({missing} months absent)"
    )
    summary.append(
      {
        "pair": pair,
        "candles": len(df),
        "first": first.strftime("%Y-%m-%d"),
        "last": last.strftime("%Y-%m-%d"),
        "months_missing": missing,
      }
    )

    if args.dry_run:
      continue

    write_feather(df, pair, "5m")
    for tf, rule in DERIVED_TIMEFRAMES.items():
      write_feather(resample_ohlcv(df, rule), pair, tf)

  ok = [s for s in summary if s["candles"] > 0]
  print(f"\nRecovered {len(ok)}/{len(pairs)} pairs.")
  if ok:
    # The last candle is the de-facto delisting date - the single most useful
    # number here, because it says when a live bot would have been left holding
    # an untradeable position.
    print("\nLast candle per pair (≈ delisting date):")
    for s in sorted(ok, key=lambda x: x["last"]):
      print(f"  {s['pair']:14s} {s['last']}")
  bad = [s for s in summary if s["candles"] == 0]
  if bad:
    print(f"\nUnavailable even from the archive: {[s['pair'] for s in bad]}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
