# ─────────────────────────────────────────────
#  Backtester — Global Configuration
# ─────────────────────────────────────────────

TICKERS               = ["AAPL", "MSFT", "NVDA"]  # Stocks to trade
MAX_SHARES_PER_TICKER = 50                        # Max shares to hold per ticker (pyramiding limit)
TICKER                = TICKERS[0]                # Fallback for single-asset code if needed
START_DATE    = "2020-01-01"
END_DATE      = "2024-01-01"
INTERVAL      = "1d"            # 1d / 1wk / 1mo  (use "1m" for intraday, last 7 days only)

INITIAL_CASH  = 10_000          # starting portfolio value in USD
COMMISSION    = 0.001           # 0.10 % per trade (both sides)
SLIPPAGE      = 0.0005          # 0.05 % price impact per trade

# ── SMA Crossover parameters ──────────────────
SMA_SHORT     = 20              # fast moving-average window (days)
SMA_LONG      = 50              # slow moving-average window (days)

# ── Mean Reversion parameters ─────────────────
MR_WINDOW     = 20              # rolling mean / std look-back window
MR_Z_ENTRY    = -1.5            # z-score threshold to BUY  (price too low)
MR_Z_EXIT     =  0.5            # z-score threshold to SELL (price recovered)
