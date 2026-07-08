import requests
from datetime import datetime, timezone, timedelta
import config

def get_et_timestamp() -> str:
    """Returns the current ET time as a formatted string."""
    try:
        from zoneinfo import ZoneInfo
        now_et = datetime.now(ZoneInfo("America/New_York"))
        return now_et.strftime("%Y-%m-%d %H:%M ET")
    except Exception:
        # Fallback to offset approximation (UTC-4) if zoneinfo is not available
        now_utc = datetime.now(timezone.utc)
        now_et = now_utc - timedelta(hours=4)
        return now_et.strftime("%Y-%m-%d %H:%M ET")

def send_discord_message(message: str) -> bool:
    """Sends a text message to Discord via webhook. Catches errors to ensure trading continues."""
    webhook_url = getattr(config, "DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        return False
    try:
        payload = {"content": message}
        response = requests.post(webhook_url, json=payload, timeout=10)
        if response.status_code not in [200, 204]:
            print(f"[Discord Error] Failed to send notification (status {response.status_code}): {response.text}")
            return False
        return True
    except Exception as e:
        print(f"[Discord Exception] Error sending message: {str(e)}")
        return False

def notify_buy(ticker: str, price: float, shares: int, atr_stop: float, portfolio_value: float):
    """Sends a formatted Buy notification to Discord."""
    timestamp = get_et_timestamp()
    message = (
        f"🟢 **BUY**\n\n"
        f"**Ticker:** {ticker}\n"
        f"**Price:** ${price:,.2f}\n"
        f"**Shares:** {shares}\n\n"
        f"**Reason:**\n"
        f"• SMA20 crossed above SMA50\n"
        f"• Momentum filter passed\n"
        f"• SPY above 200-day SMA\n\n"
        f"**ATR Stop:** ${atr_stop:,.2f}\n\n"
        f"**Portfolio Value:** ${portfolio_value:,.2f}\n\n"
        f"*Timestamp: {timestamp}*"
    )
    send_discord_message(message)

def notify_sell(ticker: str, price: float, holding_days: int, exit_reason: str, pnl: float, pnl_pct: float, portfolio_value: float):
    """Sends a formatted Sell notification to Discord."""
    timestamp = get_et_timestamp()
    sign = "+" if pnl >= 0 else ""
    message = (
        f"🔴 **SELL**\n\n"
        f"**Ticker:** {ticker}\n"
        f"**Price:** ${price:,.2f}\n\n"
        f"**Holding Period:** {holding_days} Days\n\n"
        f"**Exit Reason:**\n"
        f"{exit_reason}\n\n"
        f"**Profit:**\n"
        f"{sign}${pnl:,.2f} ({sign}{pnl_pct:.1f}%)\n\n"
        f"**Portfolio Value:**\n"
        f"${portfolio_value:,.2f}\n\n"
        f"*Timestamp: {timestamp}*"
    )
    send_discord_message(message)

def notify_market_regime(bullish: bool):
    """Sends a formatted Market Regime change notification to Discord."""
    timestamp = get_et_timestamp()
    if bullish:
        message = (
            f"📈 **MARKET REGIME**\n\n"
            f"**Bullish**\n\n"
            f"SPY is above the 200-day SMA.\n\n"
            f"New long positions are now allowed.\n\n"
            f"*Timestamp: {timestamp}*"
        )
    else:
        message = (
            f"📉 **MARKET REGIME**\n\n"
            f"**Bearish**\n\n"
            f"SPY is below the 200-day SMA.\n\n"
            f"New long positions are temporarily disabled.\n\n"
            f"*Timestamp: {timestamp}*"
        )
    send_discord_message(message)

def notify_backtest_completion(ticker: str, metrics: dict):
    """Sends a formatted Backtest Completion summary to Discord."""
    timestamp = get_et_timestamp()
    message = (
        f"📊 **SMA BACKTEST COMPLETED ({ticker})**\n\n"
        f"**Initial Capital:** ${metrics.get('Initial Capital', 10000.0):,.2f}\n"
        f"**Final Portfolio Value:** ${metrics.get('Final Equity ($)', 0.0):,.2f}\n"
        f"**Total Return:** {metrics.get('Total Return (%)', 0.0):.2f}%\n"
        f"**CAGR:** {metrics.get('CAGR (%)', 0.0):.2f}%\n"
        f"**Sharpe Ratio:** {metrics.get('Sharpe Ratio', 0.0):.3f}\n"
        f"**Maximum Drawdown:** {metrics.get('Max Drawdown (%)', 0.0):.2f}%\n"
        f"**Win Rate:** {metrics.get('Win Rate (%)', 0.0):.2f}%\n"
        f"**Profit Factor:** {metrics.get('Profit Factor', 0.0)}\n"
        f"**Number of Trades:** {metrics.get('Total Trades', 0)}\n\n"
        f"*Timestamp: {timestamp}*"
    )
    send_discord_message(message)
