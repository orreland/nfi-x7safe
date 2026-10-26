"""
X7SafeStopVariants - hard-stop / rebuy-mode experiments (2026-10-13).

WHY THIS FILE EXISTS
--------------------
Six weeks of dry-run (2026-08-30 .. 2026-10-12) lost -5.2% while the 18-month
backtest of the same strategy reported +145%. Eight trades account for 56% of
the dry-run's gross loss, all of them rebuy-mode entries (tags 64/65) closed
by freqtrade's own `stoploss = -0.15` (exit_reason stoploss_on_exchange /
emergency_exit).

The backtest never contained that exit. Upstream confirm_trade_exit()
(X7.py:12680) denies every exit_reason in ("stop_loss", "trailing_stop_loss"),
and backtesting honours the denial: the baseline run (survB-safe-percent) has
0 stop_loss exits across 436 trades, although 20 of its 166 rebuy trades
traded more than 15% below their first entry. Dry-run differs because
stoploss_on_exchange=True puts a real stop order on the (simulated) exchange,
which fills without asking the strategy. So `stoploss = -0.15` was dead code
in every backtest and is live code on the server.

Rebuy mode's own doom stop (`system_v3_2_stop_threshold_spot_rebuy`, 0.48 of
first-entry cost) was never overridden by X7Safe, so in dry-run the -15% hard
stop is the only stop a rebuy trade ever meets.

Each class below changes one thing so the difference is attributable. Run them
over the same window, universe and config chain as survB-safe-percent, which
stays the "stop denied" reference.
"""

from datetime import datetime

from freqtrade.persistence import Trade
from freqtrade.strategy import stoploss_from_absolute

from NostalgiaForInfinityX7Safe import NostalgiaForInfinityX7Safe


class X7SafeStopHonored(NostalgiaForInfinityX7Safe):
  """What the server actually does today: the -15% hard stop executes.

  The server's X7Safe gates this on order_types["stoploss_on_exchange"], which
  is False in the backtest config chain, so copying the server file would
  change nothing here. Backtesting has no exchange-side stop to imitate, so
  the stop is let through unconditionally instead.
  """

  def confirm_trade_exit(
    self,
    pair: str,
    trade: Trade,
    order_type: str,
    amount: float,
    rate: float,
    time_in_force: str,
    exit_reason: str,
    current_time: datetime,
    **kwargs,
  ) -> bool:
    if exit_reason in ("stop_loss", "trailing_stop_loss"):
      self._record_trigger("hard_stop", pair, current_time, f"reason={exit_reason}")
      return True
    return super().confirm_trade_exit(
      pair, trade, order_type, amount, rate, time_in_force, exit_reason, current_time, **kwargs
    )


def _without_rebuy_entries(params: dict, tags=("61", "62", "63", "64", "65", "68")) -> dict:
  out = dict(params)
  for tag in tags:
    out[f"long_entry_condition_{tag}_enable"] = False
  return out


class X7SafeStopHonoredNoRebuy(X7SafeStopHonored):
  """Option 2: hard stop executes, rebuy-mode entries (61-65, 68) switched off."""

  long_entry_signal_params = _without_rebuy_entries(NostalgiaForInfinityX7Safe.long_entry_signal_params)


class X7SafeStopHonoredNo6465(X7SafeStopHonored):
  """Option 2b: hard stop executes, only rebuy tags 64/65 switched off.

  Dry-run 2026-08-30 .. 2026-10-17: 36 of 61 trades were 64/65 (PF 0.36,
  -473 USDT); 61-63 had 2 trades, both wins. This arm separates "64/65 are
  bad" from "rebuy mode as a whole is bad".
  """

  long_entry_signal_params = _without_rebuy_entries(
    NostalgiaForInfinityX7Safe.long_entry_signal_params, tags=("64", "65")
  )


class X7SafeStop12(X7SafeStopHonored):
  """Option 3: hard stop executes, tightened from -15% to -12%."""

  stoploss = -0.12


class X7SafeStop25(X7SafeStopHonored):
  """Control arm: hard stop executes but loosened to -25%.

  Rebuy mode adds at -8/-12/-16/-20% (system_v3_rebuy_mode_thresholds_spot); a
  -15% stop cuts the ladder after two of four steps, -25% lets it finish.
  Included because the tight side alone cannot tell signal from selection.
  """

  stoploss = -0.25


