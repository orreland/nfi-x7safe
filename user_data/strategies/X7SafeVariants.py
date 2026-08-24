"""
X7SafeVariants - one-lever-at-a-time drawdown experiments.

Each class below changes EXACTLY ONE knob versus NostalgiaForInfinityX7Safe so
the resulting backtest difference is attributable to that knob and nothing else.
Baseline for all of them (reports/SAFE_ONLY.md, real-universe run):
    return +144.96%, TRUE max drawdown 7.91%, Sharpe 3.29

Why these three: the drawdown anatomy showed the 7.91% is a "dull ache" -
a 79-day underwater stretch driven mostly by unrealized marks on open
positions, not by a handful of blowups (only 2 losing trades in the 45 days
before the trough, totalling -217 USDT). That points at three distinct levers:

  A. Shrink exposure outright          -> LowerStake  (15% -> 10% of equity)
  B. Shorten the underwater stretch    -> FastTimeStop (30d -> 14d)
  C. Actually cut losers               -> Derisk4     (enable -8%/sell-100%)

Run each against the same real universe (80 survivors + 40 delisted) used for
the baseline, via scripts/ft_delisted.py. Compare with
nfi_backtest_lib.compute_daily_metrics() - freqtrade's own max_drawdown is
realized-only and understates the thing we are trying to reduce.
"""

from NostalgiaForInfinityX7Safe import NostalgiaForInfinityX7Safe


class X7SafeLowerStake(NostalgiaForInfinityX7Safe):
  """Lever A: cut per-trade exposure from 15% to 10% of total equity.

  The most mechanical of the three - drawdown should shrink roughly in
  proportion to exposure, and so should return. The question this run answers
  is whether the ratio is actually linear, or whether smaller positions change
  behaviour (e.g. grind sub-entries falling under exchange minimums, which
  would make the reduction worse than proportional).

  The $4,500 cap is left alone: at 10% it only binds above $45,000 equity,
  which this 18-month run never reaches, so it stays a non-factor here.
  """

  stake_pct_of_equity = 0.10


class X7SafeFastTimeStop(NostalgiaForInfinityX7Safe):
  """Lever B: cut the time stop from 30 days to 14 days.

  Aimed directly at the measured failure mode: the worst drawdown was a 79-day
  underwater stretch. Cutting positions loose sooner should shorten it - but
  risks realizing losses on positions that would have recovered, so the return
  hit could exceed the drawdown benefit. That trade-off is exactly what this
  run measures.
  """

  time_stop_days = 14


class X7SafeDerisk4(NostalgiaForInfinityX7Safe):
  """Lever C: enable upstream's de-risk level 4 (-8% -> sell 100%).

  This is the only mechanism in the upstream codebase with true "cut the loss"
  semantics; upstream ships it disabled and X7Safe has kept it that way so far.
  Unlike the grind/de-risk ladder (which only trims), this fully exits.

  Expected to be the bluntest of the three: it should cap individual trade
  losses hard, but firing at -8% on a strategy whose whole edge is buying dips
  and grinding them back may convert a lot of eventual winners into realized
  losses.
  """

  system_v3_2_derisk_level_4_enable = True


# ============================================================================
# Round 2 variants (2026-08-23) - pre-registered in reports/SAFE_ONLY.md 待办1d
# ----------------------------------------------------------------------------
# Round 1 (LowerStake / FastTimeStop / Derisk4) found no risk-adjusted
# improvement and showed the whole 7.91% drawdown is ONE event: a same-day
# cluster of doom stops on delisted coins (BETA/VIDT/HARD) during the April
# 2025 selloff. These three directions target that finding directly.
#
# OVERFITTING WARNING: with a single dominant drawdown event in the sample,
# anything tuned to reduce max drawdown is being fit to that one event. The
# pass criteria in 待办1d (return/drawdown ratio, both-halves check, Sharpe
# floor) exist to make that hard to fool. Report the whole grid, not winners.
# ============================================================================


# --- Direction 1: the doom stop threshold itself ---------------------------
# Baseline X7Safe uses 0.08 (upstream ships 0.12). This is simultaneously the
# proximate cause of the drawdown AND the reason derisk_level_4 can never fire
# (freqtrade runs custom_exit before adjust_trade_position, so an equal-or-
# tighter doom threshold always wins the race).

class X7SafeDoom05(NostalgiaForInfinityX7Safe):
  """Tighter doom stop: give up at -5% of first-entry cost instead of -8%."""

  system_v3_2_stop_threshold_doom_spot = 0.05


class X7SafeDoom12(NostalgiaForInfinityX7Safe):
  """Upstream's own 0.12 - looser than X7Safe's 0.08.

  Also the first threshold at which derisk_level_4 (-0.08) could actually
  fire before the doom stop, so this run doubles as a test of that mechanism.
  """

  system_v3_2_stop_threshold_doom_spot = 0.12
  system_v3_2_derisk_level_4_enable = True


class X7SafeDoom20(NostalgiaForInfinityX7Safe):
  """Deliberately loose (0.20) - the control arm for direction 1.

  Included precisely because it is expected to be WORSE. A grid where only the
  favourable side is tested cannot distinguish signal from selection.
  """

  system_v3_2_stop_threshold_doom_spot = 0.20
  system_v3_2_derisk_level_4_enable = True


