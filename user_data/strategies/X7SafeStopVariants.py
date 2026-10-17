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
