"""
paper_trader.py
───────────────
Executes live paper trading on Alpaca using the SMA Crossover strategy.
Run this script to check for trading signals and execute paper trades.
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
import yfinance as yf

import config
from strategy.sma_crossover import SMACrossover
from strategy.mean_reversion import MeanReversion

import os

# ── Alpaca Paper Trading Credentials ─────────────────────────────────────────
API_KEY          = os.getenv("ALPACA_API_KEY", "PKJSFSR5U6TQZWL6X6NXJH7IS6")
SECRET_KEY       = os.getenv("ALPACA_SECRET_KEY", "5TNSrSbGNvDTsrSzRH3vikZGPkmRNoW7GxeinT8McCWY")
APCA_API_BASE_URL = "https://paper-api.alpaca.markets"

HEADERS = {
    "APCA-API-KEY-ID": API_KEY,
    "APCA-API-SECRET-KEY": SECRET_KEY,
    "Content-Type": "application/json"
}

# ── Trading Settings ─────────────────────────────────────────────────────────
TICKER     = config.TICKER       # e.g., "AAPL"
QTY        = 10                  # Number of shares to trade per signal
STRATEGY   = SMACrossover(config.SMA_SHORT, config.SMA_LONG)  # Using SMA Crossover


def get_current_position(symbol: str) -> float:
    """Check if we already hold a position in the symbol on Alpaca."""
    url = f"{APCA_API_BASE_URL}/v2/positions/{symbol}"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200:
        position_data = response.json()
        qty = float(position_data.get("qty", 0))
        print(f"[Alpaca] Current position for {symbol}: {qty} shares.")
        return qty
    elif response.status_code == 404:
        # 404 means no position exists
        print(f"[Alpaca] No active position for {symbol}.")
        return 0.0
    else:
        print(f"[Error] Failed to fetch position: {response.text}")
        return 0.0


def submit_order(symbol: str, qty: int, side: str):
    """Submit a market order to Alpaca paper trading."""
    url = f"{APCA_API_BASE_URL}/v2/orders"
    data = {
        "symbol": symbol,
        "qty": str(qty),
        "side": side,
        "type": "market",
        "time_in_force": "day"
    }
    
    print(f"[Alpaca] Submitting {side.upper()} order for {qty} shares of {symbol}...")
    response = requests.post(url, headers=HEADERS, json=data)
    
    if response.status_code == 200 or response.status_code == 201:
        order_info = response.json()
        print(f"[Success] Order submitted! ID: {order_info.get('id')}, Status: {order_info.get('status')}")
    else:
        print(f"[Error] Order failed: {response.text}")


def main():
    print(f"\n{'═'*60}")
    print(f"  ALPACA PAPER TRADER | Ticker: {TICKER} | Strategy: {STRATEGY.name}")
    print(f"{'═'*60}")
    
    # 1. Fetch latest daily historical data to calculate indicators
    # We download the last 150 days to ensure we have enough data for the 50-day slow SMA
    end_dt = datetime.today()
    start_dt = end_dt - timedelta(days=150)
    
    print(f"[Data] Fetching recent data from Yahoo Finance...")
    df = yf.download(TICKER, start=start_dt.strftime("%Y-%m-%d"), end=end_dt.strftime("%Y-%m-%d"), progress=False)
    
    if df.empty:
        print("[Error] No data returned from Yahoo Finance.")
        return

    # Flatten columns if multi-index
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # 2. Generate signals
    df_copy = df.copy()
    signals = STRATEGY.generate_signals(df_copy)
    
    latest_date = df_copy.index[-1]
    latest_close = float(df_copy["Close"].iloc[-1])
    latest_signal = int(signals.iloc[-1])
    
    print(f"[Analysis] Latest data date: {latest_date.date()} | Close price: ${latest_close:.2f}")
    print(f"[Analysis] Current strategy signal: {latest_signal} (1 = BUY, -1 = SELL, 0 = HOLD)")
    
    # 3. Fetch current position from Alpaca
    current_qty = get_current_position(TICKER)
    
    # 4. Determine trade execution
    if latest_signal == 1:
        if current_qty == 0:
            submit_order(TICKER, QTY, "buy")
        else:
            print("[Decision] Signal is BUY, but we already hold a position. Holding position.")
            
    elif latest_signal == -1:
        if current_qty > 0:
            # Sell the quantity we currently hold
            submit_order(TICKER, int(current_qty), "sell")
        else:
            print("[Decision] Signal is SELL, but we have no shares to sell. Holding cash.")
            
    else:
        print("[Decision] Signal is neutral (HOLD). No actions taken.")
        
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()
