"""Shared helpers for the NFI backtesting scripts in this project.

Wraps `freqtrade backtesting` as a subprocess call using the same config-file
chain NostalgiaForInfinity's own CI uses (configs/exampleconfig*.json +
configs/trading_mode-spot.json + configs/blacklist-binance.json +
configs/pairlist-backtest-static-binance-spot-usdt.json), parses the exported
result JSON, and extracts a compact metrics dict (return, drawdown, Sharpe,
Sortino, Calmar, win rate, profit factor, ...).

Also defines the four OOS "failure criteria" used by run_walk_forward.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import zipfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
USER_DATA = ROOT / "user_data"
CONFIGS = ROOT / "configs"
REPORTS = ROOT / "reports"
PYPATCHES = ROOT / "pypatches"

# 2026-08-22: switched the project default from the upstream strategy to our
# risk-capped subclass. See reports/SAFE_ONLY.md for why: the
# upstream stoploss is fully disabled by default (X7.py: stoploss=-0.99,
# system_v3_2_stops_enable=False, u_e_stops_enable=False), and a survivorship
# experiment (reports/comparison-all-runs.md) showed upstream's headline
# return depends on the blacklist excluding coins that later delisted - when
# tested against the pair universe as it looked at the START of the window
# (survivors + delisted), upstream's return went from +191% to -4.4% and its
# drawdown blew through NFI's own 15% CI bar. NostalgiaForInfinityX7Safe wires
# up the doom stop upstream ships disabled and adds a 30-day time stop aimed
# at the slot-zombification failure mode that was actually measured.
#
# Pass --strategy=NostalgiaForInfinityX7 explicitly if you need the upstream
# strategy for comparison/archival purposes.
STRATEGY = "NostalgiaForInfinityX7Safe"
UPSTREAM_STRATEGY = "NostalgiaForInfinityX7"  # kept only for reference/comparison runs

# Same config chain as NFI's own tests/backtests/helpers.py (Backtest.__call__),
# adapted to this project's directory layout.
DEFAULT_CONFIGS = [
    CONFIGS / "exampleconfig.json",
    CONFIGS / "exampleconfig_secret.json",
    CONFIGS / "trading_mode-spot.json",
    CONFIGS / "blacklist-binance.json",
    CONFIGS / "pairlist-backtest-static-binance-spot-usdt.json",
]

# NFI's own CI acceptance bar (tests/backtests/test_winrate_and_drawdown.py):
# winrate >= 85%, max_drawdown <= 15% per monthly window (0 trades = pass).
# We reuse the same bar for our 45-day OOS windows, plus two extra checks of
# our own (net non-negative return, non-negative risk-adjusted return) - see
# check_failure_criteria() below and the final report for the rationale.
OFFICIAL_MIN_WINRATE_PCT = 85.0
OFFICIAL_MAX_DRAWDOWN_PCT = 15.0


class BacktestError(RuntimeError):
    pass


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    existing_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(PYPATCHES) + (os.pathsep + existing_path if existing_path else "")
    return env


@dataclass
class BacktestMetrics:
    start_date: str
    end_date: str
    trades: int = 0
    wins: int = 0
    losses: int = 0
    winrate_pct: float = 0.0
    profit_total_pct: float = 0.0
    profit_mean_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_abs: float = 0.0
    sharpe: Optional[float] = None
    sortino: Optional[float] = None
    calmar: Optional[float] = None
    cagr: Optional[float] = None
    profit_factor: Optional[float] = None
    expectancy: Optional[float] = None
    market_change_pct: Optional[float] = None
    result_json_path: Optional[str] = None

    # --- mark-to-market daily metrics (added 2026-08-22) ---------------------
    # freqtrade's sharpe/sortino/max_drawdown above are computed over the
    # PER-TRADE profit_ratio series, which distorts them two ways for this
    # strategy: (a) grinding trades accumulate max_stake_amount across hundreds
    # of orders, so their profit_ratio denominator is inflated (COTI: -284 USDT
    # recorded as -0.36%), and (b) unrealized losses on open positions never
    # touch the curve. These fields recompute the same quantities from the
    # daily mark-to-market equity curve in *_wallet.feather instead.
    daily_sharpe: Optional[float] = None
    daily_sortino: Optional[float] = None
    daily_max_drawdown_pct: Optional[float] = None
    daily_max_drawdown_abs: Optional[float] = None
    daily_ann_volatility_pct: Optional[float] = None
    daily_return_total_pct: Optional[float] = None
    days_in_drawdown_gt_1pct: Optional[int] = None

    # --- capital-occupancy metrics ------------------------------------------
    # The measured failure mode of this strategy is slot zombification, which
    # none of the standard metrics surface.
    slot_utilization_pct: Optional[float] = None
    slot_days_used: Optional[float] = None
    slot_days_capacity: Optional[float] = None
    longest_trade_days: Optional[float] = None
    slot_days_top3_share_pct: Optional[float] = None

    raw: dict = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "raw"}
        return d


def run_backtest(
    start: str,
    end: str,
    tag: str,
    strategy: str = STRATEGY,
    extra_configs: Optional[list[Path]] = None,
    breakdown: str = "day",
    export_dir: Optional[Path] = None,
    timeout: int = 14400,
    enable_protections: Optional[bool] = None,
) -> BacktestMetrics:
    """Run one `freqtrade backtesting` pass for [start, end) (YYYYMMDD) and
    return parsed summary metrics. Raises BacktestError on failure."""

    # --export-filename is deprecated in this freqtrade version (custom
    # filenames are no longer supported); freqtrade auto-names the result
    # file inside --export-directory instead, so we give each run its own
    # directory and then pick out the file it just wrote.
    base_export_dir = export_dir or (USER_DATA / "backtest_results")
    run_export_dir = base_export_dir / tag
    run_export_dir.mkdir(parents=True, exist_ok=True)

    resolved_extra = list(extra_configs or [])
    if strategy == STRATEGY:
        safe_overrides = CONFIGS / "local-overrides-safe.json"
        if safe_overrides not in resolved_extra:
            resolved_extra.append(safe_overrides)
        if enable_protections is None:
            # The doom stop / time stop only matter with the account-level
            # circuit breakers also active; Safe's own `protections` list is
            # otherwise ignored by freqtrade during backtesting. Callers can
            # still pass enable_protections=False explicitly to opt out.
            enable_protections = True
    extra_configs = resolved_extra
    enable_protections = bool(enable_protections)

    cmd = [
        str(VENV_PY), "-m", "freqtrade", "backtesting",
        f"--strategy={strategy}",
        f"--timerange={start}-{end}",
        f"--user-data-dir={USER_DATA}",
    ]
    for cfg in DEFAULT_CONFIGS:
        cmd.append(f"--config={cfg}")
    for cfg in extra_configs or []:
        cmd.append(f"--config={cfg}")
    cmd += [
        "--breakdown", breakdown,
        "--export", "trades",
        f"--export-directory={run_export_dir}",
        f"--log-file={USER_DATA / 'logs' / f'backtest-{tag}.log'}",
    ]
    if enable_protections:
        cmd.append("--enable-protections")

    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise BacktestError(
            f"backtest failed (exit {proc.returncode}) for {tag} [{start}-{end}]\n"
            f"cmd: {' '.join(cmd)}\n--- stdout (tail) ---\n{proc.stdout[-4000:]}\n"
            f"--- stderr (tail) ---\n{proc.stderr[-4000:]}"
        )

    json_file = _resolve_result_file(run_export_dir)
    data = json.loads(json_file.read_text(encoding="utf-8"))
    return _parse_metrics(data, start, end, str(json_file))


def _resolve_result_file(run_export_dir: Path) -> Path:
    """freqtrade writes backtest-result-<timestamp>.json (or .zip) into
    --export-directory with an auto-generated name; find whichever it wrote
    for this run (the directory is unique per call, so there's exactly one)."""
    for zip_path in run_export_dir.glob("backtest-result-*.zip"):
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(run_export_dir)

    candidates = [
        p
        for p in run_export_dir.glob("backtest-result-*.json")
        if "_config" not in p.name and "meta" not in p.name
    ]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        return candidates[0]
    raise BacktestError(f"Could not find backtest result JSON in {run_export_dir}")


def _parse_metrics(data: dict, start: str, end: str, json_path: str) -> BacktestMetrics:
    strategy_block = data.get("strategy", {})
    if isinstance(strategy_block, dict) and strategy_block:
        stats = next(iter(strategy_block.values()))
    else:
        stats = data

    total_trades = stats.get("total_trades")
    if total_trades is None:
        trades_field = stats.get("trades", [])
        total_trades = len(trades_field) if isinstance(trades_field, list) else (trades_field or 0)
    trades = total_trades or 0
    wins = stats.get("wins", 0) or 0
    losses = stats.get("losses", 0) or 0
    winrate = round(wins * 100.0 / trades, 2) if trades else 0.0

    max_dd_pct = stats.get("max_drawdown_account")
    if max_dd_pct is not None:
        max_dd_pct = round(max_dd_pct * 100, 2)
    else:
        max_dd_pct = round(stats.get("max_drawdown", 0.0) * 100, 2)

    # This freqtrade version reports profit_total/profit_mean as raw ratios
    # (e.g. 0.153) in the per-strategy stats block, not pre-multiplied
    # "_pct" fields (those only exist in some per-pair/per-tag breakdowns).
    profit_total_pct = stats.get("profit_total_pct")
    if profit_total_pct is None:
        profit_total_pct = stats.get("profit_total", 0.0) * 100
    profit_mean_pct = stats.get("profit_mean_pct")
    if profit_mean_pct is None:
        profit_mean_pct = stats.get("profit_mean", 0.0) * 100

    m = BacktestMetrics(
        start_date=start,
        end_date=end,
        trades=trades,
        wins=wins,
        losses=losses,
        winrate_pct=winrate,
        profit_total_pct=round(profit_total_pct, 3),
        profit_mean_pct=round(profit_mean_pct, 4),
        max_drawdown_pct=max_dd_pct,
        max_drawdown_abs=stats.get("max_drawdown_abs", 0.0),
        sharpe=stats.get("sharpe"),
        sortino=stats.get("sortino"),
        calmar=stats.get("calmar"),
        cagr=stats.get("cagr"),
        profit_factor=stats.get("profit_factor"),
        expectancy=stats.get("expectancy"),
        market_change_pct=round(stats.get("market_change", 0.0) * 100, 2)
        if stats.get("market_change") is not None
        else None,
        result_json_path=json_path,
        raw=stats,
    )
    for k, v in compute_daily_metrics(json_path, stats).items():
        setattr(m, k, v)
    return m


def _wallet_feather_for(result_json_path: str) -> Optional[Path]:
    """freqtrade writes <result>_<Strategy>_wallet.feather next to the result
    JSON. Find it without needing to know the strategy name."""
    p = Path(result_json_path)
    matches = sorted(p.parent.glob(p.stem + "_*_wallet.feather"))
    return matches[0] if matches else None


def _rebuild_equity_curve(stats: dict, data_dir):
    """Reconstruct the true daily mark-to-market equity curve from order flow.

    WHY NOT THE WALLET EXPORT: freqtrade's *_wallet.feather writes one row per
    CURRENCY per update event - not a fixed-cadence full-portfolio snapshot -
    and never writes a zeroing row when a position closes. Summing rows per
    timestamp therefore silently omits any open position that did not happen to
    tick at that exact instant, and (for pairs whose price data ends mid-run)
    omits it permanently. Measured on the survivorship runs that produced a
    PERSISTENT 13-20% shortfall versus the reported final balance, and even on
    clean survivor-only runs it understated the drawdown path badly (X7 upstream:
    wallet method said 4.65%, true value is 25.80%).

    This instead replays every fill from the trade list to get cash and coin
    holdings per day, then marks holdings against that pair's own daily close
    from user_data/data. Cross-validated on six independent runs: reconstructed
    final equity matches freqtrade's reported final_balance to within 0.02-0.07%,
    and at moments when no position is open it matches
    (starting_balance + cumulative realized P&L) to ~0.05%.

    Positions in pairs whose price data ends mid-backtest are held at their last
    known price (generous - in reality a delisted coin could not be sold at all).

    Returns None if the trade list or price data is unusable.
    """
    try:
        import pandas as pd
    except ImportError:
        return None

    trades = stats.get("trades") or []
    if not trades:
        return None
    start_balance = stats.get("starting_balance")
    if not start_balance:
        return None

    events = []
    for t in trades:
        fee_open = t.get("fee_open") or 0.0
        fee_close = t.get("fee_close") or 0.0
        for o in t.get("orders") or []:
            ts_ms = o.get("order_filled_timestamp")
            if ts_ms is None:
                continue
            ts = pd.to_datetime(ts_ms, unit="ms", utc=True)
            cost = o.get("cost")
            if cost is None:
                cost = (o.get("amount") or 0.0) * (o.get("safe_price") or 0.0)
            amount = o.get("amount") or 0.0
            if o.get("ft_order_side") in ("buy", "long"):
                events.append((ts, t["pair"], +amount, -cost * (1 + fee_open)))
            else:
                events.append((ts, t["pair"], -amount, +cost * (1 - fee_close)))
    if not events:
        return None

    ev = pd.DataFrame(events, columns=["ts", "pair", "damt", "dcash"]).sort_values("ts")
    ev["day"] = ev["ts"].dt.floor("D")
    days = pd.date_range(ev["day"].min(), ev["day"].max(), freq="1D")

    cash = start_balance + ev.groupby("day")["dcash"].sum().reindex(days, fill_value=0).cumsum()
    # NOTE on .reindex(days).fillna(0.0) rather than .reindex(days, fill_value=0):
    # pivot_table leaves NaN wherever a pair had no fill on a day that OTHER pairs
    # did trade, and reindex's fill_value only fills days missing from the index
    # entirely - not those pre-existing NaN cells. cumsum then carries the NaN
    # forward, so that pair's holding silently vanishes from the equity sum on
    # those days (measured: ~1,929 USDT of a ~11,100 USDT account disappearing on
    # 2025-05-03, manufacturing a phantom 19% drawdown). fillna(0.0) after the
    # reindex zeroes both cases before the cumsum, which is the correct semantics:
    # "no fill that day" means "no change in holdings", not "unknown".
    holdings = (
        ev.pivot_table(index="day", columns="pair", values="damt", aggfunc="sum")
        .reindex(days)
        .fillna(0.0)
        .cumsum()
    )
    # Float residue from summing large coin amounts (e.g. FUN trades in units of
    # 10M+) leaves ~1e-9 dust after a position is fully closed; 1e-12 is too tight
    # to catch it and the dust then gets marked at market price forever.
    holdings[holdings.abs() < 1e-6] = 0.0

    prices = {}
    for pair in holdings.columns:
        f = data_dir / f"{pair.replace('/', '_')}-5m.feather"
        if not f.exists():
            continue
        try:
            closes = pd.read_feather(f).set_index("date")["close"]
        except Exception:  # noqa: BLE001
            continue
        prices[pair] = closes.resample("1D").last().reindex(days).ffill()
    if not prices:
        return None

    price_frame = pd.DataFrame(prices).reindex(columns=holdings.columns)
    return cash + (holdings * price_frame).sum(axis=1)


def compute_daily_metrics(result_json_path: str, stats: dict) -> dict:
    """Daily MARK-TO-MARKET risk metrics (Sharpe / Sortino / max drawdown /
    volatility), plus slot-occupancy stats.

    These exist because freqtrade's own sharpe/sortino/max_drawdown are computed
    over the PER-TRADE profit_ratio series, which distorts them two ways for this
    strategy: (a) grinding trades accumulate max_stake_amount across hundreds of
    orders, inflating the ratio's denominator (COTI: -284 USDT recorded as
    -0.36%), and (b) unrealized losses on open positions never touch the curve at
    all. The gap is large: on the upstream X7 18-month run freqtrade reports a
    2.63% max drawdown while the true mark-to-market figure is 25.80%.

    IMPORTANT (2026-08-22): an earlier implementation of this function derived
    the equity curve from freqtrade's *_wallet.feather export. That was wrong -
    see _rebuild_equity_curve() for why and by how much. Any drawdown/Sharpe
    figure produced by this function before that date should be discarded.

    Note the resulting drawdown is NOT directly comparable to NFI's own CI bar
    (tests/backtests/test_winrate_and_drawdown.py, max_drawdown <= 15%), which is
    defined on freqtrade's realized-only basis. Compare like with like.

    Returns {} if pandas/numpy or the underlying data are unavailable, so this
    never breaks a run that would otherwise succeed.
    """
    try:
        import numpy as np
    except ImportError:
        return {}

    out: dict = {}

    try:
        daily = _rebuild_equity_curve(stats, USER_DATA / "data" / "binance")
    except Exception:  # noqa: BLE001 - diagnostics must never fail a run
        daily = None

    if daily is not None and len(daily) > 2:
        r = daily.pct_change().dropna()
        if len(r) > 1 and r.std() > 0:
            out["daily_sharpe"] = round(float(r.mean() / r.std() * np.sqrt(365)), 3)
            out["daily_ann_volatility_pct"] = round(float(r.std() * np.sqrt(365) * 100), 2)
        downside = r[r < 0]
        if len(downside) > 1 and downside.std() > 0:
            out["daily_sortino"] = round(float(r.mean() / downside.std() * np.sqrt(365)), 3)
        peak = daily.cummax()
        dd = daily / peak - 1.0
        out["daily_max_drawdown_pct"] = round(float(-dd.min() * 100), 2)
        out["daily_max_drawdown_abs"] = round(float((peak - daily).max()), 2)
        out["daily_return_total_pct"] = round(float((daily.iloc[-1] / daily.iloc[0] - 1.0) * 100), 3)
        out["days_in_drawdown_gt_1pct"] = int((dd < -0.01).sum())
        # Self-check: reconstructed final equity vs freqtrade's own reported
        # final_balance. Anything above ~0.5% means the reconstruction is off and
        # the figures above should not be trusted.
        report_final = stats.get("final_balance")
        if report_final:
            out["equity_recon_error_pct"] = round(
                float(abs(daily.iloc[-1] - report_final) / report_final * 100), 3
            )

    # --- slot occupancy -----------------------------------------------------
    trades = stats.get("trades") or []
    backtest_days = stats.get("backtest_days")
    max_open = stats.get("max_open_trades")
    if trades and backtest_days and max_open:
        durations_days = sorted((t.get("trade_duration") or 0) / 1440.0 for t in trades)
        used = sum(durations_days)
        capacity = float(backtest_days) * float(max_open)
        out["slot_days_used"] = round(used, 1)
        out["slot_days_capacity"] = round(capacity, 1)
        if capacity > 0:
            out["slot_utilization_pct"] = round(used / capacity * 100, 2)
        out["longest_trade_days"] = round(durations_days[-1], 2)
        if used > 0:
            out["slot_days_top3_share_pct"] = round(sum(durations_days[-3:]) / used * 100, 1)

    return out


def check_failure_criteria(m: BacktestMetrics) -> dict:
    """Four pass/fail checks applied to a single (typically OOS) window.

    1-2 mirror NFI's own official CI bar (tests/backtests/test_winrate_and_drawdown.py):
       winrate >= 85%, max_drawdown <= 15% (0 trades counts as pass, same as upstream).
    3-4 are additional checks we add for walk-forward robustness screening:
       net OOS return must be >= 0%, and Sharpe (if available) must be >= 0.
    These are deliberately strict/simple; see the final report for discussion
    of why a 45-day OOS slice failing #1/#2 is not automatically damning.
    """
    no_trades = m.trades == 0
    c1_winrate = (m.winrate_pct >= OFFICIAL_MIN_WINRATE_PCT) or no_trades
    c2_drawdown = m.max_drawdown_pct <= OFFICIAL_MAX_DRAWDOWN_PCT
    c3_nonneg_return = m.profit_total_pct >= 0.0
    c4_nonneg_sharpe = (m.sharpe is None) or (m.sharpe >= 0.0)

    checks = {
        "c1_winrate_ge_85pct": c1_winrate,
        "c2_max_drawdown_le_15pct": c2_drawdown,
        "c3_net_return_nonnegative": c3_nonneg_return,
        "c4_sharpe_nonnegative": c4_nonneg_sharpe,
    }
    checks["num_failed"] = sum(1 for v in checks.values() if v is False)
    checks["passed_all"] = checks["num_failed"] == 0
    return checks


def daterange_str(d: date) -> str:
    return d.strftime("%Y%m%d")
