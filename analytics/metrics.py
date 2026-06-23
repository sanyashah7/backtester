"""
analytics/metrics.py
─────────────────────
Computes standard quantitative finance performance metrics.
"""

import numpy as np
import pandas as pd


def compute_metrics(equity_df: pd.DataFrame, trades_df: pd.DataFrame,
                    initial_cash: float, risk_free_rate: float = 0.0) -> dict:
    """
    Parameters
    ----------
    equity_df      : DataFrame with 'equity' column indexed by date
    trades_df      : DataFrame of individual trades
    initial_cash   : starting capital
    risk_free_rate : annualised risk-free rate (default 0 for simplicity)

    Returns
    -------
    dict of performance metrics
    """
    equity  = equity_df["equity"]
    returns = equity.pct_change().dropna()

    total_return = (equity.iloc[-1] / initial_cash - 1) * 100

    # Annualised Sharpe Ratio (daily bars → × √252)
    excess   = returns - risk_free_rate / 252
    sharpe   = (excess.mean() / excess.std()) * np.sqrt(252) if excess.std() > 0 else 0.0

    # Max Drawdown
    roll_max  = equity.cummax()
    drawdown  = (equity - roll_max) / roll_max
    max_dd    = drawdown.min() * 100

    # Calmar Ratio  (total return / |max drawdown|)
    calmar = abs(total_return / max_dd) if max_dd != 0 else 0.0

    # Trade-level stats
    n_trades   = len(trades_df)
    win_rate   = 0.0
    avg_win    = 0.0
    avg_loss   = 0.0
    profit_factor = 0.0

    if n_trades > 0:
        winners      = trades_df[trades_df["pnl"] > 0]
        losers       = trades_df[trades_df["pnl"] <= 0]
        win_rate     = len(winners) / n_trades * 100
        avg_win      = winners["pnl"].mean() if len(winners) > 0 else 0.0
        avg_loss     = losers["pnl"].mean()  if len(losers)  > 0 else 0.0
        gross_profit = winners["pnl"].sum()
        gross_loss   = abs(losers["pnl"].sum())
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    return {
        "Final Equity ($)":    round(equity.iloc[-1], 2),
        "Total Return (%)":    round(total_return, 2),
        "Sharpe Ratio":        round(sharpe, 3),
        "Max Drawdown (%)":    round(max_dd, 2),
        "Calmar Ratio":        round(calmar, 3),
        "Total Trades":        n_trades,
        "Win Rate (%)":        round(win_rate, 2),
        "Avg Win ($)":         round(avg_win, 2),
        "Avg Loss ($)":        round(avg_loss, 2),
        "Profit Factor":       round(profit_factor, 3),
    }
