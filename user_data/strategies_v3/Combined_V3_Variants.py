"""Combined_V3 exit / concurrency variants - pre-registered 2026-10-25, see
reports/V3_EXIT_EXPERIMENT_2026-10-25.md section 1. Each class changes one
thing so the difference is attributable."""

from freqtrade.strategy import IntParameter

from Combined_V3 import Combined_V3


class Combined_V3_P05(Combined_V3):
  """P05: signal exits only when profit >= 0.5% (exit_profit_only already True)."""

  exit_profit_offset = 0.005


class Combined_V3_P10(Combined_V3):
  """P10: signal exits only when profit >= 1%."""

  exit_profit_offset = 0.01


class Combined_V3_C2(Combined_V3):
  """C2: at most 2 new entries per 5m candle (was 4)."""

  max_concurrent_entries_per_candle = IntParameter(1, 7, default=2, space="buy", optimize=False, load=True)


# ---------------------------------------------------------------------------
# Round 2 (pre-registered 2026-10-26, reports/V3_ROUND2_2026-10-26.md 1.1).
# ---------------------------------------------------------------------------
from datetime import timedelta  # noqa: E402

from freqtrade.strategy import merge_informative_pair  # noqa: E402


class _V3WithBTC(Combined_V3):
  """Adds BTC/USDT 1h and 24h returns (same 5m timeframe, merged by date, no lookahead)."""

  def informative_pairs(self):
    return [("BTC/USDT", self.timeframe)]

  def populate_indicators(self, dataframe, metadata):
    dataframe = super().populate_indicators(dataframe, metadata)
    btc = self.dp.get_pair_dataframe("BTC/USDT", self.timeframe)[["date", "close"]].copy()
    btc["btc_ret_1h"] = btc["close"] / btc["close"].shift(12) - 1
    btc["btc_ret_24h"] = btc["close"] / btc["close"].shift(288) - 1
    return merge_informative_pair(
      dataframe, btc[["date", "btc_ret_1h", "btc_ret_24h"]], self.timeframe, self.timeframe, ffill=True
    )


class Combined_V3_K1(_V3WithBTC):
  """K1: no new entries while BTC is down more than 3% over the last hour."""

  def populate_entry_trend(self, dataframe, metadata):
    dataframe = super().populate_entry_trend(dataframe, metadata)
    dataframe.loc[dataframe["btc_ret_1h_5m"] < -0.03, "enter_long"] = 0
    return dataframe


class Combined_V3_K2(Combined_V3):
  """K2: global StoplossGuard - 2 stop-losses on any pairs within 2h pause all entries for 2h."""

  @property
  def protections(self):
    return list(super().protections) + [
      {
        "method": "StoplossGuard",
        "lookback_period_candles": 24,
        "trade_limit": 2,
        "stop_duration_candles": 24,
        "only_per_pair": False,
      }
    ]


class _V3TimeStop(Combined_V3):
  time_stop_hours = 24

  def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
    if current_profit < 0 and current_time - trade.open_date_utc >= timedelta(hours=self.time_stop_hours):
      return f"time_stop_{self.time_stop_hours}h"
    return None


class Combined_V3_T12(_V3TimeStop):
  """T12: exit a losing trade after 12 hours."""

  time_stop_hours = 12


class Combined_V3_T24(_V3TimeStop):
  """T24: exit a losing trade after 24 hours."""

  time_stop_hours = 24


class Combined_V3_PC(_V3WithBTC):
  """PC: signal exits need >= 1% profit (like P10), except while BTC is down more
  than 3% over 24h, when any profit is enough (like the baseline)."""

  pc_min_profit = 0.01
  pc_crash = -0.03

  def confirm_trade_exit(self, pair, trade, order_type, amount, rate, time_in_force, exit_reason, current_time, **kwargs):
    if exit_reason == "exit_signal" and trade.calc_profit_ratio(rate) < self.pc_min_profit:
      df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
      if len(df) and df["btc_ret_24h_5m"].iloc[-1] > self.pc_crash:
        return False
    return True
