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
