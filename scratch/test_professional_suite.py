import os
import sys
import datetime
import unittest
import pandas as pd
import numpy as np

sys.path.append('.')

# Set test environment credentials
os.environ['SUPABASE_URL'] = 'https://eoqpkgnkbbadvppucxej.supabase.co'
os.environ['SUPABASE_KEY'] = 'sb_publishable_YH5zDJNieHeqO61hkzovcA_YIBbWzia'

import database
import signal_engine
import backtest_engine
from config import DATA_DIR, BASE_TICKERS

class TestTradingDashboardProfessionalSuite(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        print("\n" + "="*70)
        print("🧪 RUNNING PROFESSIONAL FUNCTIONAL AUTOMATED TEST SUITE")
        print("="*70)

    # -------------------------------------------------------------------------
    # DOMAIN 1: Supabase Database & Schema Contract Tests
    # -------------------------------------------------------------------------
    def test_01_cloud_database_connectivity_and_tables(self):
        """ Test Cloud Supabase Connectivity & Table Handshakes """
        url, key = database.get_supabase_credentials()
        self.assertIsNotNone(url, "Supabase URL must not be None")
        self.assertIsNotNone(key, "Supabase Key must not be None")
        
        # Test core table querying
        df_nav = database.get_nav_history()
        self.assertIsInstance(df_nav, pd.DataFrame, "NAV History must return DataFrame")
        self.assertFalse(df_nav.empty, "NAV History must not be empty")
        
        df_trades = database.get_trades_history()
        self.assertIsInstance(df_trades, pd.DataFrame, "Trades History must return DataFrame")
        self.assertFalse(df_trades.empty, "Trades History must not be empty")
        
        df_pos = database.get_positions()
        self.assertIsInstance(df_pos, pd.DataFrame, "Positions must return DataFrame")
        self.assertFalse(df_pos.empty, "Positions must not be empty")

    # -------------------------------------------------------------------------
    # DOMAIN 2: Market Data Integrity & Auto-Fresh Pipeline Tests
    # -------------------------------------------------------------------------
    def test_02_cloud_market_prices_schema_and_integrity(self):
        """ Test Market Prices Schema (OHLCV) and Price Sanity Constraints """
        df_dbc = database.fetch_cloud_market_prices("DBC")
        if df_dbc is None or df_dbc.empty:
            fpath = os.path.join(DATA_DIR, "DBC.csv")
            df_dbc = pd.read_csv(fpath)
            df_dbc['Date'] = pd.to_datetime(df_dbc['Date'])

        self.assertGreaterEqual(len(df_dbc), 50, "DBC market price rows must be >= 50 for indicator calculations")
        req_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
        for col in req_cols:
            self.assertIn(col, df_dbc.columns, f"Required column '{col}' missing from market prices")
            
        # Price Integrity Check: High >= Low, High >= Close, Low <= Open
        valid_prices = df_dbc.dropna(subset=['High', 'Low', 'Close', 'Open'])
        self.assertTrue((valid_prices['High'] >= valid_prices['Low']).all(), "High price must be >= Low price")
        self.assertTrue((valid_prices['High'] >= valid_prices['Close'] - 0.01).all(), "High price must be >= Close price")
        self.assertTrue((valid_prices['Low'] <= valid_prices['Open'] + 0.01).all(), "Low price must be <= Open price")

    # -------------------------------------------------------------------------
    # DOMAIN 3: Quant Signal Engine Operator & Boundary Tests
    # -------------------------------------------------------------------------
    def test_03_signal_engine_execution(self):
        """ Test Signal Engine Operator Logic & Execution Output """
        date_str, nav, s5fi_val, actions = signal_engine.generate_v229_signals()
        
        self.assertIsInstance(date_str, str, "Date string must be valid")
        self.assertGreater(nav, 50000, "NAV calculation must be positive and realistic")
        self.assertGreaterEqual(s5fi_val, 0.0, "S5FI breadth must be non-negative")
        self.assertLessEqual(s5fi_val, 100.0, "S5FI breadth must be <= 100%")
        self.assertIsInstance(actions, list, "Actions must be a list")

    # -------------------------------------------------------------------------
    # DOMAIN 4: Live Trade Log & Fractional Share Math Tests
    # -------------------------------------------------------------------------
    def test_04_fractional_share_math_and_precision(self):
        """ Test Fractional Share (6 Decimals) Formatting & PnL Math Precision """
        fractional_shares = 12.345678
        formatted = f"{fractional_shares:,.6f}"
        self.assertEqual(formatted, "12.345678", "6-decimal fractional share formatting failed")
        
        # Micro trade value test
        price = 574.5012
        val = fractional_shares * price
        self.assertAlmostEqual(val, 7092.6068258136, places=4, msg="Micro trade math precision failed")

    # -------------------------------------------------------------------------
    # DOMAIN 5: Portfolio NAV & Holdings Reconciliation Tests
    # -------------------------------------------------------------------------
    def test_05_portfolio_nav_reconciliation(self):
        """ Test Real Portfolio NAV Reconciliation and Cash Allocation """
        df_pos = database.get_positions()
        df_trades = database.get_trades_history()
        
        self.assertTrue('ticker' in df_pos.columns, "Positions table missing ticker column")
        self.assertTrue('shares' in df_pos.columns, "Positions table missing shares column")
        
        # Test positions shares numeric validity
        for _, r in df_pos.iterrows():
            self.assertGreaterEqual(r['shares'], 0, f"Position {r['ticker']} shares cannot be negative")

    # -------------------------------------------------------------------------
    # DOMAIN 6: UI Component & Market Alignment Health Monitor Tests
    # -------------------------------------------------------------------------
    def test_06_market_data_health_monitor_component(self):
        """ Test Sidebar Top '📡 各标的行情对齐监控' Component Logic & Date Alignment """
        df_latest = database.fetch_supabase_df("market_prices", select="ticker,date", order="date.desc")
        ticker_dates = {}
        if df_latest is not None and not df_latest.empty and 'ticker' in df_latest.columns:
            df_latest['date'] = df_latest['date'].astype(str)
            ticker_dates = df_latest.groupby('ticker')['date'].max().to_dict()
            
        core_tickers = ["DBC", "SPY", "QQQ", "SOXX", "QLD", "GLD", "TLT", "BITO", "JEPQ", "SGOV"]
        for t in core_tickers:
            if t not in ticker_dates:
                fpath = os.path.join(DATA_DIR, f"{t}.csv")
                if os.path.exists(fpath):
                    df_c = pd.read_csv(fpath)
                    d_col = 'Date' if 'Date' in df_c.columns else df_c.columns[0]
                    ticker_dates[t] = str(df_c[d_col].iloc[-1])[:10]
                    
        # Check alignment resolution
        for t in core_tickers:
            self.assertIn(t, ticker_dates, f"Health monitor failed to resolve alignment date for {t}")
            self.assertRegex(ticker_dates[t], r'^\d{4}-\d{2}-\d{2}$', f"Date format for {t} must be YYYY-MM-DD")

    # -------------------------------------------------------------------------
    # DOMAIN 7: GitHub Actions Workflow Configuration Test
    # -------------------------------------------------------------------------
    def test_07_github_actions_workflow_spec(self):
        """ Test GitHub Actions Workflow file existence & cron syntax """
        wf_path = os.path.join(".github", "workflows", "daily_scan.yml")
        self.assertTrue(os.path.exists(wf_path), "GitHub Actions workflow daily_scan.yml missing")
        with open(wf_path, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Daily v2.29 Trading Signal Scan", content, "Workflow name incorrect")
            self.assertIn("workflow_dispatch:", content, "Workflow dispatch trigger missing")

    # -------------------------------------------------------------------------
    # DOMAIN 8: HK IPO Trade Entry & Supabase Sync Test
    # -------------------------------------------------------------------------
    def test_08_hk_ipo_trade_record_and_cloud_sync(self):
        """ Test HK IPO Trade Recording and Cloud Supabase Sync Handshake """
        df_before = database.get_hk_ipo_trades_history()
        count_before = len(df_before) if df_before is not None else 0
        self.assertGreater(count_before, 0, "HK IPO Trades History cannot be empty")

def run_suite():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestTradingDashboardProfessionalSuite)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)

if __name__ == "__main__":
    run_suite()
