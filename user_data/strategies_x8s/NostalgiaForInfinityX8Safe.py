"""X8 under the deployed X7Safe safety layer, for backtesting only.
Definition and pre-checks: reports/EXPERIMENTS_2026-11-03.md 1.3. The base class is
upstream X8 at 3f0df18 (scripts/fetch_upstream.sh); entry signals are untouched."""

import logging
from datetime import datetime

from freqtrade.persistence import Trade
from freqtrade.strategy import stoploss_from_absolute

from NostalgiaForInfinityX8 import NostalgiaForInfinityX8

log = logging.getLogger(__name__)

REBUY_TAGS = {"61", "62", "63", "64", "65", "68"}


def slipped_first_entry(trade, proposed_rate: float, entry_tag) -> float:
  """Raise a trade's first entry by the mean gap measured for its side; DCA fills stay put."""
  if trade is not None:
    return proposed_rate
  tags = (entry_tag or "").split()
  rebuy = bool(tags) and any(t in REBUY_TAGS for t in tags)
  return proposed_rate * (1.0 + (0.0037 if rebuy else 0.0071))


class X8SafeStopHonored(NostalgiaForInfinityX8):
  stoploss = -0.15
  use_custom_stoploss = True
  rebuy_hard_stop = 0.15
  other_hard_stop = 0.25

  system_v4_stops_enable = True
  system_v4_stop_threshold_doom_spot = 0.08
  system_v4_max_stake = 0.5

  time_stop_days = 30
  stake_pct_of_equity = 0.15
  stake_pct_cap = 4500.0

  def _is_rebuy_trade(self, trade: Trade) -> bool:
    enter_tags = (trade.enter_tag or "").split()
    rebuy_tags = self.long_rebuy_mode_tags
    return bool(enter_tags) and (
      all(c in rebuy_tags for c in enter_tags)
      or (any(c in rebuy_tags for c in enter_tags) and all(c in self.long_rebuy_grind_mode_tags for c in enter_tags))
    )

  def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs):
    if not after_fill or trade.nr_of_successful_entries != 1 or trade.nr_of_successful_exits != 0:
      return None
    distance = self.rebuy_hard_stop if self._is_rebuy_trade(trade) else self.other_hard_stop
    if distance == -self.stoploss:
      return None
    first_price = trade.select_filled_orders(trade.entry_side)[0].safe_price
    stop = stoploss_from_absolute(
      first_price * (1.0 - distance), current_rate, is_short=trade.is_short, leverage=trade.leverage
    )
    return stop or None

  def custom_stake_amount(
    self, pair, current_time, current_rate, proposed_stake, min_stake, max_stake, leverage, entry_tag, side, **kwargs
  ) -> float:
    total_equity = Trade.total_open_trades_stakes() + self.wallets.get_free(self.config["stake_currency"])
    proposed_stake = min(total_equity * self.stake_pct_of_equity, self.stake_pct_cap)
    return super().custom_stake_amount(
      pair, current_time, current_rate, proposed_stake, min_stake, max_stake, leverage, entry_tag, side, **kwargs
    )

  def confirm_trade_exit(
    self, pair, trade, order_type, amount, rate, time_in_force, exit_reason, current_time: datetime, **kwargs
  ) -> bool:
    if exit_reason in ("stop_loss", "trailing_stop_loss"):
      return True
    return super().confirm_trade_exit(
      pair, trade, order_type, amount, rate, time_in_force, exit_reason, current_time, **kwargs
    )

  def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
    result = super().custom_exit(pair, trade, current_time, current_rate, current_profit, **kwargs)
    if result:
      return result
    age_days = (current_time - trade.open_date_utc).total_seconds() / 86400.0
    if age_days >= self.time_stop_days and current_profit <= 0.0:
      return f"exit_time_stop_{self.time_stop_days}d"
    return None

  @property
  def protections(self):
    return [
      {"method": "CooldownPeriod", "stop_duration_candles": 6},
      {
        "method": "MaxDrawdown",
        "lookback_period_candles": 288,
        "trade_limit": 10,
        "stop_duration_candles": 288,
        "max_allowed_drawdown": 0.10,
        "calculation_mode": "equity",
      },
      {
        "method": "StoplossGuard",
        "lookback_period_candles": 288,
        "trade_limit": 3,
        "stop_duration_candles": 144,
        "only_per_pair": True,
      },
    ]


class X8SafeSlip(X8SafeStopHonored):
  def custom_entry_price(self, pair, trade, current_time, proposed_rate, entry_tag, side, **kwargs) -> float:
    return slipped_first_entry(trade, proposed_rate, entry_tag)


class X8SafeNoDoom(X8SafeStopHonored):
  system_v4_stops_enable = False


class X8CommSlip(NostalgiaForInfinityX8):
  def custom_entry_price(self, pair, trade, current_time, proposed_rate, entry_tag, side, **kwargs) -> float:
    return slipped_first_entry(trade, proposed_rate, entry_tag)
