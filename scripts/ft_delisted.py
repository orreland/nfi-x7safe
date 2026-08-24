#!/usr/bin/env python
"""ft_delisted.py - run `freqtrade` with delisted pairs allowed through the
pairlist validator, so a backtest can include coins that have since died.

WHY
---
`IPairList._whitelist_for_active_markets()` drops any pair where
`market_is_active(market)` is false. Binance keeps delisted symbols in
exchangeInfo but flags them inactive, so every delisted pair is silently
removed from the whitelist even when its OHLCV data is on disk - freqtrade
logs "Ignoring X from whitelist. Market is not active." at INFO level and
carries on with a smaller universe.

That silent removal is the mechanism that hides survivorship bias: you cannot
accidentally backtest a coin that died. On this project's pairlist all 40 pairs
the blacklist excludes are now delisted (100%), so the tested universe is the
survivors by construction.

This launcher patches exactly that one predicate, for exactly the named pairs,
then hands off to freqtrade's normal CLI.

USAGE (identical to `python -m freqtrade ...` after the `--`)
  .venv\\Scripts\\python.exe scripts\\ft_delisted.py backtesting --strategy=... --config=...

SAFETY
  Refuses to run anything except `backtesting` / `download-data`. A live bot
  must never believe a delisted symbol is tradable - the exchange would reject
  the order anyway, but the bot would keep trying.
"""

from __future__ import annotations

import sys

DELISTED = {
  "ALPACA/USDT", "ALPHA/USDT", "BADGER/USDT", "BAKE/USDT", "BETA/USDT",
  "BNX/USDT", "BURGER/USDT", "DATA/USDT", "DEGO/USDT", "DF/USDT",
  "EOS/USDT", "ERN/USDT", "FARM/USDT", "FIS/USDT", "FLM/USDT",
  "FORTH/USDT", "FTM/USDT", "FUN/USDT", "FXS/USDT", "HARD/USDT",
  "HIGH/USDT", "IDEX/USDT", "KMD/USDT", "LINA/USDT", "LIT/USDT",
  "LRC/USDT", "LTO/USDT", "MBOX/USDT", "MDT/USDT", "MKR/USDT",
  "MLN/USDT", "NKN/USDT", "OM/USDT", "PERP/USDT", "POND/USDT",
  "STPT/USDT", "SXP/USDT", "TRU/USDT", "VIDT/USDT", "WING/USDT",
}


def main() -> int:
  args = sys.argv[1:]
  if not args or args[0] not in ("backtesting", "download-data"):
    print(
      "ft_delisted.py only wraps `backtesting` and `download-data`.\n"
      f"Got: {args[0] if args else '(nothing)'}",
      file=sys.stderr,
    )
    return 2

  import freqtrade.exchange.exchange_utils as exchange_utils
  import freqtrade.plugins.pairlist.IPairList as ipairlist_mod

  original = exchange_utils.market_is_active
  reactivated: set[str] = set()

  def market_is_active_allowing_delisted(market: dict) -> bool:
    if original(market):
      return True
    symbol = market.get("symbol")
    if symbol in DELISTED:
      reactivated.add(symbol)
      return True
    return False

  # Patch both the definition and the name IPairList imported into its own
  # namespace (`from ... import market_is_active`), otherwise the pairlist
  # keeps calling the unpatched original.
  exchange_utils.market_is_active = market_is_active_allowing_delisted
  if hasattr(ipairlist_mod, "market_is_active"):
    ipairlist_mod.market_is_active = market_is_active_allowing_delisted

  print(
    f"[ft_delisted] allowing {len(DELISTED)} delisted pairs through pairlist "
    f"validation (backtest only)",
    file=sys.stderr,
  )

  from freqtrade.main import main as freqtrade_main

  try:
    freqtrade_main(args)
  except SystemExit as exc:
    code = exc.code if isinstance(exc.code, int) else 0
  else:
    code = 0

  if reactivated:
    print(
      f"[ft_delisted] {len(reactivated)} delisted pairs entered the universe: "
      f"{', '.join(sorted(reactivated))}",
      file=sys.stderr,
    )
  else:
    print("[ft_delisted] WARNING: no delisted pair was reactivated", file=sys.stderr)
  return code


if __name__ == "__main__":
  sys.exit(main())
