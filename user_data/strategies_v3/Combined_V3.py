# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
"""
Combined_V3 —— 在冻结的 Combined_V2_Protections 基础上，修复独立AI代码复查
（2026-08-14）确认属实的三个"回测正确、实盘有隐患"问题。不修改任何冻结文件
（Combined_V2_Protections.py / Combined_V1_Throttle.py / BaselineStrategy.py
按项目规矩保持原样，历史回测数字182笔/+24.62%/7.76%/1.36继续只对应它们），
本文件是一个新的、独立验证的版本。

============================================================
三处改动，逐一说明"为什么改"和"对回测数字有没有实际影响"
============================================================

改动1：新增 startup_candle_count = 200
------------------------------------------------------------
问题：Combined_V2_Protections 没有声明这个字段（grep确认过），freqtrade对
未声明的策略默认给 startup_candle_count=0。策略用到的指标里最大周期是
EMA(50)，另外还有 bollinger(window=40)、rolling(window=30)。live模式下
freqtrade每次都会多拉1000根历史K线垫底，不受影响；但回测模式下，每个回测
窗口的最前面一段K线，这些指标还没吃到足够历史数据、处于未完全收敛状态
（EMA尤其明显，需要显著多于50根才能收敛稳定）。

对回测数字的影响：预期是"轻微、可解释、方向明确"的修正，不是退步——
之前窗口开头那一小段（约200根K线，5m周期约16.7小时）指标不稳定期间，
如果有真实信号本应能触发但被跳过了，现在能补上。已用18个月连续区间回测
实测验证（见下方"第二部分"实测结果），如实记录了实际差异方向和幅度。

设为200：覆盖最大周期参数EMA(50)，并留出约3倍冗余（40*3=120，50*4=200，
参考项目里 MeanReversionStrategy.py 的同类注释："覆盖所有可调周期参数的
最大取值...留出约3倍冗余，避免...指标算出来全是NaN"），确保窗口开头指标
已经收敛到稳定状态，不是勉强凑够最小可用长度。

改动2：order_types.stoploss 从默认 'limit' 改成 'market'
------------------------------------------------------------
问题：Combined_V2_Protections 没有覆盖 order_types（grep确认过），用的是
freqtrade框架默认值 {"entry": "limit", "exit": "limit", "stoploss": "limit",
"stoploss_on_exchange": False}。本策略的入场条件专门找"瀑布式急跌"
（close < 0.985 * bb_lowerband，或单根K线跌幅超1.75%），这类行情下限价止损
单可能根本挂不上（价格快速穿过限价却没有对手盘吃单），live/dry-run下实际
亏损可能远超策略设定的静态-5%止损。

对回测数字的影响：已去看 freqtrade/optimize/backtesting.py 源码核实，
**回测引擎不区分 market/limit 两种止损单类型**。第344~347行明确写着
"Set stoploss_on_exchange to false for backtesting, since a 'perfect'
stoploss-exit is assumed anyway"，止损平仓价格的计算逻辑（_get_close_rate_
for_stoploss，约第598行）只根据 trade.stop_loss 相对K线high/low的位置算
成交价，全程没有任何分支读取 order_types['stoploss'] 的值去决定要不要模拟
滑点或不成交。也就是说：**这个改动对回测模式下的任何数字（笔数/收益/
回撤/Sharpe）不会有任何影响**——回测引擎本来就假设止损是"完美成交"，
不管你声明的是limit还是market。这个改动只在live/dry-run模式下才有实际
行为差异（市价止损单成交概率远高于限价止损单，代价是可能有滑点，但比
"根本不成交、继续持有暴跌仓位"要安全）。这是"改了代码但回测数字保证不变、
效果只体现在实盘"的一处修复，已实测确认（见第二部分）而非假设。

改动3：confirm_trade_entry 直接使用修复过的实现，不再需要额外子类
------------------------------------------------------------
问题：此前维护两份几乎相同的 confirm_trade_entry——
Combined_V2_Protections.py（继承自 Combined_V1_Throttle，两个文件里这段
代码逐字相同）里是"墙钟时间戳精确比较"版本（t.open_date_utc == current_
time），这个比较只在回测模式下成立（回测里两者都是K线对齐的离散值）；
在live/dry-run模式下 current_time 和 open_date 都是精度到微秒的墙钟
时间戳，精确相等比较几乎永远不成立，导致同一根K线并发开仓上限
（max_concurrent_entries_per_candle=4）在live/dry-run下形同虚设——这正是
阶段四引入 Combined_V2_Protections_Dryrun 子类的原因。

V3直接把 Combined_V2_Protections_Dryrun 里已验证过的修复版实现（用
freqtrade内置的 timeframe_to_prev_date() 把两个时间戳分别floor到各自所属
K线的起始时刻，再比较是否落在同一根K线）作为主实现，不再需要额外子类。

这个实现同时适用于回测和live/dry-run两种模式（这正是它在
Combined_V2_Protections_Dryrun里被设计出来的初衷）：
  - 回测模式：current_time/open_date_utc 本来就已经是K线open time（K线
    边界对齐的值），对一个已经对齐到边界的时间戳做"floor到所在K线"是
    幂等操作（timeframe_to_prev_date文档明确写"Does not round when given
    a candle start date"），floor前后完全相等，所以V3在回测模式下这一处
    改动预期与V2完全等价，不会引入任何数字差异（已用第二部分实测验证）。
  - live/dry-run模式：墙钟时间戳被正确floor到所属K线起点，恢复并发节流
    的实际效力。
  → 结论：V3的 confirm_trade_entry 已经是"回测/live两用"的正确实现，
    不需要再像V2那样为live/dry-run场景单独拆一个子类。

============================================================
第二部分：实测结果（18个月连续区间回测 + 10窗口 compare_to_baseline 对比）
============================================================
见任务交付总结，此处不重复贴数字，避免这段头部注释和实际跑出来的结果
不同步、以后又需要人工对齐维护。三处改动各自的"预期方向"已经在上面写清楚，
实测数字以本次交付的总结报告为准。

============================================================
与冻结文件的关系
============================================================
本文件基于 Combined_V2_Protections.py 复制而来，除上述三处改动外，指标/
入场/离场/protections property 逻辑与 Combined_V2_Protections 完全一致
（未改动），确保这次对比看到的差异只来自这三处修复本身。
Combined_V2_Protections.py / Combined_V1_Throttle.py / BaselineStrategy.py
三个冻结文件本身未做任何修改。
"""

