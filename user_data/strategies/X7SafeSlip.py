"""OURS with the measured dry-run entry gap (reports/EXPERIMENTS_2026-11-03.md 1.1)."""

from X7SafeStopVariants import X7SafeStopHonored

REBUY_TAGS = {"61", "62", "63", "64", "65", "68"}


def slipped_first_entry(trade, proposed_rate: float, entry_tag) -> float:
  """Raise a trade's first entry by the mean gap measured for its side; DCA fills stay put."""
  if trade is not None:
    return proposed_rate
  tags = (entry_tag or "").split()
  rebuy = bool(tags) and any(t in REBUY_TAGS for t in tags)
  return proposed_rate * (1.0 + (0.0037 if rebuy else 0.0071))


class X7SafeSlip(X7SafeStopHonored):
  def custom_entry_price(self, pair, trade, current_time, proposed_rate, entry_tag, side, **kwargs) -> float:
    return slipped_first_entry(trade, proposed_rate, entry_tag)
