"""
NostalgiaForInfinityX7Safe
---------------------------
A risk-capped subclass of the official NostalgiaForInfinityX7 strategy.

REVISION 2026-08-22 -- see reports/FINAL_REPORT.md "附录 2".
  The previous revision of this file tightened `system_v3_2_stop_threshold_doom_spot`
  but never set `system_v3_2_stops_enable = True`. Since `system_name_use` is
  `system_v3_2_name`, EVERY trade runs the v3_2 branch of `long_exit_stoploss`,
  which reads:

      if is_system_v3_2:
          if self.system_v3_2_stops_enable and (profit_stake < -(entry_cost * thr)):
              return True, stoploss_doom

  and upstream ships `system_v3_2_stops_enable = False` (X7.py:583). The whole
  condition was short-circuited by `and False`, so the tightened threshold never
  participated in a single decision. The 18-month comparison run that reported
  "0 triggers" was therefore not evidence that the market never tested the stop -
  the stop was not wired up. That is fixed below.

  Three other overrides in the previous revision (`grinding_v1_max_stake`,
  `grinding_v2_max_stake`, `system_v3_1_max_stake`) also landed on dead branches:
  under system_v3_2 only `system_v3_max_stake` is read (X7.py:47269). They have
  been removed rather than left in place, because a parameter that looks like a
  risk control but is never read is worse than no parameter at all.

What upstream actually does (verified by reading the dispatch chain, not the
parameter block):
  - There is NO hard stop in the default config: stoploss=-0.99,
    use_custom_stoploss=False, trailing_stop=False, system_v3_2_stops_enable=False,
    u_e_stops_enable=False.
  - Grinding is NOT a martingale. `system_v3_max_stake = 1.0` caps a position's
    market value at the cost of its FIRST entry, so a single trade cannot eat the
    account. Measured: COTI/USDT ran 745 orders over 537 days and peaked at
    ~1,912 USDT against a 1,582 USDT first entry (1.2x).
  - The real, measured failure mode is SLOT ZOMBIFICATION: 3 trades consumed
    1,029.5 of 1,151 slot-days (89%) across the 18-month run, two of them ending
    at a loss after occupying a slot for 537 and 382 days respectively.

This subclass does not touch entry/exit signal logic. It only (a) wires up the
stop that upstream leaves disabled, (b) tightens the numeric risk knobs that are
actually read, and (c) adds one new control aimed at the failure mode the data
actually showed. Upstream NostalgiaForInfinityX7.py stays untouched so `git pull`
keeps working; point freqtrade here via --strategy NostalgiaForInfinityX7Safe.
"""

import logging
from collections import Counter
from datetime import datetime, timedelta

from freqtrade.enums import RunMode
from freqtrade.persistence import Trade

from NostalgiaForInfinityX7 import NostalgiaForInfinityX7

log = logging.getLogger(__name__)


