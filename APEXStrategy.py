# APEX FreqTrade Strategy
# Mirrors APEX signal logic using FreqTrade framework
# Paper trading (dry_run) only
# Runs alongside APEX bot — completely separate

from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class APEXStrategy(IStrategy):
    """
    APEX-style strategy for FreqTrade
    Uses RSI + EMA + MACD + Bollinger Bands
    Paper mode only — comparing vs APEX bot
    """

    INTERFACE_VERSION = 3

    # ── Timeframe ──
    timeframe = "1h"
    can_short = True

    # ── ROI — take profit targets ──
    minimal_roi = {
        "0":   0.089,   # TP4 — 8.9% (44.7% leveraged)
        "60":  0.060,   # TP3 — 6.0% after 60 min
        "120": 0.037,   # TP2 — 3.7% after 120 min
        "240": 0.022,   # TP1 — 2.2% after 240 min
    }

    # ── Stop loss ──
    stoploss = -0.03      # 3% stop loss (2x ATR equivalent)
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.022   # trail after TP1
    trailing_only_offset_is_reached = True

    # ── Startup candles needed ──
    startup_candle_count = 50

    # ── Tunable parameters ──
    buy_rsi_min  = IntParameter(30, 55, default=45, space="buy")
    buy_rsi_max  = IntParameter(55, 75, default=65, space="buy")
    sell_rsi_min = IntParameter(25, 45, default=35, space="sell")
    sell_rsi_max = IntParameter(45, 70, default=55, space="sell")
    adx_min      = IntParameter(20, 35, default=25, space="buy")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        # ── RSI ──
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # ── EMA ──
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)

        # ── MACD ──
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["macd"]        = macd["macd"]
        dataframe["macd_signal"] = macd["macdsignal"]
        dataframe["macd_hist"]   = macd["macdhist"]

        # ── Bollinger Bands ──
        bollinger = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe["bb_upper"]     = bollinger["upper"]
        dataframe["bb_mid"]       = bollinger["mid"]
        dataframe["bb_lower"]     = bollinger["lower"]
        dataframe["bb_bandwidth"] = (
            (dataframe["bb_upper"] - dataframe["bb_lower"])
            / dataframe["bb_mid"] * 100
        )

        # ── ATR ──
        dataframe["atr"]     = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"] * 100

        # ── ADX ──
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

        # ── Volume ratio ──
        dataframe["vol_avg"]   = dataframe["volume"].rolling(20).mean()
        dataframe["vol_ratio"] = dataframe["volume"] / dataframe["vol_avg"]

        # ── VWAP (rolling 24 candles) ──
        dataframe["typical_price"] = (
            dataframe["high"] + dataframe["low"] + dataframe["close"]) / 3
        dataframe["vwap"] = (
            (dataframe["typical_price"] * dataframe["volume"]).rolling(24).sum()
            / dataframe["volume"].rolling(24).sum()
        )

        # ── Breakout confirmation (Phase 2.7 preview) ──
        dataframe["highest_close"] = dataframe["close"].shift(1).rolling(20).max()
        dataframe["lowest_close"]  = dataframe["close"].shift(1).rolling(20).min()

        # ── OBV ──
        dataframe["obv"] = ta.OBV(dataframe)
        dataframe["obv_slope"] = dataframe["obv"].diff(5)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        # ── LONG conditions ──
        dataframe.loc[
            (
                # Momentum
                (dataframe["close"].pct_change(24) * 100 > 2) &

                # RSI not overbought
                (dataframe["rsi"] < self.buy_rsi_max.value) &
                (dataframe["rsi"] > self.buy_rsi_min.value) &

                # Trend
                (dataframe["ema20"] > dataframe["ema50"]) &

                # MACD bullish
                (dataframe["macd"] > dataframe["macd_signal"]) &

                # Above VWAP
                (dataframe["close"] > dataframe["vwap"]) &

                # ADX trending
                (dataframe["adx"] > self.adx_min.value) &

                # ATR not too low (not flat)
                (dataframe["atr_pct"] > 0.3) &

                # ATR not too high (not extreme)
                (dataframe["atr_pct"] < 8.0) &

                # Breakout confirmation
                (dataframe["close"] > dataframe["highest_close"]) &

                # Volume participation
                (dataframe["vol_ratio"] > 1.5) &

                # OBV rising
                (dataframe["obv_slope"] > 0) &

                # Candle data valid
                (dataframe["volume"] > 0)
            ),
            "enter_long"
        ] = 1

        # ── SHORT conditions ──
        dataframe.loc[
            (
                # Momentum down
                (dataframe["close"].pct_change(24) * 100 < -2) &

                # RSI not oversold
                (dataframe["rsi"] > self.sell_rsi_min.value) &
                (dataframe["rsi"] < self.sell_rsi_max.value) &

                # Trend down
                (dataframe["ema20"] < dataframe["ema50"]) &

                # MACD bearish
                (dataframe["macd"] < dataframe["macd_signal"]) &

                # Below VWAP
                (dataframe["close"] < dataframe["vwap"]) &

                # ADX trending
                (dataframe["adx"] > self.adx_min.value) &

                # ATR filters
                (dataframe["atr_pct"] > 0.3) &
                (dataframe["atr_pct"] < 8.0) &

                # Breakout confirmation
                (dataframe["close"] < dataframe["lowest_close"]) &

                # Volume participation
                (dataframe["vol_ratio"] > 1.5) &

                # OBV falling
                (dataframe["obv_slope"] < 0) &

                (dataframe["volume"] > 0)
            ),
            "enter_short"
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Let ROI + trailing stop handle exits
        # No fixed exit signals — same as APEX approach
        dataframe.loc[:, "exit_long"]  = 0
        dataframe.loc[:, "exit_short"] = 0
        return dataframe
