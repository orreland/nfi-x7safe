"""Long-only daily Donchian ensemble, rules fixed in reports/EXPERIMENTS_2026-11-03.md 1.4."""

from datetime import datetime

import numpy as np
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy
from pandas import DataFrame

LOOKBACKS = (20, 60, 120)


def donchian_state(close: np.ndarray, high: np.ndarray, low: np.ndarray, n: int) -> np.ndarray:
  """1 from a close above the prior n-day high until a close below the n-day channel mid."""
  state = np.zeros(len(close))
  on = 0.0
  for i in range(n, len(close)):
    upper = high[i - n : i].max()
    mid = (upper + low[i - n : i].min()) / 2.0
    if close[i] > upper:
      on = 1.0
    elif close[i] < mid:
      on = 0.0
    state[i] = on
  return state


class TrendDonchian(IStrategy):
  INTERFACE_VERSION = 3
  timeframe = "1d"
  startup_candle_count = 130
  can_short = False
  minimal_roi = {"0": 100}
  stoploss = -0.30
  use_exit_signal = True
  exit_profit_only = False
  process_only_new_candles = True
  max_weight = 0.20
  target_vol = 0.10

  def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
    c, h, l = dataframe["close"].values, dataframe["high"].values, dataframe["low"].values
    dataframe["score"] = sum(donchian_state(c, h, l, n) for n in LOOKBACKS)
    dataframe["ann_vol"] = dataframe["close"].pct_change().rolling(60).std() * np.sqrt(365)
    return dataframe

  def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
    dataframe.loc[(dataframe["score"] >= 2) & (dataframe["volume"] > 0), "enter_long"] = 1
    return dataframe

  def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
    dataframe.loc[dataframe["score"] == 0, "exit_long"] = 1
    return dataframe

  def custom_stake_amount(
    self,
    pair: str,
    current_time: datetime,
    current_rate: float,
    proposed_stake: float,
    min_stake,
    max_stake: float,
    leverage: float,
    entry_tag,
    side: str,
    **kwargs,
  ) -> float:
    df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
    vol = df["ann_vol"].iloc[-1] if len(df) else np.nan
    weight = self.max_weight if not np.isfinite(vol) or vol <= 0 else min(self.max_weight, self.target_vol / vol)
    equity = Trade.total_open_trades_stakes() + self.wallets.get_free(self.config["stake_currency"])
    return min(equity * weight, max_stake)