import logging
from datetime import datetime

# --- Do not remove these libs ---
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np
# --------------------------------
import talib.abstract as ta
from freqtrade.exchange import timeframe_to_prev_date
from freqtrade.persistence import Trade
from freqtrade.strategy import IntParameter, IStrategy
from pandas import DataFrame

logger = logging.getLogger(__name__)


def bollinger_bands(stock_price, window_size, num_of_std):
    rolling_mean = stock_price.rolling(window=window_size).mean()
    rolling_std = stock_price.rolling(window=window_size).std()
    lower_band = rolling_mean - (rolling_std * num_of_std)
    return np.nan_to_num(rolling_mean), np.nan_to_num(lower_band)


class Combined_V3(IStrategy):
    # Based on a backtesting:
    # - the best perfomance is reached with "max_open_trades" = 2 (in average for any market),
    #   so it is better to increase "stake_amount" value rather then "max_open_trades" to get more profit
    # - if the market is constantly green(like in JAN 2018) the best performance is reached with
    #   "max_open_trades" = 2 and minimal_roi = 0.01
    INTERFACE_VERSION: int = 3
    minimal_roi = {
        "0": 0.05
    }
    stoploss = -0.05
    timeframe = '5m'

    use_exit_signal = True
    exit_profit_only = True
    ignore_roi_if_entry_signal = False

    # 改动1（见文件头"问题诊断"）：Combined_V2_Protections 没有声明这个字段，
    # 默认值0导致回测窗口开头一段K线指标未完全收敛。本策略最大指标周期是
    # EMA(50)，另有 bollinger(window=40)、rolling(window=30)，200留出约3倍
    # 冗余，参考 MeanReversionStrategy.py 同类注释的做法。
    startup_candle_count: int = 200

    # 改动2（见文件头"问题诊断"）：把止损单类型从框架默认的 'limit' 改成
    # 'market'。本策略专门捕捉"瀑布式急跌"信号，急跌行情下限价止损单可能
    # 挂不上、导致实盘亏损远超策略设定的-5%静态止损；已核实freqtrade回测
    # 引擎（backtesting.py 第344~347行）对止损固定按"完美成交"处理，不读取
    # order_types['stoploss']这个字段做任何滑点/不成交模拟，所以这一处改动
    # 对回测数字保证没有任何影响，只在live/dry-run下改变实际下单行为。
    # entry/exit保持limit不变，stoploss_on_exchange保持False不变——这次只
    # 解决"急跌行情限价止损可能不成交"这一个具体风险点。
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    # 同一根K线并发开仓上限，与 Combined_V1_Throttle / Combined_V2_Protections
    # 完全一致（未改动），详见 Combined_V1_Throttle.py 文件头"参数依据"。
    max_concurrent_entries_per_candle = IntParameter(
        1, 7, default=4, space="buy", optimize=False, load=True
    )

    # ------------------------------------------------------------------
    # 风险防护三件套（改造2，与 Combined_V2_Protections 完全一致，未改动。
    # 详见 Combined_V2_Protections.py 文件头详细诊断与参数依据。）
    # ------------------------------------------------------------------
    @property
    def protections(self):
        return [
            {
                "method": "CooldownPeriod",
                "stop_duration_candles": 2,
            },
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 12,
                "trade_limit": 3,
                "stop_duration_candles": 6,
                "only_per_pair": True,
            },
            {
                "method": "MaxDrawdown",
                "lookback_period_candles": 288,
                "trade_limit": 6,
                "stop_duration_candles": 288,
                "max_allowed_drawdown": 0.15,
                "calculation_mode": "equity",
            },
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # strategy BinHV45
        mid, lower = bollinger_bands(dataframe['close'], window_size=40, num_of_std=2)
        dataframe['lower'] = lower
        dataframe['bbdelta'] = (mid - dataframe['lower']).abs()
        dataframe['closedelta'] = (dataframe['close'] - dataframe['close'].shift()).abs()
        dataframe['tail'] = (dataframe['close'] - dataframe['low']).abs()
        # strategy ClucMay72018
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['volume_mean_slow'] = dataframe['volume'].rolling(window=30).mean()

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (  # strategy BinHV45
                    dataframe['lower'].shift().gt(0) &
                    dataframe['bbdelta'].gt(dataframe['close'] * 0.008) &
                    dataframe['closedelta'].gt(dataframe['close'] * 0.0175) &
                    dataframe['tail'].lt(dataframe['bbdelta'] * 0.25) &
                    dataframe['close'].lt(dataframe['lower'].shift()) &
                    dataframe['close'].le(dataframe['close'].shift())
            ) |
            (  # strategy ClucMay72018
                    (dataframe['close'] < dataframe['ema_slow']) &
                    (dataframe['close'] < 0.985 * dataframe['bb_lowerband']) &
                    (dataframe['volume'] < (dataframe['volume_mean_slow'].shift(1) * 20))
            ),
            'enter_long'
        ] = 1
        return dataframe

    # ------------------------------------------------------------------
    # 改动3（见文件头"问题诊断"）：同一根K线并发开仓节流，直接使用
    # Combined_V2_Protections_Dryrun 里已验证过的修复版实现——用
    # timeframe_to_prev_date() 把两侧时间戳floor到所属K线起始时刻再比较，
    # 而不是对墙钟时间戳做精确相等比较。回测模式下这是幂等操作（不改变
    # 行为，已实测验证），live/dry-run模式下这是让并发节流恢复实际效力
    # 所必需的修正。这个实现同时适用于两种模式，V3不再需要像V2那样为
    # live/dry-run单独拆一个子类。
    # ------------------------------------------------------------------
    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag,
        side: str,
        **kwargs,
    ) -> bool:
        candle_trades = Trade.get_trades_proxy()
        current_candle = timeframe_to_prev_date(self.timeframe, current_time)
        same_candle_count = sum(
            1
            for t in candle_trades
            if timeframe_to_prev_date(self.timeframe, t.open_date_utc) == current_candle
        )
        if same_candle_count >= self.max_concurrent_entries_per_candle.value:
            logger.info(
                "[ConcurrencyGuard] 拒绝开仓 %s：本根K线（%s）已有 %d 笔新开仓，"
                "达到并发上限 %d——避免像2025-10-10 21:00~21:40那次事件一样，"
                "在一次市场同步波动里对多个高相关币种同时下注。",
                pair,
                current_candle,
                same_candle_count,
                self.max_concurrent_entries_per_candle.value,
            )
            return False

        return True

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        """
        dataframe.loc[
            (dataframe['close'] > dataframe['bb_middleband']),
            'exit_long'
        ] = 1
        return dataframe
