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
                 trailing_stop_pct: float = None,
                 spy_regime = None,
                 use_atr_stop: bool = False):
        self.initial_cash = initial_cash
        self.cash         = initial_cash
        self.commission   = commission
        self.slippage     = slippage

        self.stop_loss_pct     = stop_loss_pct
        self.take_profit_pct   = take_profit_pct
        self.trailing_stop_pct = trailing_stop_pct
        self.spy_regime        = spy_regime
        self.use_atr_stop      = use_atr_stop
        self.initial_atr_stop  = 0.0

        self.position     = 0.0   # shares currently held
        self.entry_price  = 0.0
        self.entry_date   = None
        self.max_price_since_entry = 0.0

        self.equity_curve: List[dict] = []
        self.trades:       List[Trade] = []

    # ──────────────────────────────────────────────────────────────
    def execute(self, date, price: float, signal: int, atr: float = None):
        """Process one bar."""
        # Check market regime for new buys
        is_bullish = True
        if self.spy_regime is not None:
            dt_key = pd.to_datetime(date).tz_localize(None)
            if dt_key in self.spy_regime.index:
                is_bullish = self.spy_regime.loc[dt_key]
            else:
                past_dates = self.spy_regime.index[self.spy_regime.index <= dt_key]
                if not past_dates.empty:
                    is_bullish = self.spy_regime.loc[past_dates[-1]]

        # 1. Update max price since entry if we are holding a position
        if self.position > 0:
            self.max_price_since_entry = max(self.max_price_since_entry, price)

        # 2. Check risk management exits
        exit_triggered = False
        exit_reason = "Signal"

        if self.position > 0:
            if self.use_atr_stop:
                # Trailing stop check (5% trailing stop)
                trailing_stop_price = self.max_price_since_entry * (1 - self.trailing_stop_pct) if self.trailing_stop_pct is not None else 0.0
                effective_stop = self.initial_atr_stop if self.initial_atr_stop is not None else 0.0
                
                if trailing_stop_price > effective_stop:
                    effective_stop = trailing_stop_price
                    current_exit_reason = "Trailing Stop"
                else:
                    current_exit_reason = "ATR Stop"
                    
                if price <= effective_stop:
                    exit_triggered = True
                    exit_reason = current_exit_reason
            else:
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
                # Check Market Regime
                if self.use_atr_stop and not is_bullish:
                    print("Market regime: Bearish\nSkipping new entries")
                    return
                elif self.use_atr_stop:
                    print("Market regime: Bullish\nBuying allowed")

                shares = self.cash // fill_price
                cost   = shares * fill_price * (1 + self.commission)
                if shares > 0 and cost <= self.cash:
                    self.cash        -= cost
                    self.position     = shares
                    self.entry_price  = fill_price
                    self.entry_date   = date
                    self.max_price_since_entry = fill_price

                    # Store entry ATR and initial ATR stop
                    if self.use_atr_stop and atr is not None and not pd.isna(atr):
                        self.entry_atr = atr
                        self.initial_atr_stop = fill_price - (2 * atr)
                        print(f"[{date}] Purchased at ${fill_price:.2f}. Initial ATR Stop: ${self.initial_atr_stop:.2f}")
                    else:
                        self.entry_atr = 0.0
                        self.initial_atr_stop = 0.0

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
