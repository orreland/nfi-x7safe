"""
Project-local compatibility shim, loaded automatically via PYTHONPATH (see
scripts/nfi_backtest_lib.py) whenever we invoke `freqtrade` in this project.
Only affects processes that run with this PYTHONPATH set - never touches the
installed venv packages themselves.

Why this exists: ccxt's binance fetch_markets() unconditionally appends a
*signed* call to sapiGetEquityMarketExchangeInfo() (tokenized-stocks
metadata) whenever `self.apiKey is not None`. freqtrade always fills
exchange.key with a default (possibly ""), so apiKey is a string, never a
real Python None, and that condition is always true - even when no API key
was configured. The unauthenticated call then fails with
"binance requires apiKey credential", which breaks plain public OHLCV
downloads / backtesting for anyone without a Binance API key.

Fix: right after ccxt constructs a binance client, if apiKey ended up as an
empty string, set it back to a real None so ccxt's own gate (which is
exactly `is not None`) correctly treats "no key configured" as "no key
configured" and skips the tokenized-stocks call. A real key set by the user
(non-empty string) still passes through completely untouched. This project
only ever runs freqtrade in dry_run/backtesting mode, never live trading, so
no signed order-placement code path is affected by this.
"""
try:
    import ccxt
    import ccxt.async_support as ccxt_async

    def _patch(cls):
        _orig_init = cls.__init__

        def _patched_init(self, config=None, *args, **kwargs):
            if config is None:
                config = {}
            _orig_init(self, config, *args, **kwargs)
            if getattr(self, "apiKey", None) == "":
                self.apiKey = None

        cls.__init__ = _patched_init

    _patch(ccxt.binance)
    _patch(ccxt_async.binance)
    try:
        import ccxt.pro as ccxt_pro

        _patch(ccxt_pro.binance)
    except Exception:
        pass
except Exception:
    pass

