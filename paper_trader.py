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
STRATEGY   = SMACrossover(config.SMA_SHORT, config.SMA_LONG)  # Using SMA Crossover


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


STATE_FILE = "trade_state.json"


def load_trade_state() -> dict:
    """Load the trade state from a local JSON file."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"[State] Error loading trade state: {str(e)}")
    return {}


def save_trade_state(state: dict):
    """Save the trade state to a local JSON file."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        print(f"[State] Error saving trade state: {str(e)}")


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


def get_positions_detailed() -> dict:
    """Fetch detailed open positions from Alpaca."""
    url = f"{config.APCA_API_BASE_URL}/v2/positions"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            positions_list = response.json()
            return {p["symbol"]: {
                "qty": float(p["qty"]),
                "avg_entry_price": float(p["avg_entry_price"]),
                "current_price": float(p["current_price"]),
                "unrealized_plpc": float(p["unrealized_plpc"])
            } for p in positions_list}
        else:
            print(f"[Alpaca] Failed to fetch detailed positions: {response.text}")
            return {}
    except Exception as e:
        print(f"[Alpaca] Exception when fetching detailed positions: {str(e)}")
        return {}


def should_exit_intraday() -> bool:
    """Check if we are within 15 minutes of market close using Alpaca Clock."""
    url = f"{config.APCA_API_BASE_URL}/v2/clock"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            clock_data = response.json()
            if not clock_data.get("is_open", False):
                return False
            
            timestamp_str = clock_data["timestamp"].replace("Z", "+00:00")
            next_close_str = clock_data["next_close"].replace("Z", "+00:00")
            
            current_time = datetime.fromisoformat(timestamp_str)
            close_time = datetime.fromisoformat(next_close_str)
            
            time_until_close = close_time - current_time
            if timedelta(minutes=0) <= time_until_close <= timedelta(minutes=15):
                print(f"[Clock] Market closes in {time_until_close.seconds // 60} minutes. Intraday exit active.")
                return True
    except Exception as e:
        print(f"[Warning] Error checking intraday close: {str(e)}")
    return False


