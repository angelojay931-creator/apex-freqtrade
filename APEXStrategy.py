"""
APEX MTF Strategy for Freqtrade
================================
Ports your proven bybit bot logic into Freqtrade:
  - Supertrend (ATR 10, mult 3.0)
  - UT Bot (key 1, ATR 10)
  - EMA 20/50/200
  - Multi-timeframe: 1h base + 4h informative (consensus)
  - 5x leverage
  - Single TP via ROI + trailing stop

Same signal philosophy as APEX bybit v3, adapted to Freqtrade's framework.
"""
from freqtrade.strategy import IStrategy, informative
from pandas import DataFrame
import talib.abstract as ta
import numpy as np


class APEXStrategy(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = '1h'
    can_short = True   # MTF bot goes both directions

    # ── Single TP via ROI (≈ TP at ~3% which at 5x = 15% on margin) ──
    minimal_roi = {
        "0": 0.06,
        "60": 0.04,
        "180": 0.025,
        "360": 0.015
    }

    # Stoploss (≈ 2x ATR equivalent, hard floor)
    stoploss = -0.05

    # Trailing stop — locks profit like your bybit trailing
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = True

    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    startup_candle_count = 250

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 3},
            {"method": "MaxDrawdown", "lookback_period_candles": 24,
             "trade_limit": 10, "stop_duration_candles": 6,
             "max_allowed_drawdown": 0.10}
        ]

    # 5x leverage
    def leverage(self, pair, current_time, current_rate, proposed_leverage,
                 max_leverage, side, **kwargs) -> float:
        return 5.0

    # ── 4h informative timeframe for MTF consensus ──
    @informative('4h')
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['ema20'] = ta.EMA(dataframe, timeperiod=20)
        dataframe['ema50'] = ta.EMA(dataframe, timeperiod=50)
        # Supertrend on 4h
        dataframe = self.supertrend(dataframe, period=10, multiplier=3.0)
        return dataframe

    def supertrend(self, dataframe: DataFrame, period=10, multiplier=3.0) -> DataFrame:
        df = dataframe.copy()
        atr = ta.ATR(df, timeperiod=period)
        hl2 = (df['high'] + df['low']) / 2
        upper = hl2 + multiplier * atr
        lower = hl2 - multiplier * atr
        final_up = upper.copy()
        final_dn = lower.copy()
        st = [True] * len(df)
        for i in range(1, len(df)):
            # sticky bands
            final_up.iloc[i] = min(upper.iloc[i], final_up.iloc[i-1]) if df['close'].iloc[i-1] > final_up.iloc[i-1] else upper.iloc[i]
            final_dn.iloc[i] = max(lower.iloc[i], final_dn.iloc[i-1]) if df['close'].iloc[i-1] < final_dn.iloc[i-1] else lower.iloc[i]
            if df['close'].iloc[i] > final_up.iloc[i-1]:
                st[i] = True
            elif df['close'].iloc[i] < final_dn.iloc[i-1]:
                st[i] = False
            else:
                st[i] = st[i-1]
        df['st_bull'] = [1 if x else 0 for x in st]
        return df

    def ut_bot(self, dataframe: DataFrame, key_value=1.0, atr_period=10) -> DataFrame:
        df = dataframe.copy()
        atr = ta.ATR(df, timeperiod=atr_period)
        n_loss = key_value * atr
        close = df['close'].values
        trail = np.zeros(len(df))
        for i in range(1, len(df)):
            prev = trail[i-1]
            if close[i] > prev and close[i-1] > prev:
                trail[i] = max(prev, close[i] - n_loss.iloc[i])
            elif close[i] < prev and close[i-1] < prev:
                trail[i] = min(prev, close[i] + n_loss.iloc[i])
            elif close[i] > prev:
                trail[i] = close[i] - n_loss.iloc[i]
            else:
                trail[i] = close[i] + n_loss.iloc[i]
        df['ut_trail'] = trail
        df['ut_buy'] = ((df['close'].shift(1) < df['ut_trail'].shift(1)) & (df['close'] > df['ut_trail'])).fillna(False)
        df['ut_sell'] = ((df['close'].shift(1) > df['ut_trail'].shift(1)) & (df['close'] < df['ut_trail'])).fillna(False)
        return df

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 1h indicators
        dataframe['ema20'] = ta.EMA(dataframe, timeperiod=20)
        dataframe['ema50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema200'] = ta.EMA(dataframe, timeperiod=200)
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe = self.supertrend(dataframe, period=10, multiplier=3.0)
        dataframe = self.ut_bot(dataframe, key_value=1.0, atr_period=10)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # LONG: 1h supertrend bull + (UT buy OR EMA bull) + 4h supertrend bull agreement
        long_cond = (
            (dataframe['st_bull'] == 1) &
            (dataframe['ema20'] > dataframe['ema50']) &
            (dataframe['ema50'] > dataframe['ema200']) &
            (dataframe['st_bull_4h'] == 1) &
            (dataframe['ema20_4h'] > dataframe['ema50_4h']) &
            (dataframe['volume'] > 0)
        )
        # SHORT: 1h supertrend bear + (UT sell OR EMA bear) + 4h supertrend bear
        short_cond = (
            (dataframe['st_bull'] == 0) &
            (dataframe['ema20'] < dataframe['ema50']) &
            (dataframe['ema50'] < dataframe['ema200']) &
            (dataframe['st_bull_4h'] == 0) &
            (dataframe['ema20_4h'] < dataframe['ema50_4h']) &
            (dataframe['volume'] > 0)
        )
        dataframe.loc[long_cond, ['enter_long', 'enter_tag']] = (1, 'mtf_long')
        dataframe.loc[short_cond, ['enter_short', 'enter_tag']] = (1, 'mtf_short')
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit long when supertrend flips bear; exit short when flips bull
        dataframe.loc[(dataframe['st_bull_4h'] == 0), 'exit_long'] = 1
        dataframe.loc[(dataframe['st_bull_4h'] == 1), 'exit_short'] = 1
        return dataframe