class X7SafeNoRebuy(NostalgiaForInfinityX7Safe):
  """Isolates rebuy mode's contribution when the hard stop is denied (as in
  every earlier backtest): baseline minus rebuy entries, nothing else."""

  long_entry_signal_params = _without_rebuy_entries(NostalgiaForInfinityX7Safe.long_entry_signal_params)


# ---------------------------------------------------------------------------
# Rebuy-specific stop experiments (pre-registered 2026-10-17, see
# reports/REBUY_AB_PARITY_2026-10-17.md section 12).
#
# The "-15% hard stop" is anchored at the FIRST entry price: freqtrade sets the
# static stop once at open, and after a DCA fill recalc_trade_from_orders()
# only lets it walk up, so a lower average never lowers it. Under -15% the
# rebuy ladder (-8/-12/-16/-20% from the previous entry) gets exactly one add
# before the stop at 0.85 x first price, and rebuy's own doom stop (0.48 x first
# slice cost) can never fire first (max loss ~0.23 x slice).
# ---------------------------------------------------------------------------


def _is_rebuy_trade(strategy, trade: Trade) -> bool:
  """Same test as X7's is_rebuy_mode in the long exit / adjust paths."""
  enter_tags = (trade.enter_tag or "").split()
  rebuy_tags = strategy.long_rebuy_mode_tags
  return bool(enter_tags) and (
    all(c in rebuy_tags for c in enter_tags)
    or (any(c in rebuy_tags for c in enter_tags) and all(c in strategy.long_rebuy_grind_mode_tags for c in enter_tags))
  )


class _FirstEntryHardStop(X7SafeStopHonored):
  """Per-side hard stop anchored at the first entry price: rebuy trades at
  (1 - rebuy_hard_stop) x first price, all others at (1 - other_hard_stop).
  Not run directly; the subclasses below set the two distances.

  A side whose distance equals the static `stoploss` (0.15) must not be
  touched at all: any custom_stoploss move also rewrites trade.stop_loss_pct,
  which recalc_trade_from_orders() reuses after a DCA fill, so even "returning
  the same price" changes where a grinding trade's stop walks to (a first
  version of X7SafeRebuyStop25 did exactly that to 16 of ~300 non-rebuy
  trades). So custom_stoploss returns None for everything except one call:
  the after_fill call for a widened side's FIRST entry. There current_rate is
  the fill price itself, so the refresh (allow_refresh=True, the only way to
  move a stop down) lands on exactly (1 - distance) x first price with
  stop_loss_pct = distance; later recalcs only walk it up when the average
  rises above the first price - the same "anchored at first entry, only walks
  up" semantics as the static -15% stop, just wider.
  """

  use_custom_stoploss = True
  rebuy_hard_stop = 0.15
  other_hard_stop = 0.15

  def custom_stoploss(
    self,
    pair: str,
    trade: Trade,
    current_time: datetime,
    current_rate: float,
    current_profit: float,
    after_fill: bool,
    **kwargs,
  ):
    if not after_fill or trade.nr_of_successful_entries != 1 or trade.nr_of_successful_exits != 0:
      return None
    distance = self.rebuy_hard_stop if _is_rebuy_trade(self, trade) else self.other_hard_stop
    if distance == -self.stoploss:
      return None
    first_price = trade.select_filled_orders(trade.entry_side)[0].safe_price
    stop = stoploss_from_absolute(
      first_price * (1.0 - distance), current_rate, is_short=trade.is_short, leverage=trade.leverage
    )
    return stop or None


class X7SafeRebuyStop25(_FirstEntryHardStop):
  """A1: rebuy trades get a hard stop at 0.75 x first entry price, every other
  trade keeps the static -15% stop exactly as in X7SafeStopHonored."""

  rebuy_hard_stop = 0.25


class X7SafeRebuyDoom10(X7SafeStopHonored):
  """B10: hard stop unchanged, rebuy doom tightened 0.48 -> 0.10 x first slice
  cost (~0.91 x first price once the first add has filled)."""

  system_v3_2_stop_threshold_spot_rebuy = 0.10


