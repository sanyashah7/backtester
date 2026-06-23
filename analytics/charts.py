"""
analytics/charts.py
────────────────────
Generates a 4-panel performance report and saves it as a PNG.
"""

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import os


def plot_results(data: pd.DataFrame, equity_df: pd.DataFrame,
                 trades_df: pd.DataFrame, strategy_name: str,
                 ticker: str, output_path: str = "results/backtest_report.png"):

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    fig, axes = plt.subplots(4, 1, figsize=(14, 18),
                             gridspec_kw={"height_ratios": [3, 1.5, 2, 1.5]})
    fig.suptitle(f"Backtest Report — {strategy_name}\n{ticker}", fontsize=15, fontweight="bold")
    fig.patch.set_facecolor("#0f0f0f")
    for ax in axes:
        ax.set_facecolor("#1a1a1a")
        ax.tick_params(colors="white")
        ax.xaxis.label.set_color("white")
        ax.yaxis.label.set_color("white")
        ax.title.set_color("white")
        for spine in ax.spines.values():
            spine.set_edgecolor("#333")

    # ── Panel 1: Price + Indicators + Trades ─────────────────────
    ax1 = axes[0]
    ax1.plot(data.index, data["Close"], color="#aaa", linewidth=1, label="Close")

    if "SMA_Short" in data.columns and "SMA_Long" in data.columns:
        ax1.plot(data.index, data["SMA_Short"], color="#FFDA30", linewidth=1.2, label=f"SMA Short")
        ax1.plot(data.index, data["SMA_Long"],  color="#FF6B35", linewidth=1.2, label=f"SMA Long")

    if "Rolling_Mean" in data.columns:
        ax1.plot(data.index, data["Rolling_Mean"], color="#4FC3F7", linewidth=1.2, label="Rolling Mean")

    # Plot buy/sell markers from trades
    if not trades_df.empty:
        ax1.scatter(pd.to_datetime(trades_df["entry_date"]),
                    trades_df["entry_price"],
                    marker="^", color="#00E676", s=80, zorder=5, label="Buy")
        ax1.scatter(pd.to_datetime(trades_df["exit_date"]),
                    trades_df["exit_price"],
                    marker="v", color="#FF1744", s=80, zorder=5, label="Sell")

    ax1.set_title("Price + Signals", fontsize=11)
    ax1.legend(fontsize=8, facecolor="#222", labelcolor="white")
    ax1.set_ylabel("Price ($)", color="white")

    # ── Panel 2: Z-Score (mean reversion) or SMA diff ────────────
    ax2 = axes[1]
    if "Z_Score" in data.columns:
        ax2.plot(data.index, data["Z_Score"], color="#CE93D8", linewidth=1)
        ax2.axhline(0,    color="#555", linewidth=0.8, linestyle="--")
        ax2.axhline(-1.5, color="#00E676", linewidth=0.8, linestyle="--", label="Entry threshold")
        ax2.axhline(0.5,  color="#FF1744", linewidth=0.8, linestyle="--", label="Exit threshold")
        ax2.set_title("Z-Score", fontsize=11)
        ax2.legend(fontsize=8, facecolor="#222", labelcolor="white")
    elif "SMA_Short" in data.columns:
        diff = data["SMA_Short"] - data["SMA_Long"]
        ax2.fill_between(data.index, diff, 0,
                         where=(diff >= 0), color="#00E676", alpha=0.4, label="Bullish")
        ax2.fill_between(data.index, diff, 0,
                         where=(diff < 0),  color="#FF1744", alpha=0.4, label="Bearish")
        ax2.axhline(0, color="#555", linewidth=0.8)
        ax2.set_title("SMA Spread (Short − Long)", fontsize=11)
        ax2.legend(fontsize=8, facecolor="#222", labelcolor="white")
    ax2.set_ylabel("Value", color="white")

    # ── Panel 3: Equity Curve vs Buy & Hold ──────────────────────
    ax3 = axes[2]
    bh_equity = (data["Close"] / data["Close"].iloc[0]) * equity_df["equity"].iloc[0]
    ax3.plot(equity_df.index, equity_df["equity"], color="#FFDA30", linewidth=1.5, label="Strategy")
    ax3.plot(bh_equity.index, bh_equity.values,   color="#4FC3F7", linewidth=1.2,
             linestyle="--", label="Buy & Hold")
    ax3.set_title("Equity Curve vs Buy & Hold", fontsize=11)
    ax3.legend(fontsize=8, facecolor="#222", labelcolor="white")
    ax3.set_ylabel("Portfolio ($)", color="white")

    # ── Panel 4: Drawdown ─────────────────────────────────────────
    ax4 = axes[3]
    roll_max = equity_df["equity"].cummax()
    drawdown = (equity_df["equity"] - roll_max) / roll_max * 100
    ax4.fill_between(drawdown.index, drawdown, 0, color="#FF1744", alpha=0.6)
    ax4.set_title("Drawdown (%)", fontsize=11)
    ax4.set_ylabel("DD %", color="white")

    for ax in axes:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=7)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"[Charts] Report saved → {output_path}")
