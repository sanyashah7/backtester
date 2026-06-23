import unittest
import pandas as pd
import numpy as np
from engine.portfolio import Portfolio, Trade
from strategy.sma_crossover import SMACrossover
from strategy.mean_reversion import MeanReversion
from analytics.metrics import compute_metrics

class TestPortfolio(unittest.TestCase):
    def setUp(self):
        # Initialize portfolio with $10,000 cash, 0.1% commission, 0.05% slippage
        self.portfolio = Portfolio(initial_cash=10000.0, commission=0.001, slippage=0.0005)

    def test_initial_state(self):
        self.assertEqual(self.portfolio.cash, 10000.0)
        self.assertEqual(self.portfolio.position, 0.0)
        self.assertEqual(len(self.portfolio.trades), 0)

    def test_buy_execution(self):
        # Simulating a buy signal (1) at price $100.0
        # fill_price = 100.0 * (1 + 0.0005 * 1) = 100.05
        # shares = 10000 // 100.05 = 99.0 shares
        # cost = 99.0 * 100.05 * 1.001 = 9914.85
        self.portfolio.execute("2026-06-01", 100.0, 1)
        
        self.assertEqual(self.portfolio.position, 99.0)
        self.assertAlmostEqual(self.portfolio.entry_price, 100.05)
        self.assertTrue(self.portfolio.cash < 10000.0)

    def test_sell_execution(self):
        # 1. Buy first
        self.portfolio.execute("2026-06-01", 100.0, 1)
        
        # 2. Sell signal (-1) at price $110.0
        # fill_price = 110.0 * (1 + 0.0005 * (-1)) = 110.0 * 0.9995 = 109.945
        # proceeds = 99.0 * 109.945 * (1 - 0.001) = 99.0 * 109.945 * 0.999 = 10873.6599
        # expected final cash = buy_cash + proceeds
        self.portfolio.execute("2026-06-02", 110.0, -1)
        
        self.assertEqual(self.portfolio.position, 0.0)
        self.assertEqual(len(self.portfolio.trades), 1)
        trade = self.portfolio.trades[0]
        self.assertEqual(trade.shares, 99.0)
        self.assertAlmostEqual(trade.entry_price, 100.05)
        self.assertAlmostEqual(trade.exit_price, 109.945)

class TestStrategies(unittest.TestCase):
    def test_sma_crossover_signals(self):
        # Create dummy data: ascending prices from 10 to 100 to force fast SMA > slow SMA
        dates = pd.date_range(start="2026-06-01", periods=10)
        data = pd.DataFrame({"Close": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]}, index=dates)
        
        strategy = SMACrossover(short_window=2, long_window=4)
        signals = strategy.generate_signals(data)
        
        self.assertEqual(len(signals), 10)
        # Fast SMA (2-day) should exceed slow SMA (4-day) as prices rise
        # Once both can be calculated (index >= 3), signal should be 1
        self.assertEqual(signals.iloc[-1], 1)

class TestMetrics(unittest.TestCase):
    def test_metrics_calculation(self):
        equity_df = pd.DataFrame({
            "equity": [10000.0, 10100.0, 10200.0, 10500.0]
        }, index=pd.to_datetime(["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04"]))
        
        trades_df = pd.DataFrame([
            {"pnl": 100.0, "pnl_pct": 1.0},
            {"pnl": 100.0, "pnl_pct": 1.0},
            {"pnl": 300.0, "pnl_pct": 3.0}
        ])
        
        metrics = compute_metrics(equity_df, trades_df, 10000.0)
        self.assertEqual(metrics["Final Equity ($)"], 10500.0)
        self.assertEqual(metrics["Total Return (%)"], 5.0)
        self.assertEqual(metrics["Total Trades"], 3)
        self.assertEqual(metrics["Win Rate (%)"], 100.0)

class TestConfig(unittest.TestCase):
    def test_config_variables(self):
        import config
        self.assertTrue(isinstance(config.TICKERS, list))
        self.assertTrue(len(config.TICKERS) > 0)
        self.assertEqual(config.MAX_SHARES_PER_TICKER, 50)

if __name__ == "__main__":
    unittest.main()
