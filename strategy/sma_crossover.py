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
    def __init__(self, short_window: int = 20, long_window: int = 50):
        if short_window >= long_window:
            raise ValueError("short_window must be less than long_window")
        self.short_window = short_window
        self.long_window  = long_window

    @property
    def name(self) -> str:
        return f"SMA-Crossover ({self.short_window}/{self.long_window})"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close      = data["Close"]
        sma_short  = close.rolling(self.short_window).mean()
        sma_long   = close.rolling(self.long_window).mean()

        # Define state: 1 when short > long, -1 when short <= long
        state = pd.Series(-1, index=data.index, dtype=int)
        state[sma_short > sma_long] = 1

        # Only emit a signal on the crossover bar (change point), hold (0) otherwise
        # Transition from -1 to 1 yields diff = +2 (BUY)
        # Transition from 1 to -1 yields diff = -2 (SELL)
        diff = state.diff().fillna(0).astype(int)
        
        position = pd.Series(0, index=data.index, dtype=int)
        position[diff == 2] = 1
        position[diff == -2] = -1

        # Zero out any signals generated before both SMAs are fully computed
        position[sma_long.isna() | sma_short.isna()] = 0

        # Attach the indicator columns to the data for charting
        data["SMA_Short"] = sma_short
        data["SMA_Long"]  = sma_long

        return position
