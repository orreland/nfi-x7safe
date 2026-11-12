"""reports/T3_NEWCOINS_2026-11-09.md 1.2: pick the yearly top-20 new coins and download their daily candles.

Public data only (data.binance.vision, plus api.binance.com klines for gaps). No account or key.
Run from the repo root with PYTHONUTF8=1. Cache: user_data/data_t3.
"""
import io
import json
import re
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

CACHE = Path("user_data/data_t3")
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
BASE = "https://data.binance.vision/data/spot"
USED = {"BTC", "ETH", "XRP", "SOL", "DOGE", "ADA", "TRX", "LINK", "AVAX", "DOT", "BCH", "LTC", "SHIB", "UNI"}
STABLE = {"USDC", "BUSD", "TUSD", "USDP", "PAX", "DAI", "FDUSD", "USDS", "SUSD", "UST", "USTC", "EUR", "GBP", "AUD", "TRY", "BRL",
          "RUB", "NGN", "UAH", "BIDR", "IDRT", "ZAR", "AEUR", "EURI", "USD1", "XUSD", "USDE", "PYUSD", "RLUSD", "FRAX", "LUSD", "GUSD",
          "BKRW", "BVND", "VAI", "USDSB", "JPY", "MXN", "ARS", "COP", "PLN", "RON", "CZK", "BFUSD"}
WRAPPED = {"PAXG", "WBTC", "BETH", "WBETH", "XAUT"}
YEARS = range(2020, 2026)  # December of these years picks the next year's list
TOP = 20
COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume"]


def get(url, timeout=60):
  for attempt in range(4):
    try:
      with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()
    except urllib.error.HTTPError as e:
      if e.code == 404:
        return None
      if attempt == 3:
        raise
    except (urllib.error.URLError, TimeoutError, ConnectionError):
      if attempt == 3:
        raise


def symbols():
  out, marker = [], ""
  while True:
    xml = get(f"{S3}?prefix=data/spot/monthly/klines/&delimiter=/&marker={marker}").decode()
    out += re.findall(r"<Prefix>data/spot/monthly/klines/([A-Z0-9]+)/</Prefix>", xml)
    if "<IsTruncated>true</IsTruncated>" not in xml:
      return out
    marker = re.search(r"<NextMarker>(.*?)</NextMarker>", xml).group(1)


def excluded(base):
  if base in USED or base in STABLE or base in WRAPPED:
    return True
  return len(base) > 4 and base.endswith(("UP", "DOWN", "BULL", "BEAR"))


def month(sym, ym, daily=False):
  url = f"{BASE}/{'daily' if daily else 'monthly'}/klines/{sym}/1d/{sym}-1d-{ym}.zip"
  raw = get(url)
  if raw is None:
    return None
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
    txt = z.open(z.namelist()[0]).read().decode()
  df = pd.read_csv(io.StringIO(txt), header=0 if txt[:4] == "open" else None).iloc[:, :8]
  df.columns = COLS
  t = df["open_time"].astype("int64")
  t = t.where(t < 10**14, t // 1000)  # files from 2025 on use microseconds
  df["date"] = pd.to_datetime(t, unit="ms")
  return df[["date", "open", "high", "low", "close", "volume", "quote_volume"]].astype({c: float for c in ("open", "high", "low", "close", "volume", "quote_volume")})


def universe():
  path = CACHE / "universe.json"
  if path.exists():
    return {int(k): v for k, v in json.loads(path.read_text()).items()}, pd.read_csv(CACHE / "dec_volume.csv")
  syms = [s for s in symbols() if s.endswith("USDT") and not excluded(s[:-4])]
  print(f"USDT spot symbols after exclusions: {len(syms)}")
  rows = []
  with ThreadPoolExecutor(16) as ex:
    for y in YEARS:
      for s, df in zip(syms, ex.map(lambda s: month(s, f"{y}-12"), syms)):
        if df is not None:
          rows.append({"year": y, "symbol": s, "days": len(df), "quote_volume": df["quote_volume"].sum()})
  vol = pd.DataFrame(rows)
  CACHE.mkdir(parents=True, exist_ok=True)
  vol.to_csv(CACHE / "dec_volume.csv", index=False)
  uni = {y + 1: vol[vol.year == y].nlargest(TOP, "quote_volume")["symbol"].str[:-4].tolist() for y in YEARS}
  path.write_text(json.dumps(uni, indent=1))
  return uni, vol


def candles(coin):
  path = CACHE / f"{coin}_USDT-1d.feather"
  if path.exists():
    return pd.read_feather(path)
  sym = f"{coin}USDT"
  months = [str(m) for m in pd.period_range("2019-01", "2026-10", freq="M")]
  parts = [month(sym, m) for m in months]
  parts += [month(sym, d, daily=True) for d in ("2026-11-01", "2026-11-02")]
  df = pd.concat([p for p in parts if p is not None]).drop_duplicates("date").sort_values("date").reset_index(drop=True)
  df = df[df.date <= "2026-11-02"]
  gaps = pd.date_range(df.date.iloc[0], df.date.iloc[-1], freq="D").difference(df.date)
  if len(gaps):  # archive holes inside the coin's life: fill from the public klines endpoint
    fill = []
    for d in gaps:
      x = json.loads(get(f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=1d&startTime={int(d.timestamp() * 1000)}&limit=1") or b"[]")
      if x and int(x[0][0]) == int(d.timestamp() * 1000):
        fill.append({"date": d, **{k: float(x[0][i]) for i, k in ((1, "open"), (2, "high"), (3, "low"), (4, "close"), (5, "volume"), (7, "quote_volume"))}})
    print(f"  {coin}: {len(gaps)} missing day(s) in the archive, filled {len(fill)} from the API: {[d.strftime('%Y-%m-%d') for d in gaps[:6]]}")
    if fill:
      df = pd.concat([df, pd.DataFrame(fill)]).sort_values("date").reset_index(drop=True)
  df.to_feather(path)
  return df


if __name__ == "__main__":
  uni, vol = universe()
  for y, coins in uni.items():
    print(f"{y}: {' '.join(coins)}")
  allc = sorted({c for v in uni.values() for c in v})
  print(f"{len(allc)} distinct coins")
  with ThreadPoolExecutor(8) as ex:
    data = dict(zip(allc, ex.map(candles, allc)))
  for c, d in data.items():
    print(f"  {c:8s} {d.date.iloc[0].date()} .. {d.date.iloc[-1].date()}  {len(d)} days")
