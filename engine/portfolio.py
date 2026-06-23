"""
engine/portfolio.py
────────────────────
Simulates a single-asset long-only portfolio.
Accounts for:
  • Commission  — flat % on notional value of each trade
  • Slippage    — price impact (you buy slightly higher, sell slightly lower)
  • Cash management — can't spend more than you have
"""

import pandas as pd
from dataclasses import dataclass, field
from typing import List


@dataclass
class Trade:
    entry_date:  object
    exit_date:   object
    entry_price: float
    exit_price:  float
    shares:      float
    pnl:         float
    pnl_pct:     float


class Portfolio:
    def __init__(self, initial_cash: float = 10_000,
                 commission: float = 0.001,
                 slippage:   float = 0.0005):
        self.initial_cash = initial_cash
        self.cash         = initial_cash
        self.commission   = commission
        self.slippage     = slippage

        self.position     = 0.0   # shares currently held
        self.entry_price  = 0.0
        self.entry_date   = None

        self.equity_curve: List[dict] = []
        self.trades:       List[Trade] = []

    # ──────────────────────────────────────────────────────────────
    def execute(self, date, price: float, signal: int):
        """Process one bar."""
        fill_price = price * (1 + self.slippage * signal) if signal != 0 else price

        if signal == 1 and self.position == 0:
            # ── BUY ──────────────────────────────────────────────
            shares = self.cash // fill_price
            cost   = shares * fill_price * (1 + self.commission)
            if shares > 0 and cost <= self.cash:
                self.cash        -= cost
                self.position     = shares
                self.entry_price  = fill_price
                self.entry_date   = date

        elif signal == -1 and self.position > 0:
            # ── SELL ─────────────────────────────────────────────
            proceeds = self.position * fill_price * (1 - self.commission)
            pnl      = proceeds - (self.position * self.entry_price * (1 + self.commission))
            pnl_pct  = (fill_price / self.entry_price - 1) * 100

            self.trades.append(Trade(
                entry_date  = self.entry_date,
                exit_date   = date,
                entry_price = self.entry_price,
                exit_price  = fill_price,
                shares      = self.position,
                pnl         = round(pnl, 2),
                pnl_pct     = round(pnl_pct, 2),
            ))

            self.cash    += proceeds
            self.position = 0.0

        # Mark-to-market equity
        equity = self.cash + self.position * price
        self.equity_curve.append({"date": date, "equity": equity})

    # ──────────────────────────────────────────────────────────────
    def get_equity_df(self) -> pd.DataFrame:
        df = pd.DataFrame(self.equity_curve).set_index("date")
        df.index = pd.to_datetime(df.index)
        return df

    def get_trades_df(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        return pd.DataFrame([vars(t) for t in self.trades])
