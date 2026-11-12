"""Combined_V3 round 3 - pre-registered 2026-11-09 23:53 UTC, see reports/V3_STOP_BANDX_2026-11-10.md section 1.

Each class changes one thing on top of the server's Combined_V3.
"""

from datetime import timedelta

from pandas import DataFrame

from Combined_V3 import Combined_V3, bollinger_bands


def _rule_a(df: DataFrame):
  return (
    df["lower"].shift().gt(0)
    & df["bbdelta"].gt(df["close"] * 0.008)
    & df["closedelta"].gt(df["close"] * 0.0175)
    & df["tail"].lt(df["bbdelta"] * 0.25)
    & df["close"].lt(df["lower"].shift())
    & df["close"].le(df["close"].shift())
  )


def _rule_b(df: DataFrame):
  return (
    (df["close"] < df["ema_slow"])
    & (df["close"] < 0.985 * df["bb_lowerband"])
    & (df["volume"] < (df["volume_mean_slow"].shift(1) * 20))
  )


class Combined_V3_B0T(Combined_V3):
  """B0T: identical entries (A | B), tagged so the two rules can be counted. B wins when both fire."""

  def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
    a, b = _rule_a(dataframe), _rule_b(dataframe)
    dataframe.loc[a | b, "enter_long"] = 1
    dataframe.loc[a, "enter_tag"] = "A"
    dataframe.loc[b, "enter_tag"] = "B"
    return dataframe


class Combined_V3_S3(Combined_V3):
  stoploss = -0.03


class Combined_V3_S4(Combined_V3):
  stoploss = -0.04


class Combined_V3_S7(Combined_V3):
  stoploss = -0.07


class Combined_V3_S10(Combined_V3):
  stoploss = -0.10


class Combined_V3_S15(Combined_V3):
  stoploss = -0.15


class Combined_V3_CS(Combined_V3):
  """CS: CombinedBinHClucAndMADV9's stop, copied as written (no fixed stop, 'still sinking after 50 min' exit)."""

  stoploss = -0.99
  use_custom_stoploss = True

  def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs):
    if current_profit > 0:
      return 0.99
    trade_time_50 = current_time - timedelta(minutes=50)
    if trade_time_50 > trade.open_date_utc:
      try:
        shift = int((trade_time_50 - trade.open_date_utc).total_seconds() / 300)
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        candle = dataframe.iloc[-shift].squeeze()
        if current_rate * 1.015 < candle["open"]:
          return 0.01
      except IndexError:
        return 0.01
    return 0.99


class Combined_V3_X(Combined_V3):
  """X: rule A becomes 'close crosses back above the 40-candle lower band'; those trades exit when the close
  falls below the band's middle after having closed above it (win or lose). Rule B unchanged."""

  def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
    dataframe = super().populate_indicators(dataframe, metadata)
    mid, _ = bollinger_bands(dataframe["close"], window_size=40, num_of_std=2)
    dataframe["mid40"] = mid
    return dataframe

  def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
    x = (
      dataframe["lower"].shift().gt(0)
      & dataframe["close"].shift().lt(dataframe["lower"].shift())
      & dataframe["close"].gt(dataframe["lower"])
      & dataframe["volume"].gt(0)
    )
    b = _rule_b(dataframe)
    dataframe.loc[x | b, "enter_long"] = 1
    dataframe.loc[x, "enter_tag"] = "X"
    dataframe.loc[b, "enter_tag"] = "B"
    return dataframe

  def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
    if trade.enter_tag != "X":
      return None
    df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
    since = df[df["date"] >= trade.open_date_utc - timedelta(minutes=5)]
    if len(since) < 2:
      return None
    last = since.iloc[-1]
    if last["close"] < last["mid40"] and (since["close"].iloc[:-1] > since["mid40"].iloc[:-1]).any():
      return "x_mid_break"
    return None

  def confirm_trade_exit(self, pair, trade, order_type, amount, rate, time_in_force, exit_reason, current_time, **kwargs):
    # X trades ignore the original 'back to the 20-candle middle, in profit' signal
    if trade.enter_tag == "X" and exit_reason == "exit_signal":
      return False
    return True


class Combined_V3_XN(Combined_V3_X):
  """XN: as X, and rule-A (X) trades have no 5% take-profit. Rule B keeps 5% through custom_roi."""

  minimal_roi = {"0": 100}
  use_custom_roi = True

  def custom_roi(self, pair, trade, current_time, trade_duration, entry_tag, side, **kwargs):
    return None if entry_tag == "X" else 0.05
