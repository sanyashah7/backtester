"""
paper_trader.py
───────────────
Executes live paper trading on Alpaca using the SMA Crossover strategy.
Runs in a continuous loop during market hours and trades active intraday timeframes.
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
import io
import time
import config
from strategy.sma_crossover import SMACrossover
from flask import Flask
import threading

app = Flask(__name__)

@app.route("/")
def home():
    return "Alpaca Paper Trader is active and running!"

@app.route("/health")
def health():
    return {"status": "healthy"}, 200


# ── Alpaca Credentials & Headers ─────────────────────────────────────────────
HEADERS = {
    "APCA-API-KEY-ID": config.API_KEY,
    "APCA-API-SECRET-KEY": config.SECRET_KEY,
    "Content-Type": "application/json"
}

# ── Trading Settings ─────────────────────────────────────────────────────────
QTY        = 10                  # Number of shares to trade per signal
STRATEGY   = SMACrossover(config.SMA_SHORT, config.SMA_LONG)  # Using SMA Crossover


def get_sp500_tickers() -> list:
    """Scrape S&P 500 stock tickers from Wikipedia."""
    print("[System] Fetching S&P 500 tickers from Wikipedia...")
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            tables = pd.read_html(io.StringIO(r.text))
            df = tables[0]
            tickers = df['Symbol'].tolist()
            # Alpaca uses dots for class shares (e.g. BRK.B)
            tickers = [t for t in tickers]
            print(f"[System] Successfully loaded {len(tickers)} S&P 500 tickers.")
            return tickers
        else:
            print(f"[Warning] Failed to fetch Wikipedia page: HTTP {r.status_code}. Using fallback tickers.")
            return config.TICKERS
    except Exception as e:
        print(f"[Warning] Error fetching S&P 500 tickers: {str(e)}. Using fallback tickers.")
        return config.TICKERS


def is_market_open() -> bool:
    """Query Alpaca Clock API to check if the US stock market is currently open."""
    url = f"{config.APCA_API_BASE_URL}/v2/clock"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            clock_data = response.json()
            is_open = clock_data.get("is_open", False)
            return is_open
        else:
            print(f"[Warning] Failed to fetch market clock status: {response.text}. Defaulting to open.")
            return True
    except Exception as e:
        print(f"[Warning] Error checking market clock: {str(e)}. Defaulting to open.")
        return True


def get_all_positions() -> dict:
    """Fetch all open positions from Alpaca in a single request."""
    url = f"{config.APCA_API_BASE_URL}/v2/positions"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        positions_list = response.json()
        positions = {p["symbol"]: float(p["qty"]) for p in positions_list}
        print(f"[Alpaca] Fetched {len(positions)} active positions.")
        return positions
    else:
        print(f"[Error] Failed to fetch positions: {response.text}")
        return {}


def fetch_alpaca_bars_bulk(tickers: list, timeframe: str, start: str, end: str) -> dict:
    """Download historical daily/intraday bars for a list of tickers from Alpaca in bulk."""
    print(f"[Data] Fetching recent {timeframe} bars for {len(tickers)} tickers in bulk from Alpaca...")
    
    url = f"{config.APCA_API_DATA_URL}/v2/stocks/bars"
    all_bars = {}
    
    # Chunk tickers list into groups of 100 (Alpaca's limit per request)
    chunk_size = 100
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        symbols_str = ",".join(chunk)
        
        params = {
            "symbols": symbols_str,
            "timeframe": timeframe,
            "start": start,
            "end": end,
            "limit": 1000,
            "adjustment": "all"
        }
        
        try:
            response = requests.get(url, headers=HEADERS, params=params)
            if response.status_code == 200:
                data = response.json()
                bars_chunk = data.get("bars", {})
                all_bars.update(bars_chunk)
            else:
                print(f"[Warning] Failed to fetch chunk from Alpaca: {response.text}")
        except Exception as e:
            print(f"[Warning] Error fetching bulk chunk: {str(e)}")
            
    return all_bars


def submit_order(symbol: str, qty: int, side: str):
    """Submit a market order to Alpaca paper trading."""
    url = f"{config.APCA_API_BASE_URL}/v2/orders"
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
        print(f"[Error] Order failed for {symbol}: {response.text}")


def main():
    # Load tickers list
    if config.USE_SP500:
        tickers_list = get_sp500_tickers()
    else:
        tickers_list = config.TICKERS

    print(f"\n{'═'*60}")
    print(f"  ALPACA PAPER TRADER | Tickers Count: {len(tickers_list)} | Strategy: {STRATEGY.name}")
    print(f"  Active Timeframe: {config.INTRADAY_INTERVAL} | Poll Frequency: {config.POLL_INTERVAL_SECONDS}s")
    print(f"{'═'*60}")
    
    print("[System] Active trading loop started. Press Ctrl+C to terminate.")

    # Track the last bar timestamp we executed a trade on for each ticker,
    # to avoid placing multiple orders during the same 5-minute bar.
    last_traded_bar = {}

    while True:
        try:
            # 1. Check if the market is open
            if not is_market_open():
                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [Clock] US stock market is currently CLOSED. Sleeping for 15 minutes...")
                time.sleep(900)  # Sleep 15 minutes
                continue
                
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [Scan] US stock market is OPEN. Running active strategy scan...")
            
            # 2. Fetch latest daily/intraday historical data in bulk to calculate indicators
            # Alpaca's free data feed (IEX) requires a 15-minute delay on queries.
            # We timezone-localize and subtract 16 minutes to avoid "recent SIP data" errors.
            from datetime import timezone
            end_dt = datetime.now(timezone.utc) - timedelta(minutes=16)
            # We download the last 5 days to ensure we have enough bars for the SMA indicators
            start_dt = end_dt - timedelta(days=5)
            
            # Convert start and end times to ISO format required by Alpaca
            start_str = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            end_str = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            
            bulk_bars = fetch_alpaca_bars_bulk(tickers_list, config.INTRADAY_INTERVAL, start_str, end_str)
            
            # 3. Get active positions to prevent sequential API spamming
            positions = get_all_positions()

            for ticker in tickers_list:
                try:
                    # Extract ticker-specific columns from the bulk download data
                    ticker_bars = bulk_bars.get(ticker, [])
                    if not ticker_bars or len(ticker_bars) < config.SMA_LONG:
                        continue
                        
                    df = pd.DataFrame(ticker_bars)
                    df = df.rename(columns={
                        "t": "Date",
                        "o": "Open",
                        "h": "High",
                        "l": "Low",
                        "c": "Close",
                        "v": "Volume"
                    })
                    df["Date"] = pd.to_datetime(df["Date"])
                    df = df.set_index("Date")
                    ticker_df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
                        
                    # 4. Generate signals
                    signals = STRATEGY.generate_signals(ticker_df)
                    
                    latest_date = ticker_df.index[-1]
                    latest_close = float(ticker_df["Close"].iloc[-1])
                    latest_signal = int(signals.iloc[-1])
                    
                    # For 500 stocks, we only log when a transaction signal is active (BUY or SELL)
                    if latest_signal in [1, -1]:
                        # Skip if we already submitted an order for this 5-minute candle
                        if last_traded_bar.get(ticker) == latest_date:
                            continue
                            
                        current_qty = positions.get(ticker, 0.0)
                        
                        if latest_signal == 1:
                            if current_qty < config.MAX_SHARES_PER_TICKER:
                                buy_qty = min(QTY, config.MAX_SHARES_PER_TICKER - current_qty)
                                print(f"[Signal] {ticker}: {latest_date} | Close: ${latest_close:.2f} | Signal: BUY")
                                print(f"[Alpaca] Current position for {ticker}: {current_qty} shares.")
                                submit_order(ticker, int(buy_qty), "buy")
                                last_traded_bar[ticker] = latest_date
                                
                        elif latest_signal == -1:
                            if current_qty > 0:
                                print(f"[Signal] {ticker}: {latest_date} | Close: ${latest_close:.2f} | Signal: SELL")
                                print(f"[Alpaca] Current position for {ticker}: {current_qty} shares.")
                                submit_order(ticker, int(current_qty), "sell")
                                last_traded_bar[ticker] = latest_date
                    
                except Exception as e:
                    print(f"[Error] Failed to process ticker {ticker}: {str(e)}")
                    
            print(f"[Scan] Scan complete. Sleeping for {config.POLL_INTERVAL_SECONDS} seconds...")
            time.sleep(config.POLL_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\n[System] Active trading loop stopped by user.")
            break
        except Exception as e:
            print(f"\n[System Error] Error in trading loop: {str(e)}. Retrying in 60s...")
            time.sleep(60)


if __name__ == "__main__":
    # Start the trading loop in a background thread
    threading.Thread(target=main, daemon=True).start()
    
    # Render provides PORT via environment variable
    import os
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
