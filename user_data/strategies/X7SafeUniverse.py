"""X7Safe that opens new trades only in high-volume (and optionally up-trending) coins.

reports/UNIVERSE_VOLUME_2026-11-06.md. Backtest only. Adds, rebuys and exits are untouched:
confirm_trade_entry only runs for new trades.
"""

import logging
from pathlib import Path

import pandas as pd

from X7SafeEntryPolicy import X7SafeEntryChase

log = logging.getLogger(__name__)


def allowed_table(pairs, datadir, top_n: int, trend_days: int = 0) -> pd.DataFrame:
  """Day x pair booleans. Row D only uses daily candles up to D-1, so it is known at D 00:00 UTC."""
  qv, up = {}, {}
  for p in pairs:
    f = Path(datadir) / f"{p.split(':')[0].replace('/', '_')}-1d.feather"
    if not f.exists():
      log.warning(f"UNIVERSE no 1d data {p}")
      continue
    d = pd.read_feather(f, columns=["date", "close", "volume"]).set_index("date")
    qv[p] = (d["volume"] * d["close"]).rolling(30, min_periods=30).sum().shift(1)
    if trend_days:
      up[p] = (d["close"] > d["close"].rolling(trend_days, min_periods=trend_days).mean()).shift(1)
  q = pd.DataFrame(qv)
  ok = q.rank(axis=1, ascending=False, method="first") <= top_n
  if trend_days:
    ok &= pd.DataFrame(up).reindex(index=ok.index, columns=ok.columns).fillna(False).astype(bool)
  return ok


class X7SafeVol20(X7SafeEntryChase):
  top_n = 20
  trend_days = 0
  _allowed = None
  _ucount = {"allowed": 0, "blocked": 0}

  def bot_start(self, **kwargs) -> None:
    super().bot_start(**kwargs)
    type(self)._allowed = None
    type(self)._ucount = {"allowed": 0, "blocked": 0}

  def _is_allowed(self, pair, current_time) -> bool:
    if self._allowed is None:
      type(self)._allowed = allowed_table(self.dp.current_whitelist(), self.config["datadir"], self.top_n, self.trend_days)
      log.info(f"UNIVERSE table {self._allowed.shape}, mean allowed per day {self._allowed.sum(axis=1).mean():.1f}")
    day = pd.Timestamp(current_time).floor("D")
    a = self._allowed
    return day in a.index and pair in a.columns and bool(a.at[day, pair])

  def confirm_trade_entry(self, pair, order_type, amount, rate, time_in_force, current_time, entry_tag, side, **kwargs) -> bool:
    ok = self._is_allowed(pair, current_time)
    self._ucount["allowed" if ok else "blocked"] += 1
    if sum(self._ucount.values()) % 500 == 0:
      log.info(f"UNIVERSE {self._ucount}")
    if not ok:
      return False
    return super().confirm_trade_entry(pair, order_type, amount, rate, time_in_force, current_time, entry_tag, side, **kwargs)


class X7SafeVol40(X7SafeVol20):
  top_n = 40


class X7SafeVol40Trend(X7SafeVol20):
  top_n = 40
  trend_days = 200


# reports/UNIVERSE_SWEEP_2026-11-07.md: more thresholds, same rule.
class X7SafeVol30(X7SafeVol20):
  top_n = 30


class X7SafeVol50(X7SafeVol20):
  top_n = 50


class X7SafeVol60(X7SafeVol20):
  top_n = 60


class X7SafeVol80(X7SafeVol20):
  top_n = 80
