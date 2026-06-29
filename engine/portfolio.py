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
    exit_reason: str = "Signal"


class Portfolio:
    def __init__(self, initial_cash: float = 10_000,
                 commission: float = 0.001,
                 slippage:   float = 0.0005,
                 stop_loss_pct: float = None,
                 take_profit_pct: float = None,
                 trailing_stop_pct: float = None):
        self.initial_cash = initial_cash
        self.cash         = initial_cash
        self.commission   = commission
        self.slippage     = slippage

        self.stop_loss_pct     = stop_loss_pct
        self.take_profit_pct   = take_profit_pct
        self.trailing_stop_pct = trailing_stop_pct

        self.position     = 0.0   # shares currently held
        self.entry_price  = 0.0
        self.entry_date   = None
        self.max_price_since_entry = 0.0

        self.equity_curve: List[dict] = []
        self.trades:       List[Trade] = []

    # ──────────────────────────────────────────────────────────────
    def execute(self, date, price: float, signal: int):
        """Process one bar."""
        # 1. Update max price since entry if we are holding a position
        if self.position > 0:
            self.max_price_since_entry = max(self.max_price_since_entry, price)

        # 2. Check risk management exits
        exit_triggered = False
        exit_reason = "Signal"

        if self.position > 0:
            if self.stop_loss_pct is not None and price <= self.entry_price * (1 - self.stop_loss_pct):
                exit_triggered = True
                exit_reason = "Stop Loss"
            elif self.take_profit_pct is not None and price >= self.entry_price * (1 + self.take_profit_pct):
                exit_triggered = True
                exit_reason = "Take Profit"
            elif self.trailing_stop_pct is not None and price <= self.max_price_since_entry * (1 - self.trailing_stop_pct):
                exit_triggered = True
                exit_reason = "Trailing Stop"

        # 3. Handle exit if triggered by risk management
        if exit_triggered:
            fill_price = price * (1 - self.slippage)  # Selling, so slippage reduces exit price
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
                exit_reason = exit_reason,
            ))

            self.cash    += proceeds
            self.position = 0.0

        # 4. Otherwise, handle normal strategy signals
        else:
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
                    self.max_price_since_entry = fill_price

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
                    exit_reason = "Signal",
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
