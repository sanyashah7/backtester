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
import gc
import config
from strategy.sma_crossover import SMACrossover
from analytics.discord_notifier import notify_buy, notify_sell, notify_market_regime
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

# ── Cache for SPY market regime to avoid Yahoo Finance rate limits ───────────
LAST_REGIME_VAL = True
LAST_REGIME_FETCH_TIME = None

# ── Cache for Daily ATR to prevent rate limits ───────────────────────────────
DAILY_ATR_CACHE = {}  # ticker: (atr, timestamp)


def get_daily_atr(ticker: str) -> float:
    """Download daily historical data for the ticker and calculate ATR(14) with caching."""
    global DAILY_ATR_CACHE
    now = datetime.now()
    
    # Check cache (valid for 1 day, since daily ATR only changes once a day)
    if ticker in DAILY_ATR_CACHE:
        cached_atr, cached_time = DAILY_ATR_CACHE[ticker]
        if (now - cached_time).days < 1:
            return cached_atr
            
    try:
        import yfinance as yf
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        })
        ticker_obj = yf.Ticker(ticker, session=session)
        # Download last 60 days of daily data (approx. 40 trading days) to compute ATR(14)
        df = ticker_obj.history(period="60d", interval="1d")
        if len(df) >= 15:
            high = df["High"]
            low = df["Low"]
            close = df["Close"]
            tr1 = high - low
            tr2 = (high - close.shift(1)).abs()
            tr3 = (low - close.shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr_series = tr.rolling(14).mean()
            atr = float(atr_series.iloc[-1])
            
            DAILY_ATR_CACHE[ticker] = (atr, now)
            print(f"[ATR] Calculated Daily ATR(14) for {ticker}: {atr:.2f}")
            return atr
        else:
            print(f"[Warning] Not enough daily data for {ticker} ATR(14). Falling back to 0.0.")
            return 0.0
    except Exception as e:
        print(f"[Error] Failed to calculate daily ATR(14) for {ticker}: {str(e)}")
        return 0.0


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


def check_market_status() -> tuple:
    """Query Alpaca Clock API to check if the US stock market is currently open.
    Returns a tuple (is_open, sleep_seconds_if_closed)."""
    url = f"{config.APCA_API_BASE_URL}/v2/clock"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            clock_data = response.json()
            is_open = clock_data.get("is_open", False)
            if is_open:
                return True, 0
            
            # Calculate dynamic sleep time if market is closed
            next_open_str = clock_data.get("next_open")
            timestamp_str = clock_data.get("timestamp")
            if next_open_str and timestamp_str:
                next_open = pd.to_datetime(next_open_str)
                now = pd.to_datetime(timestamp_str)
                time_to_open = (next_open - now).total_seconds()
                # Sleep for at least 10 seconds and at most 15 minutes (900 seconds)
                sleep_seconds = int(min(900, max(10, time_to_open + 5)))
                return False, sleep_seconds
            return False, 900
        else:
            print(f"[Warning] Failed to fetch market clock status: {response.text}. Defaulting to open.")
            return True, 0
    except Exception as e:
        print(f"[Warning] Error checking market clock: {str(e)}. Defaulting to open.")
        return True, 0



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


CACHED_DF_MAP = {}

def fetch_alpaca_bars_bulk(tickers: list, timeframe: str, start: str, end: str) -> dict:
    """Download historical daily/intraday bars for a list of tickers, using caching for efficiency."""
    global CACHED_DF_MAP
    import yfinance as yf
    
    # Check if we have cache for all tickers
    has_cache = all(t in CACHED_DF_MAP for t in tickers) and len(CACHED_DF_MAP) > 0
    
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
        
    try:
        if not has_cache:
            # Full fetch: last 5 days
            print(f"[Cache] No cache found. Performing full historical fetch (5 days) for {len(tickers)} tickers...")
            start_dt = pd.to_datetime(start)
            df = yf.download(tickers, start=start_dt, interval=yf_interval, threads=20, group_by='ticker')
        else:
            # Incremental fetch: last 1 day (subsequent scans)
            print(f"[Cache] Cache exists. Performing incremental fetch (1 day) for {len(tickers)} tickers...")
            start_dt = datetime.now() - timedelta(days=1)
            df = yf.download(tickers, start=start_dt, interval=yf_interval, threads=20, group_by='ticker')
            
        if df.empty:
            print("[Warning] Yahoo Finance returned empty DataFrame.")
            return {t: [] for t in tickers}
            
        for ticker in tickers:
            try:
                if len(tickers) == 1:
                    ticker_df = df.dropna(how='all')
                else:
                    if ticker in df.columns.get_level_values(0):
                        ticker_df = df[ticker].dropna(how='all')
                    else:
                        continue
                        
                if ticker_df.empty:
                    continue
                    
                # Format to uniform columns
                bars = []
                for dt, row in ticker_df.iterrows():
                    if pd.isna(row["Close"]):
                        continue
                    bars.append({
                        "t": dt,
                        "o": float(row["Open"]),
                        "h": float(row["High"]),
                        "l": float(row["Low"]),
                        "c": float(row["Close"]),
                        "v": int(row["Volume"]) if not pd.isna(row["Volume"]) else 0
                    })
                new_df = pd.DataFrame(bars)
                if new_df.empty:
                    continue
                new_df = new_df.set_index("t")
                
                if ticker in CACHED_DF_MAP:
                    old_df = CACHED_DF_MAP[ticker]
                    combined = pd.concat([old_df, new_df])
                    combined = combined[~combined.index.duplicated(keep='last')].sort_index()
                    CACHED_DF_MAP[ticker] = combined.tail(150)
                else:
                    CACHED_DF_MAP[ticker] = new_df.tail(150)
            except Exception as e:
                print(f"[Warning] Failed to update cache for {ticker}: {str(e)}")
                
    except Exception as e:
        print(f"[Error] Yahoo Finance download failed: {str(e)}")
        
    # Return formatted list of dicts from CACHED_DF_MAP
    result = {}
    for ticker in tickers:
        if ticker in CACHED_DF_MAP:
            cached_df = CACHED_DF_MAP[ticker]
            bars_list = []
            for dt, row in cached_df.iterrows():
                bars_list.append({
                    "t": dt.isoformat(),
                    "o": row["o"],
                    "h": row["h"],
                    "l": row["l"],
                    "c": row["c"],
                    "v": row["v"]
                })
            result[ticker] = bars_list
        else:
            result[ticker] = []
    return result


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


def get_recent_split_factor(ticker: str) -> float:
    """Check if a stock split occurred for ticker in the last 7 days and return cumulative split factor."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        splits = t.splits
        if not splits.empty:
            start_dt = datetime.now() - timedelta(days=7)
            splits.index = splits.index.tz_localize(None)
            recent_splits = splits[splits.index >= start_dt]
            if not recent_splits.empty:
                factor = recent_splits.prod()
                return float(factor)
    except Exception as e:
        print(f"[Warning] Failed to fetch splits for {ticker}: {str(e)}")
    return 1.0


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

    last_regime = None
    last_traded_bar = {}

    while True:
        try:
            # 1. Check if the market is open
            is_open, sleep_secs = check_market_status()
            if not is_open:
                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [Clock] US stock market is currently CLOSED. Sleeping for {sleep_secs/60:.1f} minutes...")
                time.sleep(sleep_secs)
                continue
                
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [Scan] US stock market is OPEN. Running active strategy scan...")
            
            # Fetch daily SPY data to determine market regime (once every 4 hours)
            market_bullish = True
            current_time = datetime.now()
            
            global LAST_REGIME_VAL, LAST_REGIME_FETCH_TIME
            
            should_fetch_spy = (
                LAST_REGIME_FETCH_TIME is None or 
                (current_time - LAST_REGIME_FETCH_TIME).total_seconds() > 14400
            )
            
            if should_fetch_spy:
                try:
                    import yfinance as yf
                    session = requests.Session()
                    session.headers.update({
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
                    })
                    spy = yf.Ticker("SPY", session=session)
                    spy_df = spy.history(period="2y", interval="1d")
                    if len(spy_df) >= 200:
                        spy_close = spy_df["Close"].iloc[-1]
                        spy_200_sma = spy_df["Close"].rolling(200).mean().iloc[-1]
                        market_bullish = spy_close > spy_200_sma
                        LAST_REGIME_VAL = market_bullish
                        LAST_REGIME_FETCH_TIME = current_time
                        print(f"Market regime: {'Bullish' if market_bullish else 'Bearish'} (Updated)")
                    else:
                        print("[Warning] Not enough SPY data for 200-day SMA. Defaulting to previous/fallback.")
                        market_bullish = LAST_REGIME_VAL
                except Exception as e:
                    print(f"[Error] Failed to calculate SPY market regime: {str(e)}. Defaulting to previous/fallback: {LAST_REGIME_VAL}")
                    market_bullish = LAST_REGIME_VAL
            else:
                market_bullish = LAST_REGIME_VAL
                print(f"Market regime: {'Bullish' if market_bullish else 'Bearish'} (Cached)")
                
            # Notify Discord on regime change
            if last_regime is not None and last_regime != market_bullish:
                try:
                    notify_market_regime(market_bullish)
                except Exception as ne:
                    print(f"[Warning] Failed to send market regime notification: {str(ne)}")
            last_regime = market_bullish

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

            # Load tracked position metadata from local JSON file
            position_metadata_file = "position_metadata.json"
            position_metadata = {}
            if os.path.exists(position_metadata_file):
                try:
                    with open(position_metadata_file, "r") as f:
                        position_metadata = json.load(f)
                except Exception as e:
                    print(f"[Warning] Failed to load position_metadata.json: {str(e)}")

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

                        # Check for stock split disequilibrium to avoid phantom stop losses
                        split_factor = get_recent_split_factor(ticker)
                        if split_factor != 1.0:
                            expected_pre_split_entry = latest_close * split_factor
                            if abs(avg_entry - expected_pre_split_entry) / expected_pre_split_entry < 0.15:
                                print(f"[Split Lag Detected] {ticker}: Stock split factor {split_factor} detected, but Alpaca entry price (${avg_entry:.2f}) is not yet adjusted. Skipping risk checks to prevent phantom stop-loss.")
                                continue

                        # Update trailing stop max price
                        current_max = max_prices.get(ticker, avg_entry)
                        
                        # Adjust current_max for split if it's still pre-split
                        if split_factor != 1.0 and current_max > latest_close * 1.5:
                            print(f"[Split Adjustment] {ticker}: Adjusting trailing stop max price from {current_max:.2f} to {current_max / split_factor:.2f}")
                            current_max = current_max / split_factor
                            max_prices[ticker] = current_max

                        current_max = max(current_max, latest_close)
                        max_prices[ticker] = current_max

                        try:
                            with open(max_prices_file, "w") as f:
                                json.dump(max_prices, f)
                        except Exception:
                            pass

                        # Load or initialize position metadata
                        meta = position_metadata.get(ticker, {})
                        initial_atr_stop = meta.get("initial_atr_stop")
                        
                        if initial_atr_stop is None:
                            # Calculate Daily ATR(14) instead of 5-minute ATR
                            latest_atr = get_daily_atr(ticker)
                            if latest_atr <= 0.0:
                                print(f"[Warning] Failed to calculate Daily ATR for existing position {ticker}. Skipping risk check for this cycle.")
                                continue
                                
                            initial_atr_stop = avg_entry - (2 * latest_atr)
                            position_metadata[ticker] = {
                                "entry_price": avg_entry,
                                "entry_atr": latest_atr,
                                "initial_atr_stop": initial_atr_stop,
                                "entry_date": datetime.now().isoformat()
                            }
                            try:
                                with open(position_metadata_file, "w") as f:
                                    json.dump(position_metadata, f)
                            except Exception:
                                pass

                        # Adjust initial_atr_stop for split if split occurred and stop is pre-split
                        if split_factor != 1.0 and initial_atr_stop > latest_close * 1.5:
                            print(f"[Split Adjustment] {ticker}: Adjusting initial ATR stop from {initial_atr_stop:.2f} to {initial_atr_stop / split_factor:.2f}")
                            initial_atr_stop = initial_atr_stop / split_factor
                            position_metadata[ticker]["initial_atr_stop"] = initial_atr_stop
                            try:
                                with open(position_metadata_file, "w") as f:
                                    json.dump(position_metadata, f)
                            except Exception:
                                pass

                        # Check risk exits
                        exit_reason = None
                        if latest_close <= initial_atr_stop:
                            exit_reason = "ATR Stop Loss"
                        elif config.TRAILING_STOP_PCT is not None and latest_close <= current_max * (1 - config.TRAILING_STOP_PCT):
                            exit_reason = "Trailing Stop"

                        if exit_reason:
                            print(f"[Risk Exit] {ticker}: Triggered {exit_reason} at close price ${latest_close:.2f} (Entry: ${avg_entry:.2f}, Stop: ${initial_atr_stop:.2f})")
                            submit_order(ticker, int(qty), "sell")
                            
                            # Calculate PnL for Sell Notification
                            pnl = (latest_close - avg_entry) * qty
                            pnl_pct = (latest_close / avg_entry - 1) * 100.0
                            
                            # Get holding days
                            holding_days = 0
                            entry_date_str = position_metadata.get(ticker, {}).get("entry_date")
                            if entry_date_str:
                                try:
                                    entry_date = datetime.fromisoformat(entry_date_str)
                                    holding_days = (datetime.now() - entry_date).days
                                except Exception:
                                    pass
                                    
                            try:
                                notify_sell(
                                    ticker=ticker,
                                    price=latest_close,
                                    holding_days=holding_days,
                                    exit_reason=exit_reason,
                                    pnl=pnl,
                                    pnl_pct=pnl_pct,
                                    portfolio_value=get_account_equity()
                                )
                            except Exception as ne:
                                print(f"[Warning] Failed to send Discord Sell notification: {str(ne)}")

                            if ticker in max_prices:
                                del max_prices[ticker]
                                try:
                                    with open(max_prices_file, "w") as f:
                                        json.dump(max_prices, f)
                                except Exception:
                                    pass
                                    
                            if ticker in position_metadata:
                                del position_metadata[ticker]
                                try:
                                    with open(position_metadata_file, "w") as f:
                                        json.dump(position_metadata, f)
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
                                # Check Market Regime Filter first!
                                if not market_bullish:
                                    print(f"[Scan] Skipping BUY for {ticker} because market regime is Bearish.")
                                    continue

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
                                    
                                # Calculate Daily ATR(14) instead of 5-minute ATR
                                latest_atr = get_daily_atr(ticker)
                                if latest_atr <= 0.0:
                                    print(f"[Warning] Failed to calculate Daily ATR for {ticker}. Skipping trade.")
                                    continue
                                    
                                print(f"[Signal] {ticker}: {latest_date} | Close: ${latest_close:.2f} | Signal: BUY")
                                print(f"[Alpaca] Target allocation: ${target_value:.2f} ({buy_qty} shares).")
                                submit_order(ticker, buy_qty, "buy")
                                last_traded_bar[ticker] = latest_date
                                
                                initial_atr_stop = latest_close - (2 * latest_atr)

                                # Store position metadata
                                position_metadata[ticker] = {
                                    "entry_price": latest_close,
                                    "entry_atr": latest_atr,
                                    "initial_atr_stop": initial_atr_stop,
                                    "entry_date": datetime.now().isoformat()
                                }
                                try:
                                    with open(position_metadata_file, "w") as f:
                                        json.dump(position_metadata, f)
                                except Exception:
                                    pass

                                print(f"[ATR Stop] {ticker}: Purchased at ${latest_close:.2f}. Initial ATR Stop: ${initial_atr_stop:.2f}")

                                try:
                                    notify_buy(
                                        ticker=ticker,
                                        price=latest_close,
                                        shares=buy_qty,
                                        atr_stop=initial_atr_stop,
                                        portfolio_value=equity
                                    )
                                except Exception as ne:
                                    print(f"[Warning] Failed to send Discord Buy notification: {str(ne)}")

                                # Update positions dictionary
                                positions[ticker] = buy_qty
                                
                        elif latest_signal == -1:
                            sell_count += 1
                            if current_qty > 0:
                                print(f"[Signal] {ticker}: {latest_date} | Close: ${latest_close:.2f} | Signal: SELL")
                                print(f"[Alpaca] Current position for {ticker}: {current_qty} shares.")
                                submit_order(ticker, int(current_qty), "sell")
                                last_traded_bar[ticker] = latest_date
                                
                                # Calculate PnL for Sell Notification
                                avg_entry = positions_detailed.get(ticker, {}).get("avg_entry_price", latest_close)
                                pnl = (latest_close - avg_entry) * current_qty
                                pnl_pct = (latest_close / avg_entry - 1) * 100.0
                                
                                # Get holding days
                                holding_days = 0
                                entry_date_str = position_metadata.get(ticker, {}).get("entry_date")
                                if entry_date_str:
                                    try:
                                        entry_date = datetime.fromisoformat(entry_date_str)
                                        holding_days = (datetime.now() - entry_date).days
                                    except Exception:
                                        pass

                                try:
                                    notify_sell(
                                        ticker=ticker,
                                        price=latest_close,
                                        holding_days=holding_days,
                                        exit_reason="SMA20 crossed below SMA50",
                                        pnl=pnl,
                                        pnl_pct=pnl_pct,
                                        portfolio_value=get_account_equity()
                                    )
                                except Exception as ne:
                                    print(f"[Warning] Failed to send Discord Sell notification: {str(ne)}")

                                # Clean up trailing stop tracking and metadata
                                if ticker in max_prices:
                                    del max_prices[ticker]
                                    try:
                                        with open(max_prices_file, "w") as f:
                                            json.dump(max_prices, f)
                                    except Exception:
                                        pass
                                        
                                if ticker in position_metadata:
                                    del position_metadata[ticker]
                                    try:
                                        with open(position_metadata_file, "w") as f:
                                            json.dump(position_metadata, f)
                                    except Exception:
                                        pass
                                
                                if ticker in positions:
                                    del positions[ticker]
                    
                except Exception as e:
                    print(f"[Error] Failed to process ticker {ticker}: {str(e)}")
                    
            print(f"[Scan] Scan complete. Summary: {buy_count} BUY, {sell_count} SELL, {hold_count} HOLD, {skip_count} skipped.")
            
            # Explicitly clean up memory to prevent Render OOM
            try:
                del bulk_bars
                del positions
                del positions_detailed
            except NameError:
                pass
            gc.collect()

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
