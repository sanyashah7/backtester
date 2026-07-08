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
from analytics.discord_notifier import notify_backtest_completion


def fetch_spy_regime(start_date: str, end_date: str) -> pd.Series:
    """
    Downloads SPY daily data starting 350 days before start_date,
    computes 200 SMA, and returns a Series of boolean indicating if SPY Close > 200 SMA.
    """
    start_dt = pd.to_datetime(start_date)
    extended_start = (start_dt - pd.Timedelta(days=350)).strftime("%Y-%m-%d")
    try:
        spy_data = fetch_data("SPY", extended_start, end_date, "1d")
        spy_close = spy_data["Close"]
        spy_sma = spy_close.rolling(200).mean()
        spy_bullish = spy_close > spy_sma
        spy_bullish.index = pd.to_datetime(spy_bullish.index).tz_localize(None)
        return spy_bullish.loc[start_date:]
    except Exception as e:
        print(f"[Warning] Failed to fetch/calculate SPY regime for backtesting: {str(e)}. Defaulting to Bullish.")
        idx = pd.date_range(start_date, end_date)
        return pd.Series(True, index=idx)


def run_strategy(data: pd.DataFrame, strategy, label: str, ticker: str, spy_regime: pd.Series = None) -> dict:
    print(f"\n{'─'*55}")
    print(f"  Running: {strategy.name}")
    print(f"{'─'*55}")

    # Work on a copy so each strategy gets a clean DataFrame
    df = data.copy()
    signals = strategy.generate_signals(df)

    if label == "SMA_Crossover":
        # Calculate ATR_14 for SMA_Crossover
        high = df["High"]
        low = df["Low"]
        close = df["Close"]
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df["ATR_14"] = tr.rolling(14).mean()

        portfolio = Portfolio(
            initial_cash      = config.INITIAL_CASH,
            commission        = config.COMMISSION,
            slippage          = config.SLIPPAGE,
            stop_loss_pct     = None,
            take_profit_pct   = None,
            trailing_stop_pct = config.TRAILING_STOP_PCT,
            spy_regime        = spy_regime,
            use_atr_stop      = True
        )
    else:
        portfolio = Portfolio(
            initial_cash      = config.INITIAL_CASH,
            commission        = config.COMMISSION,
            slippage          = config.SLIPPAGE,
            stop_loss_pct     = config.STOP_LOSS_PCT,
            take_profit_pct   = config.TAKE_PROFIT_PCT,
            trailing_stop_pct = config.TRAILING_STOP_PCT,
            spy_regime        = None,
            use_atr_stop      = False
        )

    for date, row in df.iterrows():
        sig = int(signals.loc[date])
        atr_val = row.get("ATR_14", None) if label == "SMA_Crossover" else None
        portfolio.execute(date, float(row["Close"]), sig, atr=atr_val)

    equity_df = portfolio.get_equity_df()
    trades_df = portfolio.get_trades_df()
    metrics   = compute_metrics(equity_df, trades_df, config.INITIAL_CASH)

    # Save chart
    chart_path = f"results/{ticker}_{label}_report.png"
    plot_results(df, equity_df, trades_df, strategy.name, ticker, chart_path)

    # Print trade log (last 5)
    if not trades_df.empty:
        print("\n  Last 5 trades:")
        print(trades_df[["entry_date","exit_date","entry_price","exit_price","pnl","pnl_pct","exit_reason"]]
              .tail(5).to_string(index=False))

    # Print professional summary and alert Discord for SMA Crossover
    if label == "SMA_Crossover":
        print("\n" + "=" * 60)
        print("                 BACKTEST PERFORMANCE SUMMARY                 ")
        print("=" * 60)
        print(f"Ticker:                     {ticker}")
        print(f"Initial Capital:            ${config.INITIAL_CASH:,.2f}")
        print(f"Final Portfolio Value:      ${metrics.get('Final Equity ($)', 0.0):,.2f}")
        print(f"Total Return (%):           {metrics.get('Total Return (%)', 0.0):.2f}%")
        print(f"CAGR (Annualized):          {metrics.get('CAGR (%)', 0.0):.2f}%")
        print(f"Sharpe Ratio:               {metrics.get('Sharpe Ratio', 0.0):.3f}")
        print(f"Maximum Drawdown:           {metrics.get('Max Drawdown (%)', 0.0):.2f}%")
        print(f"Win Rate:                   {metrics.get('Win Rate (%)', 0.0):.2f}%")
        print(f"Profit Factor:              {metrics.get('Profit Factor', 0.0)}")
        print(f"Avg Winning Trade:          ${metrics.get('Avg Win ($)', 0.0):,.2f}")
        print(f"Avg Losing Trade:           ${metrics.get('Avg Loss ($)', 0.0):,.2f}")
        print(f"Number of Trades:           {metrics.get('Total Trades', 0)}")
        print("=" * 60 + "\n")

        try:
            metrics_dict = {
                'Initial Capital': config.INITIAL_CASH,
                'Final Equity ($)': metrics.get('Final Equity ($)', 0.0),
                'Total Return (%)': metrics.get('Total Return (%)', 0.0),
                'CAGR (%)': metrics.get('CAGR (%)', 0.0),
                'Sharpe Ratio': metrics.get('Sharpe Ratio', 0.0),
                'Max Drawdown (%)': metrics.get('Max Drawdown (%)', 0.0),
                'Win Rate (%)': metrics.get('Win Rate (%)', 0.0),
                'Profit Factor': metrics.get('Profit Factor', 0.0),
                'Total Trades': metrics.get('Total Trades', 0)
            }
            notify_backtest_completion(ticker, metrics_dict)
        except Exception as e:
            print(f"[Warning] Failed to send backtest completion notification to Discord: {str(e)}")

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


