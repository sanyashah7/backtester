# ─────────────────────────────────────────────
#  Alpaca Credentials & Endpoints
# ─────────────────────────────────────────────
import os

API_KEY               = os.getenv("ALPACA_API_KEY", "PKJSFSR5U6TQZWL6X6NXJH7IS6")
SECRET_KEY            = os.getenv("ALPACA_SECRET_KEY", "5TNSrSbGNvDTsrSzRH3vikZGPkmRNoW7GxeinT8McCWY")
APCA_API_BASE_URL     = "https://paper-api.alpaca.markets"
APCA_API_DATA_URL     = "https://data.alpaca.markets"

# ─────────────────────────────────────────────
#  Backtester — Global Configuration
# ─────────────────────────────────────────────

USE_SP500             = True                      # True to trade all S&P 500 stocks, False for list below
TICKERS               = ["AAPL", "MSFT", "NVDA"]  # Fallback stocks if USE_SP500 is False
BACKTEST_LIMIT        = 5                         # Run historical backtests on the first N stocks to keep it fast
MAX_SHARES_PER_TICKER = 50                        # Max shares to hold per ticker (pyramiding limit)
MAX_PORTFOLIO_SIZE    = 10                        # Max unique stocks/positions to hold at once
INTRADAY_INTERVAL     = "5Min"                    # Timeframe for active live trading (e.g. 1Min, 5Min, 15Min)
POLL_INTERVAL_SECONDS = 300                       # How often to check market status/run indicators (5 minutes)
TICKER                = TICKERS[0]                # Fallback for single-asset code if needed
START_DATE    = "2020-01-01"
END_DATE      = "2024-01-01"
INTERVAL      = "1d"            # 1d / 1wk / 1mo  (use "1m" for intraday, last 7 days only)

INITIAL_CASH  = 10_000          # starting portfolio value in USD
COMMISSION    = 0.001           # 0.10 % per trade (both sides)
SLIPPAGE      = 0.0005          # 0.05 % price impact per trade

# ── SMA Crossover parameters ──────────────────
SMA_SHORT             = 20              # fast moving-average window (days)
SMA_LONG              = 50              # slow moving-average window (days)
EXIT_BELOW_FAST_SMA   = True            # Exit when price closes below fast SMA

# ── Risk Management parameters ────────────────
STOP_LOSS_PCT         = 0.025           # 2.5% hard stop-loss (None to disable)
TAKE_PROFIT_PCT       = 0.12            # 12% take-profit (None to disable)
TRAILING_STOP_PCT     = 0.05            # 5% trailing stop-loss (None to disable)

# ── Mean Reversion parameters ─────────────────
MR_WINDOW     = 20              # rolling mean / std look-back window
MR_Z_ENTRY    = -1.5            # z-score threshold to BUY  (price too low)
MR_Z_EXIT     =  0.5            # z-score threshold to SELL (price recovered)

# ── Strategy Entry Filters ────────────────────
USE_VOLUME_FILTER       = False           # Disable Volume filter to allow more trades
VOLUME_MA_WINDOW        = 20              # Window for average volume
VOLUME_MULTIPLIER       = 1.5             # Volume must be >= X times average volume

USE_ATR_FILTER          = False           # Disable ATR filter to allow more trades
ATR_WINDOW              = 14              # Window for ATR calculation
ATR_MULTIPLIER          = 1.0             # Daily range must be >= X times ATR

USE_PRICE_CHANGE_FILTER = True            # Only enter if daily price change is positive/significant
PRICE_CHANGE_THRESHOLD  = 0.50            # Minimum daily price change % (0.5% threshold)

# ── Optimization Parameters ───────────────────
LEVERAGE_MULTIPLIER    = 1.0    # Leverage multiplier for position sizing (e.g. 1.0 for 1x cash only)

