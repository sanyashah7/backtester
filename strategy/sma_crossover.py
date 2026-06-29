"""
strategy/sma_crossover.py
──────────────────────────
ALGORITHM 1 — Dual Simple Moving Average (SMA) Crossover
─────────────────────────────────────────────────────────
Logic:
  • Compute a FAST (short) SMA and a SLOW (long) SMA over closing prices.
  • When the fast SMA crosses ABOVE the slow SMA  →  BUY signal  (+1)
    (the short-term trend is now stronger than the long-term trend)
  • When the fast SMA crosses BELOW the slow SMA  →  SELL signal (-1)
    (momentum is weakening)
  • While both SMAs move in the same direction  →  HOLD (0)

Why it works:
  Trend-following. Catches sustained directional moves.
  Classic, battle-tested, easy to interpret.

Weakness:
  Lags price; whipsaws badly in sideways / choppy markets.
"""

import pandas as pd
from strategy.base import Strategy


class SMACrossover(Strategy):
    def __init__(self, short_window: int = 20, long_window: int = 50, exit_below_fast_sma: bool = False):
        if short_window >= long_window:
            raise ValueError("short_window must be less than long_window")
        self.short_window = short_window
        self.long_window  = long_window
        self.exit_below_fast_sma = exit_below_fast_sma

    @property
    def name(self) -> str:
        suffix = " + Fast Exit" if self.exit_below_fast_sma else ""
        return f"SMA-Crossover ({self.short_window}/{self.long_window}){suffix}"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close      = data["Close"]
        sma_short  = close.rolling(self.short_window).mean()
        sma_long   = close.rolling(self.long_window).mean()

        position = pd.Series(0, index=data.index, dtype=int)
        in_trade = False

        for i in range(1, len(data)):
            # Ensure we have valid values for current and prior bars
            if pd.isna(sma_long.iloc[i]) or pd.isna(sma_short.iloc[i]) or pd.isna(sma_long.iloc[i-1]) or pd.isna(sma_short.iloc[i-1]):
                continue

            # Bullish crossover: short SMA crosses above long SMA
            bullish_cross = (sma_short.iloc[i] > sma_long.iloc[i]) and (sma_short.iloc[i-1] <= sma_long.iloc[i-1])
            # Bearish crossover: short SMA crosses below or equal to long SMA
            bearish_cross = (sma_short.iloc[i] <= sma_long.iloc[i]) and (sma_short.iloc[i-1] > sma_long.iloc[i-1])

            if not in_trade:
                if bullish_cross:
                    position.iloc[i] = 1
                    in_trade = True
            else:
                # Exit conditions: bearish crossover OR (if enabled) price closes below fast SMA
                if bearish_cross or (self.exit_below_fast_sma and close.iloc[i] < sma_short.iloc[i]):
                    position.iloc[i] = -1
                    in_trade = False

        # Attach the indicator columns to the data for charting
        data["SMA_Short"] = sma_short
        data["SMA_Long"]  = sma_long

        return position
