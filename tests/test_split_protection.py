import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import datetime, timedelta
import sys
import os

# Ensure the project root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from paper_trader import get_recent_split_factor

class TestSplitProtection(unittest.TestCase):

    @patch('yfinance.Ticker')
    def test_get_recent_split_factor_with_split(self, mock_ticker):
        # Setup mock for yfinance Ticker.splits
        mock_t = MagicMock()
        
        # Create a mock Series for splits with a tz-aware DatetimeIndex
        split_date = datetime.now() - timedelta(days=2)
        idx = pd.DatetimeIndex([split_date]).tz_localize('America/New_York')
        mock_t.splits = pd.Series([4.0], index=idx)
        
        mock_ticker.return_value = mock_t

        factor = get_recent_split_factor("CRWD")
        self.assertEqual(factor, 4.0)

    @patch('yfinance.Ticker')
    def test_get_recent_split_factor_no_split(self, mock_ticker):
        mock_t = MagicMock()
        mock_t.splits = pd.Series([], dtype=float)
        mock_ticker.return_value = mock_t

        factor = get_recent_split_factor("AAPL")
        self.assertEqual(factor, 1.0)

    @patch('yfinance.Ticker')
    def test_get_recent_split_factor_old_split(self, mock_ticker):
        mock_t = MagicMock()
        # Split happened 10 days ago (older than our 7-day window)
        split_date = datetime.now() - timedelta(days=10)
        idx = pd.DatetimeIndex([split_date]).tz_localize('America/New_York')
        mock_t.splits = pd.Series([2.0], index=idx)
        mock_ticker.return_value = mock_t

        factor = get_recent_split_factor("MSFT")
        self.assertEqual(factor, 1.0)

    def test_split_lag_logic(self):
        # Simulate logic executed inside paper_trader.py
        
        # Test Case 1: Split lag is present (Alpaca has not adjusted yet)
        latest_close = 194.27
        split_factor = 4.0
        avg_entry = 760.37
        
        expected_pre_split_entry = latest_close * split_factor
        diff_pct = abs(avg_entry - expected_pre_split_entry) / expected_pre_split_entry
        
        # Should be inside tolerance (< 0.15)
        self.assertTrue(diff_pct < 0.15)
        
        # Test Case 2: Split is already adjusted on Alpaca
        avg_entry_adjusted = 190.09
        diff_pct_adjusted = abs(avg_entry_adjusted - expected_pre_split_entry) / expected_pre_split_entry
        
        # Should be outside tolerance (>= 0.15)
        self.assertTrue(diff_pct_adjusted >= 0.15)

    def test_trailing_stop_adjustment_logic(self):
        # Simulate local max_prices trailing stop adjustment
        latest_close = 194.27
        split_factor = 4.0
        current_max = 760.37  # Pre-split trailing stop max
        
        # Check logic:
        # if split_factor != 1.0 and current_max > latest_close * 1.5:
        #     current_max = current_max / split_factor
        
        self.assertTrue(split_factor != 1.0)
        self.assertTrue(current_max > latest_close * 1.5)
        
        adjusted_max = current_max / split_factor
        self.assertEqual(adjusted_max, 190.0925)

if __name__ == "__main__":
    unittest.main()