# --- Direction 2: delisting foreknowledge ----------------------------------
# Every coin that drove the drawdown was delisted later. This asks: if the
# blacklist were N days more timely, how much of that is recoverable?
#
# NOT DEPLOYABLE. It hard-codes each coin's actual last-candle date, which is
# look-ahead by construction. It measures an UPPER BOUND on what better
# blacklist hygiene could buy, to decide whether that ops work is worth doing.

_DELISTING_DATES = {
  "FTM/USDT": "2025-01-13", "LIT/USDT": "2025-02-10", "ERN/USDT": "2025-03-10",
  "BNX/USDT": "2025-03-18", "BURGER/USDT": "2025-03-28", "LINA/USDT": "2025-03-28",
  "BADGER/USDT": "2025-04-16", "BETA/USDT": "2025-04-16", "HARD/USDT": "2025-04-16",
  "VIDT/USDT": "2025-04-16", "ALPACA/USDT": "2025-05-02", "WING/USDT": "2025-05-02",
  "STPT/USDT": "2025-05-19", "EOS/USDT": "2025-05-26", "ALPHA/USDT": "2025-07-04",
  "KMD/USDT": "2025-07-04", "LTO/USDT": "2025-07-04", "MKR/USDT": "2025-09-15",
  "BAKE/USDT": "2025-09-17", "FLM/USDT": "2025-11-12", "PERP/USDT": "2025-11-12",
  "FIS/USDT": "2025-12-17", "FXS/USDT": "2026-01-13", "DATA/USDT": "2026-02-13",
  "DF/USDT": "2026-02-13", "NKN/USDT": "2026-02-13", "OM/USDT": "2026-03-02",
  "FORTH/USDT": "2026-04-01", "IDEX/USDT": "2026-04-01", "LRC/USDT": "2026-04-01",
  "SXP/USDT": "2026-04-01", "FUN/USDT": "2026-04-23", "MDT/USDT": "2026-04-23",
  "DEGO/USDT": "2026-04-28", "TRU/USDT": "2026-04-28", "FARM/USDT": "2026-05-27",
  "MLN/USDT": "2026-05-27", "HIGH/USDT": "2026-06-19", "MBOX/USDT": "2026-06-19",
  "POND/USDT": "2026-07-10",
}


class _ForeknowledgeMixin:
  """Refuse NEW entries within `foreknowledge_days` of a pair's delisting.

  Only blocks entries; positions already open still run their normal course,
  which matches what a blacklist update actually does in production.
  """

  foreknowledge_days = 0

  def confirm_trade_entry(self, pair, order_type, amount, rate, time_in_force, current_time, entry_tag, side, **kwargs):
    iso = _DELISTING_DATES.get(pair)
    if iso and self.foreknowledge_days:
      import pandas as pd

      cutoff = pd.Timestamp(iso, tz="UTC") - pd.Timedelta(days=self.foreknowledge_days)
      if pd.Timestamp(current_time) >= cutoff:
        return False
    return super().confirm_trade_entry(
      pair, order_type, amount, rate, time_in_force, current_time, entry_tag, side, **kwargs
    )


class X7SafeForeknow7(_ForeknowledgeMixin, NostalgiaForInfinityX7Safe):
  foreknowledge_days = 7


class X7SafeForeknow30(_ForeknowledgeMixin, NostalgiaForInfinityX7Safe):
  foreknowledge_days = 30


# --- Direction 3: account-level circuit breaker ----------------------------
# Baseline: MaxDrawdown over a 288-candle (24h) lookback, 10% threshold.
# The drawdown was a single-day cluster, so window/threshold shape may matter
# more than any per-trade stop.

class X7SafeBreakerTight(NostalgiaForInfinityX7Safe):
  """Same 24h window, but halve the trigger to 5%."""

  @property
  def protections(self):
    p = [dict(x) for x in super().protections]
    for item in p:
      if item.get("method") == "MaxDrawdown":
        item["max_allowed_drawdown"] = 0.05
    return p


class X7SafeBreakerLong(NostalgiaForInfinityX7Safe):
  """Week-long lookback at 12% - catches a slower bleed the 24h window misses."""

  @property
  def protections(self):
    p = [dict(x) for x in super().protections]
    for item in p:
      if item.get("method") == "MaxDrawdown":
        item["lookback_period_candles"] = 2016  # 7d at 5m
        item["max_allowed_drawdown"] = 0.12
        item["stop_duration_candles"] = 576  # 48h pause
    return p


class X7SafeBreakerLong15(NostalgiaForInfinityX7Safe):
  """Neighbourhood probe for X7SafeBreakerLong: same 7d window, 15% instead of 12%.

  Exists only to test whether the 7d/12% result is a knife-edge. If 12% helps
  and 15% does nothing (or hurts), the "improvement" is likely fitted to the
  one drawdown event rather than a real property of the longer window.
  """

  @property
  def protections(self):
    p = [dict(x) for x in super().protections]
    for item in p:
      if item.get("method") == "MaxDrawdown":
        item["lookback_period_candles"] = 2016
        item["max_allowed_drawdown"] = 0.15
        item["stop_duration_candles"] = 576
    return p
