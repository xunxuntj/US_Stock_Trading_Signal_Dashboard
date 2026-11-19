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

from core.sync.reconcile_engine import check_position_drift, ingest_broker_orders, ingest_broker_cash_transactions
from core.broker.base import CashTransactionItem
from core.sync.metrics import compute_strategy_metrics

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
        import sqlite3
        mem_conn = sqlite3.connect(":memory:")
        date_str = "2026-11-02"
        ticker = "TEST_TICKER"
        action = "BUY"

        # Isolated in-memory DB: zero production portfolio.db mutation
        self.assertFalse(is_signal_already_sent(date_str, ticker, action, conn=mem_conn))
        mark_signal_sent(date_str, ticker, action, target_val=5000.0, conn=mem_conn)
        self.assertTrue(is_signal_already_sent(date_str, ticker, action, conn=mem_conn))
        mem_conn.close()



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



    def test_08_metrics_calculation_and_card_display(self):

        from core.sync.metrics import compute_strategy_metrics

        metrics = compute_strategy_metrics()

        self.assertIn("strat_ret_pct", metrics)

        self.assertIn("strat_cagr", metrics)

        self.assertIn("sharpe", metrics)

        self.assertIn("alpha_pct", metrics)

        self.assertGreater(metrics["strat_ret_pct"], 0)



        notifier = ProactiveNotifier()

        # Test signal card with metrics badge

        card = notifier.format_signal_card_markdown("2026-11-02", nav=150000.0, s5fi_val=50.0, actions=[], metrics=metrics)

        self.assertIn("策略实盘收益", card)

        self.assertIn("夏普", card)



    def test_09_hk_ipo_reconciler_and_kids_settlement(self):

        from core.ipo.tracker import calculate_kid_ipo_settlement, get_dynamic_kids_available_capital

        h_bal, c_bal = get_dynamic_kids_available_capital()

        self.assertGreater(h_bal, 100.0)

        self.assertGreater(c_bal, 100.0)



        # 1. Test Profit Settlement (5x reward)

        win_res = calculate_kid_ipo_settlement(

            ticker_name="TEST_WIN",

            margin_principal_hkd=50000.0,

            net_profit_hkd=2500.0,

            hiro_capital_rmb=h_bal,

            caspar_capital_rmb=c_bal,

            multiplier=5.0

        )

        self.assertEqual(win_res["effective_mult"], 5.0)

        self.assertAlmostEqual(win_res["roi"], 0.05, places=3)

        self.assertGreater(win_res["hiro"]["profit"], 0)

        self.assertEqual(win_res["hiro"]["return_total"], round(h_bal + win_res["hiro"]["profit"], 2))



        # 2. Test Loss Settlement (1x protection)

        loss_res = calculate_kid_ipo_settlement(

            ticker_name="TEST_LOSS",

            margin_principal_hkd=50000.0,

            net_profit_hkd=-500.0,

            hiro_capital_rmb=h_bal,

            caspar_capital_rmb=c_bal,

            multiplier=5.0

        )

        self.assertEqual(loss_res["effective_mult"], 1.0)

        self.assertLess(loss_res["hiro"]["profit"], 0)

        self.assertEqual(loss_res["hiro"]["return_total"], round(h_bal + loss_res["hiro"]["profit"], 2))





    def test_10_xirr_and_macro_wealth_metrics(self):

        from core.sync.macro_metrics import calculate_xirr, compute_macro_wealth_metrics

        import datetime



        # Test standard XIRR: Invest 100k on day 0, invest 10k on day 180, end with 130k on day 365

        d0 = datetime.date(2025, 1, 1)

        d1 = datetime.date(2025, 7, 1)

        d2 = datetime.date(2026, 1, 1)

        cfs = [(d0, -100000.0), (d1, -10000.0), (d2, 130000.0)]

        xirr = calculate_xirr(cfs)

        self.assertGreater(xirr, 15.0)

        self.assertLess(xirr, 25.0)



        # Test compute_macro_wealth_metrics

        res = compute_macro_wealth_metrics(

            total_consolidated_equity=130000.0,

            cash_balance=1000.0,

            vault_balance=500.0,

            initial_capital=100000.0,

            initial_date="2026-01-15",

            hk_ipo_cum=10000.0

        )

        self.assertEqual(res["total_consolidated_equity"], 130000.0)

        self.assertEqual(res["moic_tvpi"], 1.30)

        self.assertEqual(res["cumulative_net_pnl"], 30000.0)

        self.assertGreater(res["mwr_xirr_pct"], 0)



    def test_11_passive_income_and_cashflow_yield(self):

        from core.sync.macro_metrics import compute_macro_wealth_metrics

        import pandas as pd



        positions = pd.DataFrame([

            {"ticker": "JEPQ", "shares": 1261.0, "market_value": 70000.0},

            {"ticker": "SGOV", "shares": 404.0, "market_value": 40600.0},

        ])



        res = compute_macro_wealth_metrics(

            total_consolidated_equity=130000.0,

            cash_balance=500.0,

            vault_balance=1000.0,

            positions_df=positions,

            hk_ipo_cum=11000.0

        )



        # JEPQ: 1261 * 5.04 = ~6355.44

        self.assertAlmostEqual(res["jepq_annual_div"], 1261.0 * 5.04, places=1)

        # SGOV: 404 * 5.20 = ~2100.80

        self.assertAlmostEqual(res["sgov_annual_yield"], 404.0 * 5.20, places=1)

        # Vault: 1000 * 0.045 = 45.0

        self.assertEqual(res["vault_annual_yield"], 45.0)

        # Total annual passive cashflow should be positive and substantial (> 8000 USD)

        self.assertGreater(res["total_annual_passive_cashflow"], 8000.0)

        self.assertGreater(res["monthly_passive_cashflow"], 650.0)

        self.assertGreater(res["cashflow_yield_pct"], 5.0)



    def test_12_two_layer_reconcile_report_formatting(self):

        from core.notifier.dispatcher import ProactiveNotifier

        notifier = ProactiveNotifier()



        accounts = [

            {

                "account_name": "老虎证券 - 综合账户 (638812)",

                "equity": 129760.79,

                "cash": 0.0,

                "market_value": 128977.59,

                "accrued_dividend": 702.82,

                "vault_balance": 80.38,

                "locked_funds": 3.48

            },

            {

                "account_name": "老虎证券 - 环球账户 (U9959007)",

                "equity": 0.0,

                "cash": 0.0,

                "market_value": 0.0

            }

        ]



        macro_m = {

            "total_consolidated_equity": 129760.79,

            "cumulative_net_pnl": 20443.38,

            "moic_tvpi": 1.19,

            "mwr_xirr_pct": 25.4,

            "ytd_pnl": 20443.38,

            "ytd_ret_pct": 18.7,

            "liquidity_buffer_val": 40682.38,

            "liquidity_buffer_pct": 31.3,

            "leverage_status": "未使用杠杆 (负债 $0.00 / 极度安全)",

            "total_annual_passive_cashflow": 8642.50,

            "monthly_passive_cashflow": 720.21,

            "cashflow_yield_pct": 6.66,

            "jepq_annual_div": 6359.17,

            "sgov_annual_yield": 2100.80,

            "vault_annual_yield": 3.62

        }



        strat_m = {

            "strat_ret_pct": 53.05,

            "strat_cagr": 70.96,

            "max_dd_pct": -7.89,

            "curr_dd_pct": -7.89,

            "sharpe": 2.15,

            "spy_ret_pct": 18.5,

            "alpha_pct": 34.55,

            "live_days": 292,

            "start_date": "2026-01-15",

            "start_nav": 99215.41

        }



        res = notifier.dispatch_daily_report(

            date_str="2026-11-03",

            total_equity=129760.79,

            strategy_equity=128977.59,

            hk_ipo_cum=11208.10,

            cash=0.0,

            accounts_detail=accounts,

            drift_summary=[],

            metrics=strat_m,

            macro_metrics=macro_m

        )

        self.assertIn("telegram", res)

        self.assertIn("feishu", res)






    # -------------------------------------------------------------------------
    # DOMAIN 6: Multi-Broker Cash Flow Ingestion & Strategy Ledger Tests
    # -------------------------------------------------------------------------
    def test_13_multi_broker_cash_flow_ingestion_and_twr_unitization(self):
        import sqlite3
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE cash_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            notes TEXT
        )
        ''')
        cursor.execute('''
        CREATE TABLE nav_history (
            date TEXT PRIMARY KEY,
            nav REAL NOT NULL,
            cash REAL NOT NULL,
            jepq_val REAL NOT NULL,
            sgov_val REAL NOT NULL,
            trend_val REAL NOT NULL,
            total_equity REAL,
            strategy_equity REAL,
            hk_pnl_cum REAL,
            high_water_mark REAL,
            drawdown_pct REAL,
            source TEXT
        )
        ''')

        # Ingest cash transactions from Tiger and Schwab
        tx1 = CashTransactionItem(
            transaction_id="tx_tiger_1",
            account_id="638812",
            broker=BrokerType.TIGER,
            date="2026-02-01",
            type="DEPOSIT",
            amount=5000.0,
            description="Tiger Wire Deposit"
        )
        tx2 = CashTransactionItem(
            transaction_id="tx_schwab_1",
            account_id="56169533",
            broker=BrokerType.SCHWAB,
            date="2026-11-04",
            type="DEPOSIT",
            amount=1500.0,
            description="Schwab Wire In"
        )

        num_ingested, details = ingest_broker_cash_transactions([tx1, tx2], conn=conn)
        self.assertEqual(num_ingested, 2)

        # Idempotency check: re-running should ingest 0
        num_ingested_again, _ = ingest_broker_cash_transactions([tx1, tx2], conn=conn)
        self.assertEqual(num_ingested_again, 0)

        # Seed NAV points
        cursor.execute("INSERT INTO nav_history VALUES ('2026-01-15', 100000.0, 0, 0, 0, 0, 100000.0, 100000.0, 0, 100000.0, 0, 'MOCK')")
        cursor.execute("INSERT INTO nav_history VALUES ('2026-02-01', 110000.0, 0, 0, 0, 0, 110000.0, 110000.0, 0, 110000.0, 0, 'MOCK')")
        cursor.execute("INSERT INTO nav_history VALUES ('2026-11-04', 125000.0, 0, 0, 0, 0, 125000.0, 125000.0, 0, 125000.0, 0, 'MOCK')")
        conn.commit()

        strat_m = compute_strategy_metrics(conn=conn)
        self.assertTrue(strat_m['strat_ret_pct'] > 0)
        self.assertTrue('unit_nav' in strat_m)

        conn.close()

    # -------------------------------------------------------------------------
    # DOMAIN 7: Financial-Grade Regression Guards (Token, Sync, Account Schema)
    # -------------------------------------------------------------------------
    def test_14_fetch_supabase_df_preserves_text_and_token_columns(self):
        from unittest.mock import patch, MagicMock
        import database

        mock_rows = [{
            "broker": "SCHWAB",
            "refresh_token": "j78C6Er2SAMPLE_BASE64_TOKEN_123456@",
            "updated_at": "2026-11-18 09:17:29",
            "account": "Charles Schwab (嘉信理财)",
            "category": "STRATEGY_L0",
            "shares": "27.0"
        }]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_rows

        with patch("database.get_supabase_credentials", return_value=("https://example.supabase.co", "fake_key")):
            with patch("httpx.get", return_value=mock_resp):
                df = database.fetch_supabase_df("broker_tokens?broker=eq.SCHWAB")

        self.assertIsNotNone(df)
        self.assertEqual(df.iloc[0]["refresh_token"], "j78C6Er2SAMPLE_BASE64_TOKEN_123456@")
        self.assertEqual(df.iloc[0]["account"], "Charles Schwab (嘉信理财)")
        self.assertEqual(df.iloc[0]["category"], "STRATEGY_L0")
        self.assertEqual(float(df.iloc[0]["shares"]), 27.0)

    def test_15_sync_positions_never_closes_on_auth_error(self):
        from unittest.mock import patch
        import pandas as pd
        from core.sync.reconcile_engine import sync_broker_positions_to_db

        existing_db_pos = pd.DataFrame([
            {"ticker": "SGOV", "shares": 1268.0, "cost_basis": 100.5, "layer": "SGOV", "account": "老虎证券 - 综合账户"},
            {"ticker": "JEPQ", "shares": 27.0, "cost_basis": 54.7, "layer": "L0", "account": "Charles Schwab (嘉信理财)"},
        ])
        partial_broker_df = pd.DataFrame([
            {"ticker": "SGOV", "shares": 1268.0, "cost_basis": 100.5, "layer": "SGOV", "accounts": "老虎证券 - 综合账户"}
        ])

        closed_calls = []
        def fake_update(ticker, shares, cost_basis, layer, account=""):
            if shares == 0.0 and layer == "CLOSED":
                closed_calls.append(ticker)

        with patch("database.get_positions", return_value=existing_db_pos):
            with patch("database.update_position", side_effect=fake_update):
                res = sync_broker_positions_to_db(partial_broker_df, shadow_mode=False, allow_close=False)

        self.assertEqual(res["closed"], [])
        self.assertEqual(closed_calls, [])

    def test_16_schwab_orders_api_includes_to_entered_time_and_attribution(self):
        import datetime
        from unittest.mock import patch, MagicMock
        from core.broker.schwab_connector import SchwabBrokerConnector
        from core.broker.base import BrokerType

        conn = SchwabBrokerConnector(app_key="k", app_secret="s", refresh_token="r", account_number="56169533")
        conn._access_token = "tok"
        conn._token_expires_at = datetime.datetime.now() + datetime.timedelta(minutes=20)
        conn._account_hash = "HASH123"

        captured_urls = []
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{
            "orderId": "999001",
            "orderLegCollection": [{"instrument": {"symbol": "JEPQ"}, "instruction": "BUY"}],
            "orderActivityCollection": [{
                "activityType": "EXECUTION",
                "executionLegs": [{"legId": 1, "quantity": 27.0, "price": 54.7, "time": "2026-11-17T14:37:00+0000"}]
            }]
        }]

        def fake_get(url, headers=None):
            captured_urls.append(url)
            return mock_resp

        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.side_effect = fake_get
            orders = conn.get_filled_orders()

        self.assertEqual(len(captured_urls), 1)
        self.assertIn("fromEnteredTime=", captured_urls[0])
        self.assertIn("toEnteredTime=", captured_urls[0])
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].broker, BrokerType.SCHWAB)
        self.assertEqual(orders[0].ticker, "JEPQ")

    def test_17_record_trade_cloud_payload_includes_account(self):
        import os
        import sqlite3
        import tempfile
        from unittest.mock import patch, MagicMock
        import database

        fd, tmp_db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            c_init = sqlite3.connect(tmp_db)
            c_init.execute("""
                CREATE TABLE trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT, ticker TEXT, action TEXT, shares REAL, price REAL,
                    total_val REAL, fee REAL, pnl REAL, layer TEXT, reason TEXT,
                    category TEXT, is_strategy INTEGER, account TEXT
                )
            """)
            c_init.commit()
            c_init.close()

            posted_payloads = []
            mock_resp = MagicMock()
            mock_resp.status_code = 201

            def fake_post(url, json=None, headers=None, timeout=5.0):
                posted_payloads.append(json)
                return mock_resp

            with patch("database.get_connection", side_effect=lambda: sqlite3.connect(tmp_db)):
                with patch("database.get_supabase_credentials", return_value=("https://example.supabase.co", "fake_key")):
                    with patch("httpx.post", side_effect=fake_post):
                        database.record_trade(
                            "2026-11-17", "JEPQ", "BUY", 27.0, 54.7, 1476.9,
                            layer="L0", reason="API Auto-Sync (SCHWAB)", account=None
                        )

            c_chk = sqlite3.connect(tmp_db)
            row = c_chk.execute("SELECT ticker, account FROM trades").fetchone()
            c_chk.close()
            self.assertEqual(row[0], "JEPQ")
            self.assertEqual(row[1], "Charles Schwab (嘉信理财)")
            self.assertEqual(len(posted_payloads), 1)
            self.assertEqual(posted_payloads[0][0]["account"], "Charles Schwab (嘉信理财)")
        finally:
            if os.path.exists(tmp_db):
                os.remove(tmp_db)

    def test_18_multi_account_same_ticker_isolation(self):
        import os
        import sqlite3
        import tempfile
        from unittest.mock import patch
        import pandas as pd
        import database
        from core.sync.reconcile_engine import check_position_drift, sync_broker_positions_to_db

        fd, tmp_db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            with patch("database.DB_PATH", tmp_db):
                with patch("database.get_connection", side_effect=lambda: sqlite3.connect(tmp_db)):
                    with patch("database.get_supabase_credentials", return_value=(None, None)):
                        database.init_db()
                        broker_df = pd.DataFrame([
                            {"ticker": "WBA.CVR", "shares": 100.0, "cost_basis": 0.5, "layer": "TREND", "account": "老虎证券 - 综合账户"},
                            {"ticker": "WBA.CVR", "shares": 154.0, "cost_basis": 0.53, "layer": "TREND", "account": "老虎证券 - 环球账户"},
                            {"ticker": "JEPQ", "shares": 27.0, "cost_basis": 54.7, "layer": "L0", "account": "Charles Schwab (嘉信理财)"},
                        ])
                        res = sync_broker_positions_to_db(broker_df, shadow_mode=False, allow_close=True)
                        self.assertEqual(len(res["updated"]), 3)

                        c_chk = sqlite3.connect(tmp_db)
                        rows = c_chk.execute("SELECT ticker, shares, account FROM positions ORDER BY account, ticker").fetchall()
                        c_chk.close()
                        self.assertEqual(len(rows), 3)

                        db_df = pd.DataFrame(rows, columns=["ticker", "shares", "account"])
                        drift = check_position_drift(db_df, broker_df)
                        self.assertFalse(drift.has_drift)
        finally:
            if os.path.exists(tmp_db):
                os.remove(tmp_db)

    def test_19_sync_then_ingest_orders_never_doubles_shares(self):
        import os
        import sqlite3
        import tempfile
        from unittest.mock import patch
        import pandas as pd
        import database
        from core.sync.reconcile_engine import sync_broker_positions_to_db, ingest_broker_orders

        fd, tmp_db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            with patch("database.DB_PATH", tmp_db), patch("core.sync.reconcile_engine.DB_PATH", tmp_db):
                with patch("database.get_connection", side_effect=lambda: sqlite3.connect(tmp_db)):
                    with patch("database.get_supabase_credentials", return_value=(None, None)):
                        database.init_db()
                        # Step A: Broker live positions already reflect the 27-share JEPQ fill
                        broker_df = pd.DataFrame([
                            {"ticker": "JEPQ", "shares": 27.0, "cost_basis": 54.7, "layer": "L0", "account": "Charles Schwab (嘉信理财)"}
                        ])
                        sync_broker_positions_to_db(broker_df, shadow_mode=False, allow_close=True)

                        # Step B: Immediately ingest the same-day filled order for 27 shares of JEPQ
                        fill = FilledOrder(
                            order_id="1008693944817_1",
                            account_id="56169533",
                            broker=BrokerType.SCHWAB,
                            ticker="JEPQ",
                            action="BUY",
                            shares=27.0,
                            price=54.7,
                            total_value=1476.9,
                            fee=0.0,
                            filled_at="2026-11-17 14:37:00",
                            status="FILLED"
                        )
                        num_synced, _ = ingest_broker_orders([fill], shadow_mode=False)
                        self.assertEqual(num_synced, 1)

                        # Shares MUST remain 27.0 (NOT doubled to 54.0!)
                        c_chk = sqlite3.connect(tmp_db)
                        pos_rows = c_chk.execute("SELECT ticker, shares, account FROM positions").fetchall()
                        trade_rows = c_chk.execute("SELECT ticker, shares, account FROM trades").fetchall()
                        c_chk.close()
                        self.assertEqual(len(pos_rows), 1)
                        self.assertAlmostEqual(pos_rows[0][1], 27.0, places=4)
                        self.assertEqual(pos_rows[0][2], "Charles Schwab (嘉信理财)")
                        self.assertEqual(len(trade_rows), 1)
                        self.assertEqual(trade_rows[0][2], "Charles Schwab (嘉信理财)")
        finally:
            if os.path.exists(tmp_db):
                os.remove(tmp_db)

    def test_20_tiger_connector_auth_error_reported_by_manager(self):
        from unittest.mock import MagicMock
        from core.broker.tiger_connector import TigerBrokerConnector

        conn = TigerBrokerConnector(account_id="638812", account_name="老虎证券 - 综合账户")
        fake_sdk = MagicMock()
        fake_sdk.get_positions.side_effect = RuntimeError("Tiger gateway timeout")
        conn._client = fake_sdk

        pos = conn.get_positions()
        self.assertEqual(pos, [])
        self.assertIsNotNone(conn.last_auth_error)

        mgr = MultiBrokerManager(use_mock_if_no_keys=False)
        mgr.register_connector("tiger_test", conn)
        warnings = mgr.get_auth_warnings()
        self.assertEqual(len(warnings), 1)
        self.assertIn("老虎证券 - 综合账户", warnings[0])

    def test_21_account_balances_roundtrip(self):
        import os
        import sqlite3
        import tempfile
        from unittest.mock import patch
        import database

        fd, tmp_db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            with patch("database.DB_PATH", tmp_db):
                with patch("database.get_connection", side_effect=lambda: sqlite3.connect(tmp_db)):
                    with patch("database.get_supabase_credentials", return_value=(None, None)):
                        database.init_db()
                        sample_accounts = [
                            {"account_name": "老虎证券 - 综合账户", "broker": "TIGER", "equity": 127878.69, "cash": 325.37, "market_value": 127553.32},
                            {"account_name": "Charles Schwab (嘉信理财)", "broker": "SCHWAB", "equity": 1500.27, "cash": 23.10, "market_value": 1477.17},
                        ]
                        database.save_account_balances(sample_accounts)
                        loaded = database.get_account_balances()
                        self.assertIn("老虎证券 - 综合账户", loaded)
                        self.assertAlmostEqual(loaded["Charles Schwab (嘉信理财)"]["cash"], 23.10, places=2)
                        self.assertAlmostEqual(loaded["老虎证券 - 综合账户"]["cash"], 325.37, places=2)
        finally:
            if os.path.exists(tmp_db):
                os.remove(tmp_db)

    def test_22_signal_engine_uses_data_guard_and_aggregates_multi_account_exits(self):
        from unittest.mock import patch
        import pandas as pd
        import numpy as np
        import signal_engine

        dates = pd.date_range("2026-01-01", periods=60)
        df_spy = pd.DataFrame({
            "Close": [500.0 + i * 0.5 for i in range(60)],
            "EMA200": [480.0] * 60,
            "ST_trend": [1] * 60,
        }, index=dates)
        df_soxx = pd.DataFrame({
            "Close": [200.0 + i * 0.2 for i in range(60)],
            "EMA200": [190.0] * 60,
            "ST_trend": [1] * 59 + [-1],
        }, index=dates)
        # Corrupted QQQ with NaN close on latest bar should be filtered out by Data Guard
        df_qqq_bad = df_spy.copy()
        df_qqq_bad.iloc[-1, df_qqq_bad.columns.get_loc("Close")] = np.nan

        mock_data = {"SPY": df_spy, "SOXX": df_soxx, "QQQ": df_qqq_bad}
        # Multi-account positions holding SOXX in two separate accounts (10 + 15 = 25 shares)
        mock_pos = pd.DataFrame([
            {"ticker": "SOXX", "shares": 10.0, "cost_basis": 200.0, "layer": "TREND", "account": "老虎证券 - 综合账户"},
            {"ticker": "SOXX", "shares": 15.0, "cost_basis": 205.0, "layer": "TREND", "account": "Charles Schwab (嘉信理财)"},
        ])

        with patch("signal_engine.ensure_latest_market_data", return_value=None):
            with patch("signal_engine.be.prepare_data", return_value=mock_data):
                with patch("signal_engine.get_positions", return_value=mock_pos):
                    _, _, _, actions = signal_engine.generate_v229_signals()

        soxx_sells = [a for a in actions if a["ticker"] == "SOXX" and a["action"] == "SELL"]
        self.assertEqual(len(soxx_sells), 1)
        expected_val = 25.0 * float(df_soxx["Close"].iloc[-1])
        self.assertAlmostEqual(soxx_sells[0]["target_val"], expected_val, places=2)
        # Corrupted QQQ must NOT produce any buy/sell action
        self.assertEqual([a for a in actions if a["ticker"] == "QQQ"], [])

    def test_23_supabase_post_retry_recovers_from_transient_503(self):
        from unittest.mock import patch, MagicMock
        import database

        r_503 = MagicMock(status_code=503, text="Service Unavailable")
        r_201 = MagicMock(status_code=201, text="Created")
        calls = {"n": 0}

        def fake_post(url, json=None, headers=None, timeout=10.0):
            calls["n"] += 1
            return r_503 if calls["n"] == 1 else r_201

        with patch("httpx.post", side_effect=fake_post), patch("time.sleep", return_value=None):
            res = database._supabase_post_with_retry("https://example.supabase.co/rest/v1/test", [{"a": 1}], {}, retries=2)

        self.assertEqual(res.status_code, 201)
        self.assertEqual(calls["n"], 2)

    def test_24_schwab_balance_api_error_sets_auth_error_and_no_magic_fallback(self):
        from unittest.mock import patch
        from core.broker.schwab_connector import SchwabBrokerConnector

        conn = SchwabBrokerConnector(app_key="k", app_secret="s", refresh_token="r", account_number="")
        with patch.object(conn, "_ensure_access_token", return_value="valid_token"):
            with patch.object(conn, "_get_account_hash", side_effect=RuntimeError("network timeout")):
                with patch("database.get_cash_transactions", side_effect=RuntimeError("db offline")):
                    bal = conn.get_account_balance()

        self.assertIsNotNone(conn.last_auth_error)
        self.assertIn("network timeout", conn.last_auth_error)
        self.assertEqual(bal.total_equity, 0.0)
        self.assertEqual(bal.account_id, "SCHWAB_UNKNOWN")

if __name__ == "__main__":

    unittest.main()

