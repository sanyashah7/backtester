"""
main.py
────────
Entry point — runs both strategies and prints a comparison table.
Edit config.py to change ticker, dates, or strategy parameters.
"""

import sys
import pandas as pd

import config
from data.fetcher import fetch_data
from strategy.sma_crossover  import SMACrossover
from strategy.mean_reversion import MeanReversion
from engine.portfolio        import Portfolio
from analytics.metrics       import compute_metrics
from analytics.charts        import plot_results


def run_strategy(data: pd.DataFrame, strategy, label: str, ticker: str) -> dict:
    print(f"\n{'─'*55}")
    print(f"  Running: {strategy.name}")
    print(f"{'─'*55}")

    # Work on a copy so each strategy gets a clean DataFrame
    df = data.copy()
    signals = strategy.generate_signals(df)

    portfolio = Portfolio(
        initial_cash = config.INITIAL_CASH,
        commission   = config.COMMISSION,
        slippage     = config.SLIPPAGE,
    )

    for date, row in df.iterrows():
        sig = int(signals.loc[date])
        portfolio.execute(date, float(row["Close"]), sig)

    equity_df = portfolio.get_equity_df()
    trades_df = portfolio.get_trades_df()
    metrics   = compute_metrics(equity_df, trades_df, config.INITIAL_CASH)

    # Save chart
    chart_path = f"results/{ticker}_{label}_report.png"
    plot_results(df, equity_df, trades_df, strategy.name, ticker, chart_path)

    # Print trade log (last 5)
    if not trades_df.empty:
        print("\n  Last 5 trades:")
        print(trades_df[["entry_date","exit_date","entry_price","exit_price","pnl","pnl_pct"]]
              .tail(5).to_string(index=False))

    return metrics


def print_comparison(results: dict):
    print(f"\n{'═'*60}")
    print("  STRATEGY COMPARISON")
    print(f"{'═'*60}")
    header = f"{'Metric':<25}" + "".join(f"{k:>17}" for k in results)
    print(header)
    print("─" * len(header))
    all_keys = list(list(results.values())[0].keys())
    for key in all_keys:
        row = f"{key:<25}"
        for metrics in results.values():
            val = metrics.get(key, "—")
            row += f"{str(val):>17}"
        print(row)
    print(f"{'═'*60}\n")


def main():
    print(f"\n{'═'*55}")
    print(f"  BACKTESTER  |  {config.TICKERS}  |  {config.START_DATE} → {config.END_DATE}")
    print(f"  Capital: ${config.INITIAL_CASH:,}  |  Commission: {config.COMMISSION*100}%  |  Slippage: {config.SLIPPAGE*100}%")
    print(f"{'═'*55}")

    for ticker in config.TICKERS:
        print(f"\n{'═'*55}")
        print(f"  BACKTESTING TICKER: {ticker}")
        print(f"{'═'*55}")
        
        try:
            raw_data = fetch_data(ticker, config.START_DATE, config.END_DATE, config.INTERVAL)

            strategies = {
                "SMA_Crossover":  SMACrossover(config.SMA_SHORT,   config.SMA_LONG),
                "Mean_Reversion": MeanReversion(config.MR_WINDOW,  config.MR_Z_ENTRY, config.MR_Z_EXIT),
            }

            results = {}
            for label, strategy in strategies.items():
                results[label] = run_strategy(raw_data, strategy, label, ticker)

            print_comparison(results)
        except Exception as e:
            print(f"[Error] Backtest failed for ticker {ticker}: {str(e)}")
            
    print("  All charts saved in  ./results/")


if __name__ == "__main__":
    main()
