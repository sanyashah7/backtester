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
import os
import json
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
STRATEGY   = SMACrossover(
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
)


def get_sp500_tickers() -> list:
    """Load S&P 500 stock tickers from local file."""
    print("[System] Loading S&P 500 tickers from local file data/sp500.txt...")
    try:
        with open("data/sp500.txt", "r") as f:
            tickers = [line.strip() for line in f if line.strip()]
        print(f"[System] Successfully loaded {len(tickers)} S&P 500 tickers from local file.")
        return tickers
    except Exception as e:
        print(f"[Warning] Error reading local S&P 500 file: {str(e)}. Using fallback tickers.")
        return config.TICKERS


def is_market_open() -> bool:
    """Query Alpaca Clock API to check if the US stock market is currently open."""
    url = f"{config.APCA_API_BASE_URL}/v2/clock"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
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
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            positions_list = response.json()
            positions = {p["symbol"]: float(p["qty"]) for p in positions_list}
            print(f"[Alpaca] Fetched {len(positions)} active positions.")
            return positions
        else:
            print(f"[Error] Failed to fetch positions: {response.text}")
            return {}
    except Exception as e:
        print(f"[Error] Exception when fetching positions: {str(e)}")
        return {}


def get_all_positions_detailed() -> dict:
    """Fetch open positions with detailed information (qty, avg_entry_price, current_price)."""
    url = f"{config.APCA_API_BASE_URL}/v2/positions"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            positions_list = response.json()
            detailed = {
                p["symbol"]: {
                    "qty": float(p["qty"]),
                    "avg_entry_price": float(p["avg_entry_price"]),
                    "current_price": float(p["current_price"])
                }
                for p in positions_list
            }
            print(f"[Alpaca] Fetched {len(detailed)} detailed positions.")
            return detailed
        else:
            print(f"[Error] Failed to fetch detailed positions: {response.text}")
            return {}
    except Exception as e:
        print(f"[Error] Exception when fetching detailed positions: {str(e)}")
        return {}


def get_account_equity() -> float:
    """Fetch total account equity from Alpaca."""
    url = f"{config.APCA_API_BASE_URL}/v2/account"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            account_data = response.json()
            return float(account_data.get("equity", 100000.0))
        else:
            print(f"[Error] Failed to fetch account: {response.text}")
            return 100000.0
    except Exception as e:
        print(f"[Error] Exception when fetching account: {str(e)}")
        return 100000.0


