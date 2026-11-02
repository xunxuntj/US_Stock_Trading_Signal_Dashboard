"""
Automated Test Suite for Quantitative Trading System v3.0 (tests/test_v3_suite.py)
Tests:
1. Data Guard (data integrity, trading calendar, dirty data detection)
2. Signal Guard (canonical layer normalization, zero blind spot exit scans, idempotency)
3. Multi-Broker Aggregation (Tiger + Schwab multi-account consolidation)
4. Reconciliation Engine (position drift detection & order ingestion idempotency)
5. Proactive Notifier (Telegram & Feishu card formatting)
"""

import os
import sys
import unittest
import pandas as pd
import numpy as np

# Ensure root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.sanity.data_guard import validate_dataframe_integrity, is_us_trading_day
from core.sanity.signal_guard import (
    get_canonical_layer, exhaustive_scan_trend_exits,
    is_signal_already_sent, mark_signal_sent
)
from core.broker.base import BrokerType, PositionItem, FilledOrder
from core.broker.mock_connector import MockBrokerConnector
from core.broker.manager import MultiBrokerManager
from core.sync.reconcile_engine import check_position_drift, ingest_broker_orders
from core.notifier.dispatcher import ProactiveNotifier


class TestV3SystemSuite(unittest.TestCase):

    # -------------------------------------------------------------------------
    # DOMAIN 1: Data Sanity & Fault-Tolerance Tests
    # -------------------------------------------------------------------------
    def test_01_data_guard_detects_dirty_and_extreme_data(self):
        # 1. Normal DataFrame
        dates = pd.date_range("2026-01-01", periods=60)
        df_normal = pd.DataFrame({"Close": [100.0 + i for i in range(60)]}, index=dates)
        valid, issues = validate_dataframe_integrity("SPY", df_normal)
        self.assertTrue(valid)
        self.assertEqual(len(issues), 0)

        # 2. DataFrame with NaN Close
        df_nan = df_normal.copy()
        df_nan.iloc[-1, 0] = np.nan
        valid_nan, issues_nan = validate_dataframe_integrity("SPY", df_nan)
        self.assertFalse(valid_nan)
        self.assertTrue(any("Invalid close price" in msg for msg in issues_nan))

        # 3. DataFrame with Zero Price
        df_zero = df_normal.copy()
        df_zero.iloc[-1, 0] = 0.0
        valid_zero, issues_zero = validate_dataframe_integrity("SPY", df_zero)
        self.assertFalse(valid_zero)

        # 4. DataFrame with abnormal jump (> 45%)
        df_jump = df_normal.copy()
        df_jump.iloc[-1, 0] = df_jump.iloc[-2, 0] * 1.55  # 55% jump
        valid_jump, issues_jump = validate_dataframe_integrity("SPY", df_jump)
        self.assertFalse(valid_jump)
        self.assertTrue(any("Abnormal single-day price movement" in msg for msg in issues_jump))

    # -------------------------------------------------------------------------
    # DOMAIN 2: Signal Guard & Zero-Blind-Spot Elimination
    # -------------------------------------------------------------------------
    def test_02_canonical_layer_normalization_prevents_soxx_bug(self):
        # Even if legacy DB had 'TREND' or wrong case recorded, it must resolve to canonical layer!
        self.assertEqual(get_canonical_layer("SOXX", recorded_layer="TREND"), "L1")
        self.assertEqual(get_canonical_layer("soxx", recorded_layer=None), "L1")
        self.assertEqual(get_canonical_layer("SPY", recorded_layer="TREND"), "L1")
        self.assertEqual(get_canonical_layer("QLD", recorded_layer="TREND"), "L2")
        self.assertEqual(get_canonical_layer("DBC", recorded_layer="TREND"), "Non-Equity")
        self.assertEqual(get_canonical_layer("JEPQ", recorded_layer="L0"), "L0")
        self.assertEqual(get_canonical_layer("SGOV", recorded_layer="SGOV"), "SGOV")

    def test_03_exhaustive_exit_scan_catches_trend_bearish_flip(self):
        # Simulate active position where SOXX was tagged as 'TREND'
        positions_df = pd.DataFrame([
            {"ticker": "SOXX", "shares": 18.0, "cost_basis": 554.78, "layer": "TREND"},
            {"ticker": "JEPQ", "shares": 1000.0, "cost_basis": 55.0, "layer": "L0"},
            {"ticker": "QLD", "shares": 100.0, "cost_basis": 90.0, "layer": "L2"},
        ])

        latest_dt = pd.Timestamp("2026-11-02")
        # SOXX has ST_trend = -1 (Bearish flip)
        df_soxx = pd.DataFrame({"Close": [550.0], "ST_trend": [-1]}, index=[latest_dt])
        # QLD has ST_trend = 1, but parent QQQ has ST_trend = -1
        df_qld = pd.DataFrame({"Close": [95.0], "ST_trend": [1]}, index=[latest_dt])
        df_qqq = pd.DataFrame({"Close": [500.0], "ST_trend": [-1]}, index=[latest_dt])
        df_jepq = pd.DataFrame({"Close": [60.0], "ST_trend": [-1]}, index=[latest_dt])

        data_dict = {
            "SOXX": df_soxx,
            "QLD": df_qld,
            "QQQ": df_qqq,
            "JEPQ": df_jepq
        }

        actions, warnings = exhaustive_scan_trend_exits(positions_df, data_dict, latest_dt, "2026-11-02")

        # Must catch SOXX exit (even though layer was 'TREND')!
        soxx_action = [a for a in actions if a["ticker"] == "SOXX"]
        self.assertEqual(len(soxx_action), 1)
        self.assertEqual(soxx_action[0]["action"], "SELL")

        # Must catch QLD exit because parent QQQ turned Bearish (-1)!
        qld_action = [a for a in actions if a["ticker"] == "QLD"]
        self.assertEqual(len(qld_action), 1)
        self.assertEqual(qld_action[0]["action"], "SELL")
        self.assertIn("Parent QQQ SuperTrend turned Bearish", qld_action[0]["reason"])

        # JEPQ (L0) must NEVER trigger exit regardless of ST_trend!
        jepq_action = [a for a in actions if a["ticker"] == "JEPQ"]
        self.assertEqual(len(jepq_action), 0)

    def test_04_signal_deduplication_idempotency(self):
        date_str = "2026-11-02"
        ticker = "TEST_TICKER"
        action = "BUY"

        # Initially not sent
        # Mark as sent
        mark_signal_sent(date_str, ticker, action, target_val=5000.0)
        # Should now be recognized as already sent today
        self.assertTrue(is_signal_already_sent(date_str, ticker, action))

    # -------------------------------------------------------------------------
    # DOMAIN 3: Multi-Broker Ingestion & Reconcile Tests
    # -------------------------------------------------------------------------
    def test_05_multi_broker_position_aggregation(self):
        mgr = MultiBrokerManager(use_mock_if_no_keys=False)

        # Connector 1: Tiger Universal with 10 shares of SPY @ $700
        tiger_conn = MockBrokerConnector(account_id="TIGER_U", account_name="Tiger Universal", broker=BrokerType.TIGER)
        tiger_conn.mock_positions = [
            PositionItem(account_id="TIGER_U", broker=BrokerType.TIGER, ticker="SPY", shares=10.0, cost_basis=700.0, market_price=750.0, market_value=7500.0)
        ]

        # Connector 2: Schwab with 20 shares of SPY @ $730
        schwab_conn = MockBrokerConnector(account_id="SCHWAB_1", account_name="Schwab Main", broker=BrokerType.SCHWAB)
        schwab_conn.mock_positions = [
            PositionItem(account_id="SCHWAB_1", broker=BrokerType.SCHWAB, ticker="SPY", shares=20.0, cost_basis=730.0, market_price=750.0, market_value=15000.0)
        ]

        mgr.register_connector("tiger_u", tiger_conn)
        mgr.register_connector("schwab_1", schwab_conn)

        df_agg = mgr.get_aggregated_positions()
        self.assertEqual(len(df_agg), 1)
        row = df_agg.iloc[0]
        self.assertEqual(row["ticker"], "SPY")
        self.assertEqual(row["shares"], 30.0)
        # Weighted cost: (10*700 + 20*730) / 30 = (7000 + 14600) / 30 = 21600 / 30 = 720.0
        self.assertAlmostEqual(row["cost_basis"], 720.0, places=2)
        self.assertEqual(row["market_value"], 22500.0)

    def test_06_position_drift_detection(self):
        # DB has 18 shares of SOXX
        db_df = pd.DataFrame([{"ticker": "SOXX", "shares": 18.0}])
        # Broker has 19.2 shares of SOXX (e.g. DRIP dividend or new execution)
        broker_df = pd.DataFrame([{"ticker": "SOXX", "shares": 19.2}])

        drift = check_position_drift(db_df, broker_df)
        self.assertTrue(drift.has_drift)
        self.assertEqual(len(drift.drifts), 1)
        self.assertEqual(drift.drifts[0]["ticker"], "SOXX")
        self.assertAlmostEqual(drift.drifts[0]["diff"], 1.2, places=2)

    # -------------------------------------------------------------------------
    # DOMAIN 4: Proactive Notifier Card Tests
    # -------------------------------------------------------------------------
    def test_07_notifier_formats_clear_cards(self):
        notifier = ProactiveNotifier()
        actions = [
            {"ticker": "SOXX", "action": "SELL", "target_val": 10000.0, "shares": 18.0, "reason": "SuperTrend Bearish"}
        ]
        card_text = notifier.format_signal_card_markdown("2026-11-02", nav=132000.0, s5fi_val=48.5, actions=actions)
        self.assertIn("实盘交易指令决策卡", card_text)
        self.assertIn("SOXX", card_text)
        self.assertIn("卖出平仓", card_text)
        self.assertIn("$10,000.00", card_text)


if __name__ == "__main__":
    unittest.main()
