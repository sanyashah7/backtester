"""
data/fetcher.py
───────────────
Fetches OHLCV data directly from Yahoo Finance API.
"""

import pandas as pd
import yfinance as yf

def fetch_data(ticker: str, start: str, end: str, interval: str = "1d") -> pd.DataFrame:
    """
    Download historical OHLCV data from Yahoo Finance API.

    Parameters
    ----------
    ticker   : Asset symbol  e.g. "AAPL", "MSFT"
    start    : start date string     e.g. "2020-01-01"
    end      : end date string       e.g. "2024-01-01"
    interval : bar size              "1d" | "1wk" | "1mo"

    Returns
    -------
    pd.DataFrame with columns: Open, High, Low, Close, Volume
    """
    print(f"[DataFetcher] Downloading {ticker} from Yahoo Finance {start} → {end} (interval={interval})")
    
    # Map interval to Yahoo Finance interval
    yf_interval = interval
    if interval == "1Min" or interval == "1m":
        yf_interval = "1m"
    elif interval == "5Min" or interval == "5m":
        yf_interval = "5m"
    elif interval == "15Min" or interval == "15m":
        yf_interval = "15m"
    elif interval == "1wk":
        yf_interval = "1wk"
    elif interval == "1mo":
        yf_interval = "1mo"
    else:
        yf_interval = "1d"
        
    ticker_obj = yf.Ticker(ticker)
    df = ticker_obj.history(start=start, end=end, interval=yf_interval)
    
    if df.empty:
        raise ValueError(f"No data returned from Yahoo Finance for ticker '{ticker}'. Check symbol or date range.")
        
    # Clean up column names to match the expected format
    df = df.rename(columns={
        "Open": "Open",
        "High": "High",
        "Low": "Low",
        "Close": "Close",
        "Volume": "Volume"
    })
    
    # Select OHLCV columns only
    df = df[["Open", "High", "Low", "Close", "Volume"]]
    
    # Make timezone naive to avoid any matching issues in backtester/plotting
    df.index = df.index.tz_localize(None)
    
    print(f"[DataFetcher] {len(df)} bars loaded  ({df.index[0].date()} → {df.index[-1].date()})")
    return df
