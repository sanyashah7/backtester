import unittest
import pandas as pd
from engine.portfolio import Portfolio

class TestNewStrategyFeatures(unittest.TestCase):

    def test_spy_regime_bullish_and_bearish(self):
        # Create a mock spy_regime series
        dates = pd.to_datetime(["2026-06-01", "2026-06-02"])
        spy_regime = pd.Series([True, False], index=dates)

        # Bullish regime test
        portfolio_bullish = Portfolio(initial_cash=10000.0, spy_regime=spy_regime, use_atr_stop=True)
        # Price $100, buy signal (1). Should buy since regime is bullish on 2026-06-01
        portfolio_bullish.execute("2026-06-01", 100.0, 1, atr=2.0)
        self.assertTrue(portfolio_bullish.position > 0)

        # Bearish regime test
        portfolio_bearish = Portfolio(initial_cash=10000.0, spy_regime=spy_regime, use_atr_stop=True)
        # Price $100, buy signal (1). Should NOT buy since regime is bearish on 2026-06-02
        portfolio_bearish.execute("2026-06-02", 100.0, 1, atr=2.0)
        self.assertEqual(portfolio_bearish.position, 0.0)

    def test_atr_stop_loss_trigger(self):
        portfolio = Portfolio(initial_cash=10000.0, use_atr_stop=True)
        # Buy on 2026-06-01 at $100, ATR=5.0
        # fill_price = 100.0 * (1 + 0.0005) = 100.05
        # stop price = 100.05 - 2*5.0 = 90.05
        portfolio.execute("2026-06-01", 100.0, 1, atr=5.0)
        self.assertEqual(portfolio.initial_atr_stop, 90.05)

        # Price drops to $95. Should NOT trigger ATR stop (90.05)
        portfolio.execute("2026-06-02", 95.0, 0)
        self.assertTrue(portfolio.position > 0)

        # Price drops to $90. Should trigger ATR stop (<= 90.05)
        portfolio.execute("2026-06-03", 90.0, 0)
        self.assertEqual(portfolio.position, 0.0)
        self.assertEqual(portfolio.trades[0].exit_reason, "ATR Stop")

    def test_trailing_stop_precedence(self):
        # 5% trailing stop, ATR=5.0
        # Stop Price initially: ATR stop = 100.05 - 10 = 90.05. Trailing stop = 100.05 * 0.95 = 95.0475
        # Since trailing stop is higher than ATR stop, it should hit trailing stop first!
        portfolio = Portfolio(initial_cash=10000.0, trailing_stop_pct=0.05, use_atr_stop=True)
        portfolio.execute("2026-06-01", 100.0, 1, atr=5.0)
        
        # Price drops to $94. Should trigger Trailing Stop (since 94 <= 95.0475)
        portfolio.execute("2026-06-02", 94.0, 0)
        self.assertEqual(portfolio.position, 0.0)
        self.assertEqual(portfolio.trades[0].exit_reason, "Trailing Stop")

    def test_mean_reversion_uses_fixed_stops(self):
        # Mean reversion (use_atr_stop=False).
        # Standard configuration uses stop_loss_pct=0.025 (2.5%) and take_profit_pct=0.12 (12%)
        portfolio = Portfolio(initial_cash=10000.0, stop_loss_pct=0.025, take_profit_pct=0.12, use_atr_stop=False)
        portfolio.execute("2026-06-01", 100.0, 1)

        # Price drops to $98. Stop loss (97.5) not hit yet.
        portfolio.execute("2026-06-02", 98.0, 0)
        self.assertTrue(portfolio.position > 0)

        # Price drops to $97. Stop loss hit!
        portfolio.execute("2026-06-03", 97.0, 0)
        self.assertEqual(portfolio.position, 0.0)
        self.assertEqual(portfolio.trades[0].exit_reason, "Stop Loss")

if __name__ == "__main__":
    unittest.main()
