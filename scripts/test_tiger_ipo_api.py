"""
Diagnostic Test Script for Tiger OpenAPI IPO, Interest, and Fee Data (scripts/test_tiger_ipo_api.py)
"""

import os
import sys
import datetime
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.broker.tiger_connector import TigerBrokerConnector


def test_tiger_ipo_capabilities():
    print("=" * 70)
    print("🔍 TIGER OPENAPI IPO, INTEREST & FEE DEEP INSPECTION")
    print("=" * 70)

    tiger_id = os.getenv("TIGER_ID")
    raw_acc = os.getenv("TIGER_ACCOUNT", "")
    pk = os.getenv("TIGER_PRIVATE_KEY_PATH")

    if not tiger_id or not pk:
        print("❌ Tiger credentials not available in environment.")
        return

    accounts = ["638812", "U9959007"]

    for acc in accounts:
        print(f"\n{'='*30} Testing Account: {acc} {'='*30}")
        connector = TigerBrokerConnector(account_id=acc, account_name=f"Tiger ({acc})")
        if not connector.is_live_connected():
            continue

        client = connector._client

        # 1. Inspect Fund Details (FEE) - HKD & USD
        print("\n--- [1] Inspecting FEE Records (HKD & USD) ---")
        for curr in ['HKD', 'USD', None]:
            try:
                res_fee = client.get_fund_details(seg_types=['SEC'], account=acc, fund_type='FEE', currency=curr, limit=15)
                if res_fee is not None and not res_fee.empty:
                    print(f"✅ Found {len(res_fee)} FEE records for currency={curr}:")
                    cols = [c for c in ['business_date', 'currency', 'type', 'desc', 'contract_name', 'amount'] if c in res_fee.columns]
                    print(res_fee[cols].to_string())
                else:
                    print(f"ℹ️ No FEE records for currency={curr}")
            except Exception as e:
                print(f"⚠️ get_fund_details (currency={curr}) error: {e}")

        # 2. Inspect Filled Orders for past 85 days
        print("\n--- [2] Inspecting Filled Orders (Last 85 days) ---")
        end_d = datetime.date.today()
        start_d = end_d - datetime.timedelta(days=85)
        try:
            orders = client.get_filled_orders(
                account=acc,
                start_date=start_d.strftime("%Y-%m-%d"),
                end_date=end_d.strftime("%Y-%m-%d"),
                limit=100
            )
            if orders:
                print(f"✅ Total {len(orders)} filled orders in last 85 days:")
                for o in orders:
                    sym = getattr(o.contract, 'symbol', '') if hasattr(o, 'contract') else ''
                    mkt = getattr(o.contract, 'market', '') if hasattr(o, 'contract') else ''
                    comm = getattr(o, 'commission', None)
                    pnl = getattr(o, 'realized_pnl', None)
                    action = getattr(o, 'action', '')
                    filled_qty = getattr(o, 'filled', 0)
                    fill_p = getattr(o, 'avg_fill_price', 0)
                    time_val = getattr(o, 'trade_time', getattr(o, 'order_time', ''))
                    print(f"  [{mkt}] {sym:<10} {action:<4} qty={filled_qty:<8} price={fill_p:<8} comm={comm} pnl={pnl} time={time_val}")
            else:
                print("ℹ️ No filled orders in last 85 days.")
        except Exception as e:
            print(f"⚠️ get_filled_orders error: {e}")

    print("\n" + "=" * 70)
    print("✅ DEEP INSPECTION COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    test_tiger_ipo_capabilities()
