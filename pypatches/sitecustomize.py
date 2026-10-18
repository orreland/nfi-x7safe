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


# ---------------------------------------------------------------------------
# Opt-in (FT_LOWMEM=1): drop a redundant full copy of every pair's indicator
# frame during backtesting.
#
# Backtesting.backtest_one_strategy() builds `preprocessed_tmp` with
# trim_dataframes(); the end-date trim is a boolean .loc, which always copies,
# so this is a second full set of indicator frames (~199 columns x ~158k
# candles per pair over 18 months). It is only read to get min/max dates and,
# with --export signals, to build signal tables - yet it stays referenced for
# the whole backtest loop. An 18-month X7 run peaks right at this machine's
# commit limit, so freeing it early is the difference between finishing and
# MemoryError. Trading logic, data and results are untouched: the same
# `preprocessed` dict goes to backtest() exactly as before.
# ---------------------------------------------------------------------------
import os as _os

if _os.environ.get("FT_LOWMEM") == "1":
    try:
        import gc as _gc

        from freqtrade.optimize import backtesting as _bt

        _orig_backtest_one_strategy = _bt.Backtesting.backtest_one_strategy

        def _lowmem_backtest_one_strategy(self, strat, data, timerange):
            if self.config.get("export", "none") == "signals":
                return _orig_backtest_one_strategy(self, strat, data, timerange)
            self._set_progress_step(_bt.BacktestState.ANALYZE, 0)
            strategy_name = strat.get_strategy_name()
            _bt.logger.info(f"Running backtesting for Strategy {strategy_name} [FT_LOWMEM]")
            backtest_start_time = _bt.dt_now()
            self._set_strategy(strat)

            preprocessed = self.strategy.advise_all_indicators(data)
            preprocessed_tmp = _bt.trim_dataframes(preprocessed, timerange, self.required_startup)
            if not preprocessed_tmp:
                raise _bt.OperationalException("No data left after adjusting for startup candles.")
            min_date, max_date = _bt.history.get_timerange(preprocessed_tmp)
            del preprocessed_tmp
            _gc.collect()
            _bt.logger.info(
                f"Backtesting with data from {min_date.strftime(_bt.DATETIME_PRINT_FORMAT)} "
                f"up to {max_date.strftime(_bt.DATETIME_PRINT_FORMAT)} "
                f"({(max_date - min_date).days} days)."
            )
            results = self.backtest(processed=preprocessed, start_date=min_date, end_date=max_date)
            backtest_end_time = _bt.dt_now()
            results.update(
                {
                    "run_id": self.run_ids.get(strategy_name, ""),
                    "backtest_start_time": int(backtest_start_time.timestamp()),
                    "backtest_end_time": int(backtest_end_time.timestamp()),
                }
            )
            self.all_bt_content[strategy_name] = results
            return min_date, max_date

        _bt.Backtesting.backtest_one_strategy = _lowmem_backtest_one_strategy

        # Same idea one step later: _get_ohlcv_as_lists() writes each pair's
        # trimmed copy back into `processed` ("gets cleared to optimize memory
        # usage" per its docstring, but it never is), while the dataprovider
        # cache already holds the full analysed frame the strategy reads from.
        # Nothing reads `processed` after the conversion (the loop runs on the
        # lists; signal export uses preprocessed_tmp, handled above), so park
        # an empty frame there instead of a second full copy. Body otherwise
        # identical to freqtrade 2026.7.
        def _lowmem_get_ohlcv_as_lists(self, processed):
            data = {}
            self._set_progress_step(_bt.BacktestState.CONVERT, len(processed))
            for pair in processed.keys():
                pair_data = processed[pair]
                self.check_abort()
                self._increment_progress()
                if not pair_data.empty:
                    pair_data.drop(_bt.HEADERS[5:] + ["buy", "sell"], axis=1, errors="ignore")
                df_analyzed = self.strategy.ft_advise_signals(pair_data, {"pair": pair})
                self.dataprovider._set_cached_df(pair, self.timeframe, df_analyzed, self.config["candle_type_def"])
                df_analyzed = pair_data = _bt.trim_dataframe(
                    df_analyzed, self.timerange, startup_candles=self.required_startup
                )
                # a fresh frame, not iloc[0:0] - an empty view would still pin the buffers
                processed[pair] = _bt.DataFrame()
                df_analyzed = df_analyzed.copy()
                for col in _bt.HEADERS[5:]:
                    tag_col = col in ("enter_tag", "exit_tag")
                    if col in df_analyzed.columns:
                        df_analyzed[col] = (
                            df_analyzed.loc[:, col].replace([_bt.nan], [0 if not tag_col else None]).shift(1)
                        )
                    elif not df_analyzed.empty:
                        df_analyzed[col] = 0 if not tag_col else None
                df_analyzed = df_analyzed.drop(df_analyzed.head(1).index)
                data[pair] = df_analyzed[_bt.HEADERS].values.tolist() if not df_analyzed.empty else []
                del pair_data, df_analyzed
            _gc.collect()
            return data

        _bt.Backtesting._get_ohlcv_as_lists = _lowmem_get_ohlcv_as_lists
    except Exception as _e:  # never break freqtrade startup over an optimisation
        print(f"[sitecustomize] FT_LOWMEM patch not applied: {_e}")

