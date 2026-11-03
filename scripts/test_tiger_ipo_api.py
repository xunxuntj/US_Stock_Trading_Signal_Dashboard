"""
Diagnostic Test Script for Tiger OpenAPI IPO, Interest, and Fee Data (scripts/test_tiger_ipo_api.py)
Tests whether Tiger OpenAPI provides:
1. HK IPO subscription financing costs and interest
2. Fee details via get_fund_details
3. Transaction details via get_transactions / get_filled_orders
Strictly READ-ONLY. No database or configuration modifications.
"""

import os
import sys
import datetime
import pandas as pd

# Ensure root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.broker.tiger_connector import TigerBrokerConnector


def test_tiger_ipo_capabilities():
    print("=" * 70)
    print("🔍 TIGER OPENAPI IPO, INTEREST & FEE CAPABILITY TEST")
    print("=" * 70)

    tiger_id = os.getenv("TIGER_ID")
    raw_acc = os.getenv("TIGER_ACCOUNT", "")
    pk = os.getenv("TIGER_PRIVATE_KEY_PATH")

    if not tiger_id or not pk:
        print("❌ Tiger credentials not available in environment.")
        return

    # Parse accounts
    accounts = [a.strip() for a in raw_acc.split(",") if a.strip()]
    if not accounts:
        accounts = ["U9959007", "638812"]

    print(f"Testing Tiger ID: {tiger_id} | Accounts: {accounts}\n")

    for acc in accounts:
        print(f"\n{'='*30} Testing Account: {acc} {'='*30}")
        connector = TigerBrokerConnector(account_id=acc, account_name=f"Tiger ({acc})")
        if not connector.is_live_connected():
            print(f"⚠️ Could not connect to Tiger for account {acc}")
            continue

        client = connector._client

        # ---------------------------------------------------------------------
        # TEST 1: get_fund_details (资金流水明细: 费用、利息、入金出金)
        # ---------------------------------------------------------------------
        print("\n--- [1] Testing get_fund_details (Fund details & fees) ---")
        try:
            # Query FEE fund details
            res_fee = client.get_fund_details(seg_types=['SEC'], account=acc, fund_type='FEE', limit=20)
            if res_fee is not None and not res_fee.empty:
                print(f"✅ Found {len(res_fee)} FEE records for {acc}:")
                print(f"Columns: {res_fee.columns.tolist()}")
                print(res_fee[['currency', 'amount', 'trans_type', 'updated_at', 'description']].head(10) if 'description' in res_fee.columns else res_fee.head(5))
            else:
                print(f"ℹ️ No FEE records returned for {acc} (or empty).")
        except Exception as e:
            print(f"⚠️ get_fund_details (FEE) call failed: {e}")

        try:
            # Query ALL fund details
            res_all = client.get_fund_details(seg_types=['SEC'], account=acc, fund_type='ALL', limit=10)
            if res_all is not None and not res_all.empty:
                print(f"✅ Found {len(res_all)} ALL records for {acc}:")
                print(f"Columns: {res_all.columns.tolist()}")
                print(res_all.head(5))
            else:
                print(f"ℹ️ No general fund details records returned.")
        except Exception as e:
            print(f"⚠️ get_fund_details (ALL) call failed: {e}")

        # ---------------------------------------------------------------------
        # TEST 2: get_transactions (订单成交费用与明细)
        # ---------------------------------------------------------------------
        print("\n--- [2] Testing get_transactions ---")
        try:
            txs = client.get_transactions(account=acc, limit=20)
            if txs:
                print(f"✅ Found {len(txs)} transaction records for {acc}:")
                for t in txs[:5]:
                    print(f"  Tx: {t}")
            else:
                print(f"ℹ️ No transactions returned.")
        except Exception as e:
            print(f"⚠️ get_transactions call failed: {e}")

        # ---------------------------------------------------------------------
        # TEST 3: get_filled_orders for HK & US stocks (查看是否有港股成交及费用)
        # ---------------------------------------------------------------------
        print("\n--- [3] Testing get_filled_orders (Historical executions & commission) ---")
        try:
            orders = client.get_filled_orders(
                account=acc,
                start_date="2026-01-01",
                end_date=datetime.date.today().strftime("%Y-%m-%d"),
                limit=100
            )
            if orders:
                print(f"✅ Found {len(orders)} filled orders for {acc}:")
                hk_orders = []
                us_orders = []
                for o in orders:
                    sym = getattr(o.contract, 'symbol', '') if hasattr(o, 'contract') else ''
                    mkt = getattr(o.contract, 'market', '') if hasattr(o, 'contract') else ''
                    sec_type = getattr(o.contract, 'sec_type', '') if hasattr(o, 'contract') else ''
                    comm = getattr(o, 'commission', None)
                    pnl = getattr(o, 'realized_pnl', None)
                    action = getattr(o, 'action', '')
                    filled_qty = getattr(o, 'filled', 0)
                    fill_p = getattr(o, 'avg_fill_price', 0)
                    time_val = getattr(o, 'trade_time', getattr(o, 'order_time', ''))

                    order_info = {
                        "symbol": sym, "market": mkt, "sec_type": sec_type,
                        "action": action, "qty": filled_qty, "price": fill_p,
                        "commission": comm, "realized_pnl": pnl, "time": time_val
                    }
                    if mkt == 'HK' or (sym and sym.isdigit()):
                        hk_orders.append(order_info)
                    else:
                        us_orders.append(order_info)

                print(f"  • HK Stock Orders Count: {len(hk_orders)}")
                if hk_orders:
                    print("  Sample HK Orders:")
                    for hko in hk_orders[:5]:
                        print(f"    {hko}")
                print(f"  • US Stock Orders Count: {len(us_orders)}")
                if us_orders:
                    print("  Sample US Orders:")
                    for uso in us_orders[:3]:
                        print(f"    {uso}")
            else:
                print(f"ℹ️ No filled orders returned for {acc}.")
        except Exception as e:
            print(f"⚠️ get_filled_orders call failed: {e}")

    print("\n" + "=" * 70)
    print("✅ TEST COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    test_tiger_ipo_capabilities()