def close_all_positions():
    """Submit sell orders for all active positions to close them before market close."""
    positions = get_all_positions()
    if not positions:
        print("[Intraday Exit] No active positions to close.")
        return
        
    print(f"[Intraday Exit] Closing all {len(positions)} positions...")
    for ticker, qty in positions.items():
        if qty > 0:
            submit_order(ticker, int(qty), "sell")
            
    # Clear the trade state file
    save_trade_state({})


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
    """Download historical daily/intraday bars for a list of tickers from Alpaca in bulk with pagination."""
    print(f"[Data] Fetching recent {timeframe} bars for {len(tickers)} tickers in bulk from Alpaca...")
    
    url = f"{config.APCA_API_DATA_URL}/v2/stocks/bars"
    all_bars = {}
    
    # Chunk tickers list into groups of 100 (Alpaca's limit per request)
    chunk_size = 100
    total_chunks = (len(tickers) + chunk_size - 1) // chunk_size
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        symbols_str = ",".join(chunk)
        chunk_num = i // chunk_size + 1
        
        print(f"[Data] Fetching chunk {chunk_num}/{total_chunks} ({len(chunk)} tickers)...")
        page_token = None
        
        while True:
            params = {
                "symbols": symbols_str,
                "timeframe": timeframe,
                "start": start,
                "end": end,
                "limit": 10000,
                "adjustment": "all",
                "feed": "iex"
            }
            if page_token:
                params["page_token"] = page_token
                
            try:
                response = requests.get(url, headers=HEADERS, params=params, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    bars_chunk = data.get("bars", {})
                    
                    # Merge chunk bars
                    for sym, bars_list in bars_chunk.items():
                        if sym in all_bars:
                            all_bars[sym].extend(bars_list)
                        else:
                            all_bars[sym] = bars_list
                            
                    page_token = data.get("next_page_token")
                    if not page_token:
                        break
                else:
                    print(f"[Warning] Failed to fetch chunk {chunk_num} from Alpaca: {response.text}")
                    break
            except Exception as e:
                print(f"[Warning] Error fetching bulk chunk {chunk_num}: {str(e)}")
                break
            
    print(f"[Data] Bulk fetch completed. Got bars for {len(all_bars)} / {len(tickers)} tickers.")
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
    last_intraday_exit_date = None

    while True:
        try:
            # 1. Check if the market is open
            if not is_market_open():
                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [Clock] US stock market is currently CLOSED. Sleeping for 15 minutes...")
                time.sleep(900)  # Sleep 15 minutes
                continue
                
            # 2. Check Intraday Exit Window (liquidation near market close)
            current_date = datetime.now().date()
            if should_exit_intraday():
                if last_intraday_exit_date != current_date:
                    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [Intraday Exit] Market close approaching. Initiating closing of all positions...")
                    close_all_positions()
                    last_intraday_exit_date = current_date
                
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [Scan] Skipping strategy scan as market is near close.")
                time.sleep(config.POLL_INTERVAL_SECONDS)
                continue

            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [Scan] US stock market is OPEN. Running active strategy scan...")
            
            # 3. Fetch latest daily/intraday historical data in bulk to calculate indicators
            from datetime import timezone
            end_dt = datetime.now(timezone.utc) - timedelta(minutes=16)
            start_dt = end_dt - timedelta(days=5)
            
            start_str = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            end_str = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            
            bulk_bars = fetch_alpaca_bars_bulk(tickers_list, config.INTRADAY_INTERVAL, start_str, end_str)
            
            # 4. Get detailed positions & sync state
            positions_detailed = get_positions_detailed()
            positions = {t: info["qty"] for t, info in positions_detailed.items()}
            trade_state = load_trade_state()
            
            state_changed = False
            for ticker in list(trade_state.keys()):
                if ticker not in positions_detailed:
                    print(f"[State Cleanup] Removing {ticker} from trade state as it is no longer held in Alpaca.")
                    del trade_state[ticker]
                    state_changed = True
            if state_changed:
                save_trade_state(trade_state)

            # 5. Manage profit target exits on open positions
            for ticker, pos_info in list(positions_detailed.items()):
                qty = pos_info["qty"]
                if qty <= 0:
                    continue
                entry_price = pos_info["avg_entry_price"]
                current_price = pos_info["current_price"]
                pct_change = (current_price - entry_price) / entry_price
                
                if ticker not in trade_state:
                    trade_state[ticker] = {
                        "entry_price": entry_price,
                        "initial_qty": qty,
                        "target1_hit": False
                    }
                    save_trade_state(trade_state)
                    
                state = trade_state[ticker]
                target1_hit = state.get("target1_hit", False)
                
                # Check Target 2 (+4.0%)
                if pct_change >= config.TARGET2 / 100.0:
                    print(f"[Exit] [Target 2] Hit for {ticker} at ${current_price:.2f} (Entry: ${entry_price:.2f}, Gain: {pct_change*100:.2f}%). Selling remaining {qty} shares.")
                    submit_order(ticker, int(qty), "sell")
                    if ticker in trade_state:
                        del trade_state[ticker]
                    save_trade_state(trade_state)
                    # Update local state so entry loop knows we closed it
                    positions_detailed[ticker]["qty"] = 0.0
                    positions[ticker] = 0.0
                    continue
                    
                # Check Target 1 (+2.0%)
                if not target1_hit and pct_change >= config.TARGET1 / 100.0:
                    sell_qty = max(1, int(qty // 2))
                    print(f"[Exit] [Target 1] Hit for {ticker} at ${current_price:.2f} (Entry: ${entry_price:.2f}, Gain: {pct_change*100:.2f}%). Selling 50% ({sell_qty} shares).")
                    submit_order(ticker, sell_qty, "sell")
                    trade_state[ticker]["target1_hit"] = True
                    save_trade_state(trade_state)
                    # Update local state
                    positions_detailed[ticker]["qty"] = qty - sell_qty
                    positions[ticker] = qty - sell_qty
                    continue

            buy_count = 0
            sell_count = 0
            hold_count = 0
            skip_count = 0

            # 6. Check strategy entry and exit signals
            for ticker in tickers_list:
                try:
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
                                if len(positions_detailed) >= config.MAX_PORTFOLIO_SIZE:
                                    print(f"[Scan] Skipping BUY for {ticker} because portfolio limit is reached ({len(positions_detailed)} / {config.MAX_PORTFOLIO_SIZE} positions).")
                                    continue
                                    
                                # Volatility Filter (daily move of at least PRICE_CHANGE_THRESHOLD %)
                                daily_change_pct = 0.0
                                latest_day = latest_date.date()
                                prev_day_bars = ticker_df[ticker_df.index.date < latest_day]
                                if not prev_day_bars.empty:
                                    prev_close = float(prev_day_bars["Close"].iloc[-1])
                                    daily_change_pct = ((latest_close - prev_close) / prev_close) * 100.0
                                else:
                                    first_open = float(ticker_df["Open"].iloc[0])
                                    daily_change_pct = ((latest_close - first_open) / first_open) * 100.0
                                    
                                if daily_change_pct < config.PRICE_CHANGE_THRESHOLD:
                                    print(f"[Filter] Skipping BUY for {ticker} because daily move ({daily_change_pct:.2f}%) is below threshold ({config.PRICE_CHANGE_THRESHOLD}%).")
                                    continue
                                    
                                # Dynamic Equal-Allocation Sizing with 2x Leverage:
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
                                
                                # Record trade state
                                trade_state[ticker] = {
                                    "entry_price": latest_close,
                                    "initial_qty": buy_qty,
                                    "target1_hit": False
                                }
                                save_trade_state(trade_state)
                                
                                # Update local positions
                                positions_detailed[ticker] = {
                                    "qty": buy_qty,
                                    "avg_entry_price": latest_close,
                                    "current_price": latest_close,
                                    "unrealized_plpc": 0.0
                                }
                                positions[ticker] = buy_qty
                                
                        elif latest_signal == -1:
                            sell_count += 1
                            if current_qty > 0:
                                print(f"[Signal] {ticker}: {latest_date} | Close: ${latest_close:.2f} | Signal: SELL")
                                print(f"[Alpaca] Current position for {ticker}: {current_qty} shares.")
                                submit_order(ticker, int(current_qty), "sell")
                                last_traded_bar[ticker] = latest_date
                                
                                # Clean trade state
                                if ticker in trade_state:
                                    del trade_state[ticker]
                                    save_trade_state(trade_state)
                                    
                                if ticker in positions_detailed:
                                    del positions_detailed[ticker]
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