class NostalgiaForInfinityX7Safe(NostalgiaForInfinityX7):
  # ==========================================================================
  # 1. Hard per-trade floor (freqtrade level)
  # ==========================================================================
  # Upstream default is -0.99 (effectively disabled). This is freqtrade's own
  # stoploss and always wins regardless of what the strategy's own logic decides.
  #
  # NOTE ON WHY THIS RARELY FIRES: freqtrade measures this against the trade's
  # *average* open rate, and grinding continuously averages down. A position can
  # be deeply underwater versus its first entry while sitting within 15% of its
  # average. This is a genuine worst-case floor, not a working stop - the doom
  # stop below is the one expected to do the work.
  stoploss = -0.15

  # ==========================================================================
  # 2. Doom stop -- THE FIX
  # ==========================================================================
  # `system_v3_2_stops_enable` is the master switch for the only stop that runs
  # under the active system version. Upstream = False. Without this line every
  # threshold below is dead code.
  system_v3_2_stops_enable = True

  # Thresholds are expressed as a ratio of the FIRST entry's cost. Upstream v3_2
  # ships 0.12; 0.08 gives up on an invalidated setup sooner.
  # The other three are kept only so that a future change of `system_name_use`
  # does not silently fall back to upstream's looser numbers.
  system_v3_2_stop_threshold_doom_spot = 0.08
  system_v3_2_stop_threshold_doom_futures = 0.24
  system_v3_stop_threshold_doom_spot = 0.08
  system_v3_1_stop_threshold_doom_spot = 0.10
  stop_threshold_doom_spot = 0.08

  # ==========================================================================
  # 3. Grind budget
  # ==========================================================================
  # Under system_v3_2 this is the ONLY max-stake constant that is read
  # (X7.py:47269: current_stake_amount < slice_amount * system_v3_max_stake).
  # Upstream 1.0 = a position may grow to the cost of its first entry.
  # 0.5 halves the grinding budget: less averaging-down, faster resolution,
  # at the cost of fewer grind cycles to harvest.
  system_v3_max_stake = 0.5

  # ==========================================================================
  # 4. Time stop -- NEW, targets the measured failure mode
  # ==========================================================================
  # Upstream has no notion of trade age. A position that never recovers holds its
  # slot forever; the backtest only surfaces this at force_exit, where it looks
  # like a tiny loss (COTI: -0.36%) rather than 537 days of dead capacity.
  #
  # This is deliberately aimed at what the data showed, not at a hypothetical
  # crash: cut a position loose once it has held a slot for `time_stop_days`
  # without getting back to break-even.
  time_stop_enable = True
  time_stop_days = 30
  # Only fire when the trade is actually underwater. A trade that is up but has
  # not yet met its exit signal is not a zombie - let the strategy work it.
  time_stop_max_profit_ratio = 0.0

  # ==========================================================================
  # 5. De-risk level 4 (off by default -- A/B candidate)
  # ==========================================================================
  # Upstream defines a -8% / sell-100% level and ships it disabled. It is the
  # only mechanism in the codebase with true "cut the loss" semantics. Left off
  # here so this run isolates the effect of the doom stop + time stop; flip to
  # True for the A/B run.
  system_v3_2_derisk_level_4_enable = False

  # ==========================================================================
  # 6. Trailing stop -- intentionally left as upstream (disabled)
  # ==========================================================================
  # NFI's exit logic is tag-driven, with per-mode take-profit ladders tuned
  # against this indicator set. Overlaying a generic trailing stop risks cutting
  # winners before the strategy's own exit fires, and was never validated
  # against this entry logic.

  # ==========================================================================
  # 8. Position sizing -- percent-of-equity with an absolute cap (2026-08-22)
  # ==========================================================================
  # configs/local-overrides-safe.json sets a FIXED stake_amount=1500, which is
  # only 15% of equity because it was sized against dry_run_wallet=10000 - the
  # backtest starting balance, not any particular real account. A fixed dollar
  # figure means the fraction of the account any one slot risks depends
  # entirely on how much money happens to be in the account: fine at $10,000,
  # nearly the whole account at $2,000, and negligible at $50,000.
  #
  # This makes the first entry a fraction of CURRENT total equity instead,
  # bounded by an absolute cap so it stops growing once the account is well
  # past the size this was tuned for:
  #
  #   first_entry = min(total_equity * stake_pct_of_equity, stake_pct_cap)
  #
  # stake_pct_of_equity = 0.15 reproduces the current $1,500 sizing exactly at
  # $10,000 equity, so nothing about the already-validated backtests changes
  # at that account size - only accounts smaller or larger than $10,000 see
  # different behavior. stake_pct_cap = 4,500 (3x the current fixed stake)
  # means the percent scheme tracks equity 1:1 up to ~$30,000, then flattens -
  # both numbers are business decisions about how large an account this
  # should ever bet 15% of, not something derived from the backtest data, and
  # should be revisited if the real account size differs a lot from these
  # assumptions.
  #
  # total_equity here is cash + value tied up in open trades (freqtrade's own
  # notion of account size for sizing purposes), NOT the mark-to-market
  # (unrealized P&L included) equity this project's daily_return_total_pct
  # metric uses elsewhere - computing that would need current market prices
  # for every open pair, which this callback doesn't have cheap access to.
  # The difference only matters while trades are open and away from their
  # entry price; it does not change which of the two sizing modes is active.
  #
  # Set stake_sizing_mode = "fixed" to fall back to configs/local-overrides-safe.json's
  # stake_amount unchanged (the previously-validated behavior), for A/B backtests.
  stake_sizing_mode = "percent"  # "percent" or "fixed"
  stake_pct_of_equity = 0.15
  stake_pct_cap = 4500.0

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
    if self.stake_sizing_mode == "percent":
      total_equity = Trade.total_open_trades_stakes() + self.wallets.get_free(self.config["stake_currency"])
      proposed_stake = min(total_equity * self.stake_pct_of_equity, self.stake_pct_cap)
    # Delegate to upstream with our own base size in place of freqtrade's
    # config-driven proposed_stake - upstream's per-mode multipliers (rebuy
    # 0.25x, rapid 0.75x, the grind ladder, ...) then scale THIS number
    # instead of the fixed-stake_amount-derived one.
    return super().custom_stake_amount(
      pair, current_time, current_rate, proposed_stake, min_stake, max_stake, leverage, entry_tag, side, **kwargs
    )

  # --- instrumentation ------------------------------------------------------
  # Counts how often each added control actually fires. A risk control that
  # never triggers has not been validated, it has merely been installed.
  #
  # Two layers (2026-10-17):
  #  - SAFE-TRIGGER [...] lines: one per decision, from an in-memory counter.
  #    That counter starts at 0 on every process start, so with the weekly
  #    controlled restart its "#n" is only "n-th since the last restart".
  #  - SAFE-TRIGGER-SUMMARY: in dry-run/live, recomputed from the trades table
  #    (closed trades by exit_reason) at startup and then hourly. It survives
  #    restarts and also covers exits the strategy never sees as a decision -
  #    exchange-side stop fills (stoploss_on_exchange) and emergency_exit -
  #    which the in-memory counter missed entirely. In backtesting it keeps
  #    printing the in-memory counter, throttled to once per candle-hour.
  _safe_trigger_counts: dict = {}
  _safe_summary_every = timedelta(hours=1)
  _safe_summary_last = None

  def _record_trigger(self, name: str, pair: str, current_time, detail: str = "") -> None:
    counts = type(self)._safe_trigger_counts
    counts[name] = counts.get(name, 0) + 1
    log.info(f"SAFE-TRIGGER [{name}] #{counts[name]} since start [{current_time}] [{pair}] {detail}")

  @staticmethod
  def _classify_exit(exit_reason) -> str | None:
    """Map a closed trade's exit_reason to the safety control that closed it."""
    reason = str(exit_reason or "")
    if "stoploss_doom" in reason:
      return "doom_stop"
    if reason.startswith("exit_time_stop"):
      return "time_stop"
    if reason in ("stop_loss", "trailing_stop_loss"):
      return "hard_stop_honored"  # passed confirm_trade_exit (section 9)
    if reason == "stoploss_on_exchange":
      return "hard_stop_exchange"  # filled on the exchange, never seen by the strategy
    if reason == "emergency_exit":
      return "emergency_exit"
    return None

  def _db_trigger_counts(self) -> dict:
    counts = Counter()
    for trade in Trade.get_trades_proxy(is_open=False):
      kind = self._classify_exit(trade.exit_reason)
      if kind:
        counts[kind] += 1
    return dict(sorted(counts.items()))

  # ==========================================================================
  # 9. Exchange-side stoploss handoff
  # ==========================================================================
  # Upstream confirm_trade_exit() (X7.py:12680) unconditionally denies any
  # exit_reason in ("stop_loss", "trailing_stop_loss") unless it is a
  # liquidation - by design, upstream wants only its own tag-driven exit
  # signals to fire, never freqtrade's blunt percentage stop.
  #
  # This deployment also runs stoploss_on_exchange=True
  # (configs/local-overrides-dryrun.json), specifically to validate "does the
  # exchange actually accept and execute this stop order" before risking real
  # money. Combined with the blanket denial above, that validation was
  # silently failing: freqtrade tries to (re)place the exchange-side stop
  # every process_throttle_secs, gets denied each time by confirm_trade_exit,
  # and by the time price has run far enough that a *new* stop order would
  # trigger immediately, dry-run can't place it and force-exits at market
  # (exit_reason=emergency_exit) - at a worse price than the configured stop
  # would have given. Confirmed 100% (4/4 emergency_exit trades, 17 "User
  # denied exit" log lines) against QI/USDT x2, TFUEL/USDT, VTHO/USDT, 2026-09.
  #
  # Fix: once stoploss_on_exchange is enabled, the exchange - not this bot's
  # 5-second polling loop - is the authority on whether the stop actually
  # fired, so trust it and let the exit through instead of re-litigating it
  # every loop only to force a worse exit later.
  def confirm_trade_exit(
    self,
    pair: str,
    trade: "Trade",
    order_type: str,
    amount: float,
    rate: float,
    time_in_force: str,
    exit_reason: str,
    current_time: "datetime",
    **kwargs,
  ) -> bool:
    if exit_reason in ("stop_loss", "trailing_stop_loss") and self.order_types.get("stoploss_on_exchange"):
      self._record_trigger("exchange_stoploss_honored", pair, current_time, f"reason={exit_reason}")
      return True
    return super().confirm_trade_exit(
      pair, trade, order_type, amount, rate, time_in_force, exit_reason, current_time, **kwargs
    )

  def custom_exit(
    self, pair: str, trade: "Trade", current_time: "datetime", current_rate: float, current_profit: float, **kwargs
  ):
    # Let the upstream logic decide first: its exit reasons are more informative,
    # and it owns side effects (the target_profit_cache) that must keep running.
    result = super().custom_exit(pair, trade, current_time, current_rate, current_profit, **kwargs)
    if result:
      if "stoploss_doom" in str(result):
        self._record_trigger("doom_stop", pair, current_time, f"profit={current_profit * 100.0:.2f}%")
      return result

    # Time stop: free the slot once a position has held it too long underwater.
    if self.time_stop_enable:
      open_date = trade.open_date_utc
      if open_date is not None:
        age_days = (current_time - open_date).total_seconds() / 86400.0
        if age_days >= self.time_stop_days and current_profit <= self.time_stop_max_profit_ratio:
          self._record_trigger(
            "time_stop", pair, current_time, f"age={age_days:.1f}d profit={current_profit * 100.0:.2f}%"
          )
          return f"exit_time_stop_{self.time_stop_days}d"

    return None

  def bot_loop_start(self, current_time: datetime, **kwargs) -> None:
    super().bot_loop_start(current_time, **kwargs)
    last = type(self)._safe_summary_last
    if last is not None and current_time - last < self._safe_summary_every:
      return
    type(self)._safe_summary_last = current_time
    if self.dp.runmode in (RunMode.DRY_RUN, RunMode.LIVE):
      try:
        log.info(f"SAFE-TRIGGER-SUMMARY (all closed trades, from DB) {self._db_trigger_counts()}")
      except Exception as e:  # instrumentation must never stop the bot
        log.warning(f"SAFE-TRIGGER-SUMMARY unavailable: {e}")
    else:
      counts = type(self)._safe_trigger_counts
      if counts:
        log.info(f"SAFE-TRIGGER-SUMMARY (decisions this run) {counts}")

  # ==========================================================================
  # 7. Bot-level circuit breakers (freqtrade Protections)
  # ==========================================================================
  # These act independently of any strategy signal - they pause trading after
  # the account has already shown distress. Only active in backtesting with
  # --enable-protections; always active in dry-run/live.
  @property
  def protections(self):
    return [
      {
        "method": "CooldownPeriod",
        "stop_duration_candles": 6,  # 30 min at 5m timeframe
      },
      {
        "method": "MaxDrawdown",
        "lookback_period_candles": 288,  # 24h at 5m timeframe
        "trade_limit": 10,
        "stop_duration_candles": 288,  # pause all new entries for 24h
        "max_allowed_drawdown": 0.10,  # account drawdown over the lookback
        # 2026-10-18: without this, freqtrade defaults to "ratios" - the
        # drawdown of the SUM of per-trade profit ratios, regardless of size -
        # which fired 4 times in the 18-month backtest while the account was
        # down < 1% each time. "equity" measures realized USDT P&L against the
        # account, which is what the line above says. See
        # reports/REBUY_AB_PARITY_2026-10-17.md sections 19/20.
        "calculation_mode": "equity",
      },
      {
        "method": "StoplossGuard",
        "lookback_period_candles": 288,
        "trade_limit": 3,
        "stop_duration_candles": 144,  # 12h pause on a pair after 3 stoplosses/24h
        "only_per_pair": True,
      },
    ]
