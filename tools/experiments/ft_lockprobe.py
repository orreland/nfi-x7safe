"""Run a backtest through scripts/ft_delisted.py with protection lock creation
instrumented (observation only - return values pass through unchanged).

freqtrade's resolver loads protection plugins from their file path, creating a
separate module, so patching freqtrade.plugins.protections.max_drawdown_protection
has no effect. Instead patch the shared pieces every protection goes through:
  - IProtection.calculate_lock_end(trades): which trades decided the lock end
  - PairLocks.lock_pair(...): when a global lock is created, with now/until

usage: python scratch/tools/ft_lockprobe.py backtesting --strategy=... (same args as ft_delisted.py)
"""
import logging
import runpy
import sys
from pathlib import Path

from freqtrade.persistence.pairlock_middleware import PairLocks
from freqtrade.plugins.protections.iprotection import IProtection

log = logging.getLogger("LOCKPROBE")
_orig_end = IProtection.calculate_lock_end
_orig_lock = PairLocks.lock_pair.__func__ if hasattr(PairLocks.lock_pair, "__func__") else PairLocks.lock_pair


def _probed_end(self, trades):
    res = _orig_end(self, trades)
    latest = max((t for t in trades if t.close_date), key=lambda t: t.close_date, default=None)
    log.warning(
        f"LOCKPROBE calculate_lock_end by {type(self).__name__}: n={len(trades)} -> until={res}; latest close trade: "
        + (f"id={latest.id} {latest.pair} open={latest.open_date} close={latest.close_date} is_open={latest.is_open} "
           f"exit_reason={latest.exit_reason} close_profit={latest.close_profit}" if latest else "none")
    )
    for t in sorted(trades, key=lambda x: x.close_date or x.open_date)[-12:]:
        log.warning(
            f"LOCKPROBE     trade id={t.id} {t.pair} open={t.open_date} close={t.close_date} "
            f"is_open={t.is_open} exit_reason={t.exit_reason} close_profit={t.close_profit}"
        )
    return res


def _probed_lock(pair, until, reason=None, *, now=None, side="*"):
    if pair == "*":
        log.warning(f"LOCKPROBE lock_pair GLOBAL now={now} until={until} reason={reason}")
    return _orig_lock(pair, until, reason, now=now, side=side)


IProtection.calculate_lock_end = _probed_end
PairLocks.lock_pair = staticmethod(_probed_lock)
root = Path(__file__).resolve().parents[2]
sys.argv = [str(root / "scripts" / "ft_delisted.py")] + sys.argv[1:]
runpy.run_path(str(root / "scripts" / "ft_delisted.py"), run_name="__main__")
