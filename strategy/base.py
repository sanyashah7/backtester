"""
strategy/base.py
────────────────
Abstract base class every strategy must implement.
"""

from abc import ABC, abstractmethod
import pandas as pd


class Strategy(ABC):
    """
    Override `generate_signals` to return a Series of trade signals:
        +1  →  BUY  (go long)
        -1  →  SELL (close long)
         0  →  HOLD (do nothing)
    """

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass
