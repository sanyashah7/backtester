# Modular Backtesting System

A clean, modular Python backtester for stocks and crypto with two built-in trading algorithms.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the backtest (default: AAPL, 2020–2024)
python main.py
```

Results (charts) are saved in the `results/` folder.

---

## Configuration (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `TICKER` | `"AAPL"` | Any Yahoo Finance symbol. Use `"BTC-USD"` for crypto |
| `START_DATE` | `"2020-01-01"` | Backtest start |
| `END_DATE` | `"2024-01-01"` | Backtest end |
| `INITIAL_CASH` | `10000` | Starting capital in USD |
| `COMMISSION` | `0.001` | 0.1% per trade |
| `SLIPPAGE` | `0.0005` | 0.05% price impact |

---

## Algorithms

### 1. SMA Crossover (`strategy/sma_crossover.py`)
**Trend-following.** Computes a fast (20-day) and slow (50-day) Simple Moving Average.
- Fast crosses **above** slow → **BUY**
- Fast crosses **below** slow → **SELL**
- Best in: trending markets (strong bull/bear runs)
- Weak in: choppy/sideways markets (lots of false signals)

### 2. Mean Reversion (`strategy/mean_reversion.py`)
**Counter-trend.** Uses a rolling Z-score to detect when price is statistically cheap.
- Z-score drops below **−1.5** → price is unusually low → **BUY**
- Z-score rises above **+0.5** → price has recovered → **SELL**
- Best in: range-bound, high-noise, mean-reverting assets
- Weak in: strong trending markets (keeps buying falling assets)

---

## Project Structure

```
backtester/
├── config.py                  ← all settings live here
├── main.py                    ← entry point, runs both strategies
├── requirements.txt
│
├── data/
│   └── fetcher.py             ← Yahoo Finance downloader
│
├── strategy/
│   ├── base.py                ← abstract Strategy class
│   ├── sma_crossover.py       ← Algorithm 1
│   └── mean_reversion.py      ← Algorithm 2
│
├── engine/
│   └── portfolio.py           ← order execution, slippage, commission, P&L
│
└── analytics/
    ├── metrics.py             ← Sharpe, drawdown, win rate, Calmar, etc.
    └── charts.py              ← 4-panel dark-mode performance chart
```

---

## Output Metrics

| Metric | What it tells you |
|---|---|
| Total Return (%) | Raw profit/loss vs starting capital |
| Sharpe Ratio | Return per unit of risk (>1 is decent, >2 is great) |
| Max Drawdown (%) | Worst peak-to-trough loss |
| Calmar Ratio | Return / Max Drawdown — risk-adjusted quality |
| Win Rate (%) | % of trades that were profitable |
| Profit Factor | Gross profits / Gross losses (>1 = profitable system) |

---

## Adding Your Own Strategy

1. Create `strategy/my_strategy.py`
2. Subclass `Strategy` from `strategy/base.py`
3. Implement `generate_signals(data) → pd.Series` returning `+1 / -1 / 0`
4. Add it to `main.py` strategies dict

```python
from strategy.my_strategy import MyStrategy
strategies["My_Strategy"] = MyStrategy(param1=..., param2=...)
```
