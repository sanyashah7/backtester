"""
strategy/mean_reversion.py
──────────────────────────
ALGORITHM 2 — Z-Score Mean Reversion
──────────────────────────────────────
Logic:
  • Compute the rolling mean and rolling std of closing prices over `window` bars.
  • Z-score = (price - rolling_mean) / rolling_std
              → measures how many std-devs the price is away from its recent average.
  • If z-score drops below  z_entry  (e.g. -1.5)  →  price is unusually LOW  →  BUY
    (expect it to revert back toward the mean)
  • If z-score rises above  z_exit   (e.g. +0.5)  →  price has recovered  →  SELL
  • Otherwise  →  HOLD (0)

Why it works:
  Mean-reverting assets (many stocks in range-bound markets, spread pairs)
  tend to bounce back after extreme moves. Works best in low-trend, high-noise
  environments — the opposite of where SMA crossover shines.

Weakness:
  Fails catastrophically in trending markets (keeps buying a falling knife).
"""

import pandas as pd
from strategy.base import Strategy


class MeanReversion(Strategy):
    def __init__(self, window: int = 20, z_entry: float = -1.5, z_exit: float = 0.5):
        self.window  = window
        self.z_entry = z_entry   # buy threshold  (negative = price below mean)
        self.z_exit  = z_exit    # sell threshold (positive = price above mean)

    @property
    def name(self) -> str:
        return f"Mean-Reversion (w={self.window}, entry={self.z_entry}, exit={self.z_exit})"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close        = data["Close"]
        rolling_mean = close.rolling(self.window).mean()
        rolling_std  = close.rolling(self.window).std()
        z_score      = (close - rolling_mean) / rolling_std

        signal   = pd.Series(0, index=data.index, dtype=int)
        in_trade = False

        for i in range(len(signal)):
            z = z_score.iloc[i]
            if pd.isna(z):
                continue
            if not in_trade and z <= self.z_entry:
                signal.iloc[i] = 1    # enter long
                in_trade = True
            elif in_trade and z >= self.z_exit:
                signal.iloc[i] = -1   # exit long
                in_trade = False

        # Attach indicator columns for charting
        data["Z_Score"]      = z_score
        data["Rolling_Mean"] = rolling_mean

        return signal
