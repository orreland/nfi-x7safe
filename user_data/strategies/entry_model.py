"""Model of a first entry from real 1m candles (reports/ENTRY_POLICY_2026-11-04.md).

The dry-run bot sends its order about 43 s after the 5m candle opens. `decide` replays
that: the market price then is read from the candle's first minute, and a limit order
below it fills only if a later minute inside the 3-minute entry timeout trades through.
1m data comes from Binance's public archive and is cached under user_data/data_1m.
"""

import io
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path(__file__).resolve().parent.parent / "data_1m"
BASE = "https://data.binance.vision/data/spot"
ORDER_DELAY_S = 43.0
TIMEOUT_MINUTES = 3
CALIBRATION = 0.0019  # real fills minus the raw model, mean of 76 dry-run trades
_frames: dict = {}


def _get_zip(url: str):
  try:
    with urllib.request.urlopen(url, timeout=60) as r:
      raw = r.read()
  except urllib.error.HTTPError as e:
    if e.code == 404:
      return None
    raise
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
    df = pd.read_csv(z.open(z.namelist()[0]), header=None, usecols=[0, 1, 2, 3, 4])
  df.columns = ["t", "o", "h", "l", "c"]
  df = df[pd.to_numeric(df["t"], errors="coerce").notna()].astype(float)
  # Binance switched spot archives from milliseconds to microseconds in 2025.
  df["t"] = (df["t"] / 1000).where(df["t"] > 1e14, df["t"]).astype("int64")
  return df


def _load_month(symbol: str, month: str) -> pd.DataFrame:
  path = CACHE / f"{symbol}-{month}.feather"
  if path.exists():
    return pd.read_feather(path)
  df = _get_zip(f"{BASE}/monthly/klines/{symbol}/1m/{symbol}-1m-{month}.zip")
  complete = df is not None
  if df is None:
    y, m = map(int, month.split("-"))
    days, d = [], date(y, m, 1)
    while d.month == m and d < datetime.now(timezone.utc).date():
      day = _get_zip(f"{BASE}/daily/klines/{symbol}/1m/{symbol}-1m-{d:%Y-%m-%d}.zip")
      if day is not None:
        days.append(day)
      d += timedelta(days=1)
    df = pd.concat(days, ignore_index=True) if days else pd.DataFrame(columns=["t", "o", "h", "l", "c"])
  if complete:  # a month rebuilt from daily files may still grow
    CACHE.mkdir(parents=True, exist_ok=True)
    df.reset_index(drop=True).to_feather(path)
  return df


def minutes(pair: str, when: datetime):
  """The candle's first TIMEOUT_MINUTES + 1 one-minute bars, or None if unavailable."""
  symbol = pair.split(":")[0].replace("/", "")
  month = f"{when:%Y-%m}"
  key = (symbol, month)
  if key not in _frames:
    if len(_frames) > 24:
      _frames.clear()
    df = _load_month(symbol, month)
    _frames[key] = df.set_index("t").sort_index() if len(df) else None
  df = _frames[key]
  if df is None:
    return None
  t0 = int(when.timestamp() * 1000)
  bars = df.reindex([t0 + 60000 * i for i in range(TIMEOUT_MINUTES + 1)])
  return None if np.isnan(bars["o"].iloc[0]) else bars


def market_at_order(bars) -> float:
  """Price when the order goes out, interpolated inside the first minute."""
  first = bars.iloc[0]
  return float(first["o"] + (first["c"] - first["o"]) * ORDER_DELAY_S / 60.0)


def decide(pair: str, when: datetime, limit_offset):
  """Fill price for a first entry, None if the order times out, "nodata" if bars are missing.

  limit_offset None chases the market. Otherwise the limit is candle open x (1 + offset):
  at or above the market it fills at the market; below, it needs a later bar to trade
  strictly through the limit (touching is not counted as a fill).
  """
  bars = minutes(pair, when)
  if bars is None:
    return "nodata"
  market = market_at_order(bars) * (1.0 + CALIBRATION)
  if limit_offset is None:
    return market
  limit = float(bars["o"].iloc[0]) * (1.0 + limit_offset)
  if market <= limit:
    return market
  rest = bars.iloc[1:]["l"].dropna()
  return limit if (rest < limit).any() else None