class X7SafeRebuyDoom15(X7SafeStopHonored):
  """B15: rebuy doom 0.15 x first slice cost (~0.89 x first price with 2 slices)."""

  system_v3_2_stop_threshold_spot_rebuy = 0.15


class X7SafeRebuyDoom20(X7SafeStopHonored):
  """B20: rebuy doom 0.20 x first slice cost (~0.86 x first price with 2 slices,
  just above the 0.85 hard stop)."""

  system_v3_2_stop_threshold_spot_rebuy = 0.20


# ---------------------------------------------------------------------------
# Non-rebuy hard-stop experiments (pre-registered 2026-10-17, report section 14).
# In W1 the -15% hard stop cut 14 non-rebuy trades for -2331 USDT; with the stop
# denied those grind positions recovered. Rebuy keeps -15% in all three; the
# non-rebuy side still has the 8% doom stop and the 30-day time stop.
# ---------------------------------------------------------------------------


class X7SafeOtherStop20(_FirstEntryHardStop):
  """N20: non-rebuy hard stop at 0.80 x first entry price, rebuy unchanged."""

  other_hard_stop = 0.20


class X7SafeOtherStop25(_FirstEntryHardStop):
  """N25: non-rebuy hard stop at 0.75 x first entry price, rebuy unchanged."""

  other_hard_stop = 0.25


class X7SafeOtherNoStop(_FirstEntryHardStop):
  """N0: non-rebuy hard stop effectively removed (0.01 x first entry price);
  only the doom stop and the time stop remain. Rebuy unchanged."""

  other_hard_stop = 0.99


# ---------------------------------------------------------------------------
# MaxDrawdown calculation mode (pre-registered 2026-10-18, report section 19).
# X7Safe's MaxDrawdown says "account drawdown over the lookback" but sets no
# calculation_mode, so freqtrade uses its default "ratios": it sums per-trade
# profit ratios and takes the drawdown of that sum, regardless of position
# size. "equity" measures realized P&L in USDT against starting balance plus
# profit realized before the window - an actual account drawdown.
# ---------------------------------------------------------------------------


class _MaxDrawdownEquity(X7SafeStopHonored):
  """Baseline with only the MaxDrawdown protection switched to equity mode."""

  max_drawdown_equity_threshold = 0.10

  @property
  def protections(self):
    prots = [dict(p) for p in super().protections]
    for p in prots:
      if p["method"] == "MaxDrawdown":
        p["calculation_mode"] = "equity"
        p["max_allowed_drawdown"] = self.max_drawdown_equity_threshold
    return prots


class X7SafeDDEquity10(_MaxDrawdownEquity):
  """E10: MaxDrawdown measured on account equity, threshold unchanged (10%)."""

  max_drawdown_equity_threshold = 0.10


class X7SafeDDEquity5(_MaxDrawdownEquity):
  """E5: MaxDrawdown measured on account equity, threshold 5%."""

  max_drawdown_equity_threshold = 0.05


# ---------------------------------------------------------------------------
# Rebuy on the N25 + E10 base (pre-registered 2026-10-25, report section 22).
# X7SafeStopHonored now inherits N25 + E10 from NostalgiaForInfinityX7Safe.
# ---------------------------------------------------------------------------


class X7SafeRebuyHalf(X7SafeStopHonored):
  """RH: rebuy first entry 0.25 -> 0.125 x a normal stake; adds are sized off
  the first entry, so the whole rebuy position halves."""

  system_v3_rebuy_mode_stake_multiplier = 0.125


class X7SafeBothStop25(X7SafeStopHonored):
  """R25: rebuy hard stop also at 0.75 x first entry (non-rebuy already is)."""

  rebuy_hard_stop = 0.25


class X7SafeN25NoRebuy(X7SafeStopHonored):
  """NR (report section 24): N25 + E10 base with rebuy entries 61-65 switched
  off (68 is already off upstream). Exit / adjust logic untouched."""

  long_entry_signal_params = _without_rebuy_entries(
    NostalgiaForInfinityX7Safe.long_entry_signal_params, tags=("61", "62", "63", "64", "65")
  )
