"""X7Safe with a modelled first-entry order, reports/ENTRY_POLICY_2026-11-04.md. Backtest only."""

import logging

from entry_model import decide
from X7SafeStopVariants import X7SafeStopHonored

log = logging.getLogger(__name__)
FALLBACK_GAP = 0.0051  # mean real gap, used only if 1m bars are missing


class X7SafeEntryChase(X7SafeStopHonored):
  limit_offset = None
  _decisions: dict = {}
  _counts = {"filled": 0, "skipped": 0, "nodata": 0}

  def _decision(self, pair, current_time):
    key = (pair, current_time)
    if key not in self._decisions:
      self._decisions[key] = decide(pair, current_time, self.limit_offset)
      kind = {"nodata": "nodata", None: "skipped"}.get(self._decisions[key], "filled") if isinstance(self._decisions[key], (str, type(None))) else "filled"
      self._counts[kind] += 1
      if kind == "nodata":
        log.warning(f"ENTRY-MODEL no 1m data {pair} {current_time}")
      if sum(self._counts.values()) % 200 == 0:
        log.info(f"ENTRY-MODEL {self._counts}")
    return self._decisions[key]

  def custom_entry_price(self, pair, trade, current_time, proposed_rate, entry_tag, side, **kwargs) -> float:
    if trade is not None:
      return proposed_rate
    d = self._decision(pair, current_time)
    if d == "nodata":
      return proposed_rate * (1.0 + FALLBACK_GAP)
    return proposed_rate if d is None else d

  def confirm_trade_entry(self, pair, order_type, amount, rate, time_in_force, current_time, entry_tag, side, **kwargs) -> bool:
    if self._decision(pair, current_time) is None:
      return False
    return super().confirm_trade_entry(pair, order_type, amount, rate, time_in_force, current_time, entry_tag, side, **kwargs)

  def bot_start(self, **kwargs) -> None:
    super().bot_start(**kwargs)
    type(self)._decisions = {}
    type(self)._counts = {"filled": 0, "skipped": 0, "nodata": 0}


class X7SafeEntryCap25(X7SafeEntryChase):
  limit_offset = 0.0025


class X7SafeEntryLimit0(X7SafeEntryChase):
  limit_offset = 0.0


class X7SafeEntryLimit25(X7SafeEntryChase):
  limit_offset = -0.0025


class X7SafeEntryLimit50(X7SafeEntryChase):
  limit_offset = -0.005
