"""
data/fetcher.py
───────────────
Fetches OHLCV data from Yahoo Finance (free, no API key needed).
Supports stocks, ETFs, indices, and crypto pairs (e.g. BTC-USD).
"""

import yfinance as yf
import pandas as pd


def fetch_data(ticker: str, start: str, end: str, interval: str = "1d") -> pd.DataFrame:
    """
    Download historical OHLCV data.

    Parameters
    ----------
    ticker   : Yahoo Finance symbol  e.g. "AAPL", "BTC-USD", "^GSPC"
    start    : start date string     e.g. "2020-01-01"
    end      : end date string       e.g. "2024-01-01"
    interval : bar size              "1d" | "1wk" | "1mo" | "1h" | "1m"

    Returns
    -------
    pd.DataFrame with columns: Open, High, Low, Close, Volume
    """
    print(f"[DataFetcher] Downloading {ticker}  {start} → {end}  interval={interval}")
    df = yf.download(ticker, start=start, end=end, interval=interval, progress=False, auto_adjust=True)

    if df.empty:
        raise ValueError(f"No data returned for ticker '{ticker}'. Check symbol or date range.")

    # Flatten MultiIndex columns if present (yfinance v0.2+)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.dropna(inplace=True)
    df.index = pd.to_datetime(df.index)

    print(f"[DataFetcher] {len(df)} bars loaded  ({df.index[0].date()} → {df.index[-1].date()})")
    return df