def get_sp500_tickers() -> list:
    """Load S&P 500 stock tickers from local file."""
    print("[System] Loading S&P 500 tickers from local file data/sp500.txt for backtesting...")
    try:
        with open("data/sp500.txt", "r") as f:
            tickers = [line.strip() for line in f if line.strip()]
        return tickers
    except Exception as e:
        print(f"[Warning] Error reading local S&P 500 file: {str(e)}. Using fallback tickers.")
        return config.TICKERS


def main():
    if config.USE_SP500:
        full_list = get_sp500_tickers()
        tickers_list = full_list[:config.BACKTEST_LIMIT]
        print(f"[System] S&P 500 enabled. Running backtest on the first {len(tickers_list)} tickers to keep it fast.")
    else:
        tickers_list = config.TICKERS

    print(f"\n{'═'*55}")
    print(f"  BACKTESTER  |  Tickers: {tickers_list}  |  {config.START_DATE} → {config.END_DATE}")
    print(f"  Capital: ${config.INITIAL_CASH:,}  |  Commission: {config.COMMISSION*100}%  |  Slippage: {config.SLIPPAGE*100}%")
    print(f"{'═'*55}")

    # Fetch SPY market regime once before the ticker loop
    spy_regime = fetch_spy_regime(config.START_DATE, config.END_DATE)

    for ticker in tickers_list:
        print(f"\n{'═'*55}")
        print(f"  BACKTESTING TICKER: {ticker}")
        print(f"{'═'*55}")
        
        try:
            raw_data = fetch_data(ticker, config.START_DATE, config.END_DATE, config.INTERVAL)

            strategies = {
                "SMA_Crossover":  SMACrossover(
                    short_window            = config.SMA_SHORT,
                    long_window             = config.SMA_LONG,
                    exit_below_fast_sma     = config.EXIT_BELOW_FAST_SMA,
                    use_volume_filter       = config.USE_VOLUME_FILTER,
                    volume_window           = config.VOLUME_MA_WINDOW,
                    volume_multiplier       = config.VOLUME_MULTIPLIER,
                    use_atr_filter          = config.USE_ATR_FILTER,
                    atr_window              = config.ATR_WINDOW,
                    atr_multiplier          = config.ATR_MULTIPLIER,
                    use_price_change_filter = config.USE_PRICE_CHANGE_FILTER,
                    price_change_threshold  = config.PRICE_CHANGE_THRESHOLD
                ),
                "Mean_Reversion": MeanReversion(config.MR_WINDOW,  config.MR_Z_ENTRY, config.MR_Z_EXIT),
            }

            results = {}
            for label, strategy in strategies.items():
                results[label] = run_strategy(raw_data, strategy, label, ticker, spy_regime=spy_regime)

            print_comparison(results)
        except Exception as e:
            print(f"[Error] Backtest failed for ticker {ticker}: {str(e)}")
            
    print("  All charts saved in  ./results/")


if __name__ == "__main__":
    main()