def fetch_alpaca_bars_bulk(tickers: list, timeframe: str, start: str, end: str) -> dict:
    """Download historical daily/intraday bars for a list of tickers from Yahoo Finance in bulk."""
    import yfinance as yf
    
    # Map timeframe to yfinance interval
    yf_interval = "5m"
    if timeframe == "1Min" or timeframe == "1m":
        yf_interval = "1m"
    elif timeframe == "5Min" or timeframe == "5m":
        yf_interval = "5m"
    elif timeframe == "15Min" or timeframe == "15m":
        yf_interval = "15m"
    elif timeframe == "1Day" or timeframe == "1d":
        yf_interval = "1d"
        
    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)
    
    print(f"[YahooData] Fetching recent {yf_interval} bars for {len(tickers)} tickers in bulk from Yahoo Finance...")
    
    try:
        # Download in bulk
        df = yf.download(tickers, start=start_dt, end=end_dt, interval=yf_interval)
        if df.empty:
            print("[Warning] Yahoo Finance returned empty DataFrame.")
            return {}
            
        all_bars = {}
        for ticker in tickers:
            if ticker in df.columns.get_level_values('Ticker'):
                # Extract the columns for this ticker
                ticker_df = df.xs(ticker, level='Ticker', axis=1).dropna(how='all')
                
                bars = []
                for dt, row in ticker_df.iterrows():
                    if pd.isna(row["Close"]):
                        continue
                    bars.append({
                        "t": dt.isoformat(),
                        "o": float(row["Open"]),
                        "h": float(row["High"]),
                        "l": float(row["Low"]),
                        "c": float(row["Close"]),
                        "v": int(row["Volume"]) if not pd.isna(row["Volume"]) else 0
                    })
                all_bars[ticker] = bars
                
        print(f"[YahooData] Bulk fetch completed. Got bars for {len(all_bars)} / {len(tickers)} tickers.")
        return all_bars
        
    except Exception as e:
        print(f"[Error] Yahoo Finance bulk download failed: {str(e)}")
        return {}


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
    try:
        response = requests.post(url, headers=HEADERS, json=data, timeout=10)
        if response.status_code in [200, 201]:
            order_info = response.json()
            print(f"[Success] Order submitted! ID: {order_info.get('id')}, Status: {order_info.get('status')}")
        else:
            print(f"[Error] Order failed for {symbol}: {response.text}")
    except Exception as e:
        print(f"[Error] Exception during order submission for {symbol}: {str(e)}")


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
            from datetime import timezone
            end_dt = datetime.now(timezone.utc)
            start_dt = end_dt - timedelta(days=5)
            
            start_str = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            end_str = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            
            bulk_bars = fetch_alpaca_bars_bulk(tickers_list, config.INTRADAY_INTERVAL, start_str, end_str)
            
            # Load tracked max prices from local JSON file
            max_prices_file = "max_prices.json"
            max_prices = {}
            if os.path.exists(max_prices_file):
                try:
                    with open(max_prices_file, "r") as f:
                        max_prices = json.load(f)
                except Exception as e:
                    print(f"[Warning] Failed to load max_prices.json: {str(e)}")

            # 3. Get active positions to prevent sequential API spamming
            positions = get_all_positions()
            positions_detailed = get_all_positions_detailed()

            buy_count = 0
            sell_count = 0
            hold_count = 0
            skip_count = 0

            # 4. Check strategy entry and exit signals
            for ticker in tickers_list:
                try:
                    # Extract ticker-specific columns from the bulk download data
                    ticker_bars = bulk_bars.get(ticker, [])
                    if not ticker_bars or len(ticker_bars) < config.SMA_LONG:
                        skip_count += 1
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
                        
                    signals = STRATEGY.generate_signals(ticker_df)
                    
                    latest_date = ticker_df.index[-1]
                    latest_close = float(ticker_df["Close"].iloc[-1])

                    # Check risk exits if position exists
                    if ticker in positions_detailed:
                        pos_info = positions_detailed[ticker]
                        qty = pos_info["qty"]
                        avg_entry = pos_info["avg_entry_price"]

                        # Update trailing stop max price
                        current_max = max_prices.get(ticker, avg_entry)
                        current_max = max(current_max, latest_close)
                        max_prices[ticker] = current_max

                        try:
                            with open(max_prices_file, "w") as f:
                                json.dump(max_prices, f)
                        except Exception:
                            pass

                        # Check risk exits
                        exit_reason = None
                        if config.STOP_LOSS_PCT is not None and latest_close <= avg_entry * (1 - config.STOP_LOSS_PCT):
                            exit_reason = "Stop Loss"
                        elif config.TAKE_PROFIT_PCT is not None and latest_close >= avg_entry * (1 + config.TAKE_PROFIT_PCT):
                            exit_reason = "Take Profit"
                        elif config.TRAILING_STOP_PCT is not None and latest_close <= current_max * (1 - config.TRAILING_STOP_PCT):
                            exit_reason = "Trailing Stop"

                        if exit_reason:
                            print(f"[Risk Exit] {ticker}: Triggered {exit_reason} at close price ${latest_close:.2f} (Entry: ${avg_entry:.2f})")
                            submit_order(ticker, int(qty), "sell")
                            if ticker in max_prices:
                                del max_prices[ticker]
                                try:
                                    with open(max_prices_file, "w") as f:
                                        json.dump(max_prices, f)
                                except Exception:
                                    pass
                            sell_count += 1
                            last_traded_bar[ticker] = latest_date
                            continue

                    signals = STRATEGY.generate_signals(ticker_df)
                    latest_signal = int(signals.iloc[-1])
                    
                    if len(tickers_list) <= 10:
                        sma20 = float(ticker_df["SMA_Short"].iloc[-1])
                        sma50 = float(ticker_df["SMA_Long"].iloc[-1])
                        print(f"  └─ {ticker:<5} | Close: ${latest_close:7.2f} | SMA20: ${sma20:7.2f} | SMA50: ${sma50:7.2f} | Signal: {latest_signal:>2}")

                    if latest_signal == 0:
                        hold_count += 1
                    
                    if latest_signal in [1, -1]:
                        if last_traded_bar.get(ticker) == latest_date:
                            continue
                            
                        current_qty = positions.get(ticker, 0.0)
                        
                        if latest_signal == 1:
                            buy_count += 1
                            if current_qty == 0:
                                # Portfolio size check:
                                if len(positions) >= config.MAX_PORTFOLIO_SIZE:
                                    print(f"[Scan] Skipping BUY for {ticker} because portfolio limit is reached ({len(positions)} / {config.MAX_PORTFOLIO_SIZE} positions).")
                                    continue
                                    
                                # Dynamic Equal-Allocation Sizing:
                                equity = get_account_equity()
                                target_value = (equity / config.MAX_PORTFOLIO_SIZE) * config.LEVERAGE_MULTIPLIER
                                buy_qty = int(target_value // latest_close)
                                
                                if buy_qty < 1:
                                    print(f"[Scan] Skipping BUY for {ticker} because price ${latest_close:.2f} is higher than allocation ${target_value:.2f}.")
                                    continue
                                    
                                print(f"[Signal] {ticker}: {latest_date} | Close: ${latest_close:.2f} | Signal: BUY")
                                print(f"[Alpaca] Target allocation: ${target_value:.2f} ({buy_qty} shares).")
                                submit_order(ticker, buy_qty, "buy")
                                last_traded_bar[ticker] = latest_date
                                
                                # Update positions dictionary
                                positions[ticker] = buy_qty
                                
                        elif latest_signal == -1:
                            sell_count += 1
                            if current_qty > 0:
                                print(f"[Signal] {ticker}: {latest_date} | Close: ${latest_close:.2f} | Signal: SELL")
                                print(f"[Alpaca] Current position for {ticker}: {current_qty} shares.")
                                submit_order(ticker, int(current_qty), "sell")
                                last_traded_bar[ticker] = latest_date
                                
                                # Clean up trailing stop tracking
                                if ticker in max_prices:
                                    del max_prices[ticker]
                                    try:
                                        with open(max_prices_file, "w") as f:
                                            json.dump(max_prices, f)
                                    except Exception:
                                        pass
                                
                                if ticker in positions:
                                    del positions[ticker]
                    
                except Exception as e:
                    print(f"[Error] Failed to process ticker {ticker}: {str(e)}")
                    
            print(f"[Scan] Scan complete. Summary: {buy_count} BUY, {sell_count} SELL, {hold_count} HOLD, {skip_count} skipped.")
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
    port = int(os.getenv("PORT", 5001))
    app.run(host="0.0.0.0", port=port)
