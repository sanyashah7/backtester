"""
data/fetcher.py
───────────────
Fetches OHLCV data directly from Alpaca Market Data API.
"""

import requests
import pandas as pd
from datetime import datetime
import config


def fetch_data(ticker: str, start: str, end: str, interval: str = "1d") -> pd.DataFrame:
    """
    Download historical OHLCV data from Alpaca Market Data API.

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
    print(f"[DataFetcher] Downloading {ticker} from Alpaca  {start} → {end}")
    
    # Map interval to Alpaca timeframe
    timeframe = "1Day"
    if interval == "1wk":
        timeframe = "1Week"
    elif interval == "1mo":
        timeframe = "1Month"
        
    # Convert dates to ISO 8601 format required by Alpaca
    start_dt = datetime.strptime(start, "%Y-%m-%d").isoformat() + "Z"
    end_dt = datetime.strptime(end, "%Y-%m-%d").isoformat() + "Z"
    
    url = f"{config.APCA_API_DATA_URL}/v2/stocks/{ticker}/bars"
    headers = {
        "APCA-API-KEY-ID": config.API_KEY,
        "APCA-API-SECRET-KEY": config.SECRET_KEY,
        "Content-Type": "application/json"
    }
    params = {
        "timeframe": timeframe,
        "start": start_dt,
        "end": end_dt,
        "limit": 10000,
        "adjustment": "all"
    }
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code != 200:
        raise ValueError(f"Failed to fetch data from Alpaca for '{ticker}': {response.text}")
        
    data = response.json()
    bars = data.get("bars", [])
    
    if not bars:
        raise ValueError(f"No data returned from Alpaca for ticker '{ticker}'. Check symbol or date range.")
        
    df = pd.DataFrame(bars)
    df = df.rename(columns={
        "t": "Date",
        "o": "Open",
        "h": "High",
        "l": "Low",
        "c": "Close",
        "v": "Volume"
    })
    
    # Set index to Date
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date")
    
    # Select OHLCV columns
    df = df[["Open", "High", "Low", "Close", "Volume"]]
    
    print(f"[DataFetcher] {len(df)} bars loaded  ({df.index[0].date()} → {df.index[-1].date()})")
    return df

