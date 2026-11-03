"""
Diagnostic script to inspect all asset fields for 638812 & U9959007 (scripts/inspect_tiger_assets.py)
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.broker.tiger_connector import TigerBrokerConnector


def inspect_assets():
    print("=" * 70)
    print("🔍 TIGER ASSET STRUCTURE DEEP INSPECTION")
    print("=" * 70)

    for acc in ["638812", "U9959007"]:
        print(f"\n{'='*25} Inspecting Account: {acc} {'='*25}")
        conn = TigerBrokerConnector(account_id=acc)
        if not conn.is_live_connected():
            print("Client not connected.")
            continue
        client = conn._client

        # 1. get_prime_assets
        print("\n--- [1] get_prime_assets (consolidated=True) ---")
        try:
            prime_obj = client.get_prime_assets(account=acc, consolidated=True)
            if prime_obj:
                print(f"Prime object dict keys: {dir(prime_obj)}")
                segs = getattr(prime_obj, 'segments', {})
                print(f"Available segments: {list(segs.keys())}")
                for s_key, s_val in segs.items():
                    print(f"\n  Segment [{s_key}]:")
                    for attr in [
                        'category', 'currency', 'net_liquidation', 'equity_with_loan',
                        'gross_position_value', 'cash_balance', 'cash_available_for_trade',
                        'locked_funds', 'uncollected', 'unrealized_pl', 'realized_pl',
                        'buying_power', 'excess_liquidation', 'consolidated_seg_types'
                    ]:
                        val = getattr(s_val, attr, None)
                        if val is not None and str(val) != 'inf':
                            print(f"    {attr}: {val}")

                    curr_assets = getattr(s_val, 'currency_assets', {})
                    if curr_assets:
                        print("    Currency Assets:")
                        for c_k, c_v in curr_assets.items():
                            print(f"      {c_k}: cash={getattr(c_v, 'cash_balance', None)}, avail={getattr(c_v, 'cash_available_for_trade', None)}")
            else:
                print("get_prime_assets returned None")
        except Exception as e:
            print(f"get_prime_assets error: {e}")

        # 2. get_assets with segment=True, market_value=True
        print("\n--- [2] get_assets(segment=True, market_value=True) ---")
        try:
            asset_list = client.get_assets(account=acc, segment=True, market_value=True)
            if asset_list:
                for idx, a in enumerate(asset_list):
                    print(f"Asset [{idx}] account: {getattr(a, 'account', None)}")
                    summary = getattr(a, 'summary', None)
                    if summary:
                        print("  Summary:")
                        for attr in [
                            'net_liquidation', 'gross_position_value', 'cash',
                            'accrued_dividend', 'accrued_cash', 'accrued_interest',
                            'available_funds', 'buying_power', 'excess_liquidity',
                            'equity_with_loan', 'currency', 'unrealized_pnl', 'realized_pnl'
                        ]:
                            val = getattr(summary, attr, None)
                            if val is not None and str(val) != 'inf':
                                print(f"    {attr}: {val}")

                    segs = getattr(a, 'segments', {})
                    if segs:
                        print(f"  Segments in get_assets: {list(segs.keys())}")
                        for s_k, s_v in segs.items():
                            print(f"    Segment {s_k}: net_liq={getattr(s_v, 'net_liquidation', None)}, cash={getattr(s_v, 'cash', None)}, mkt={getattr(s_v, 'gross_position_value', None)}, acc_div={getattr(s_v, 'accrued_dividend', None)}, acc_cash={getattr(s_v, 'accrued_cash', None)}")

                    mkt_vals = getattr(a, 'market_values', {})
                    if mkt_vals:
                        print(f"  Market Values in get_assets: {list(mkt_vals.keys())}")
                        for m_k, m_v in mkt_vals.items():
                            print(f"    {m_k}: net_liq={getattr(m_v, 'net_liquidation', None)}, cash={getattr(m_v, 'cash_balance', None)}, stock_mkt={getattr(m_v, 'stock_market_value', None)}, div={getattr(m_v, 'net_dividend', None)}")
            else:
                print("get_assets returned None or empty")
        except Exception as e:
            print(f"get_assets error: {e}")

    print("\n" + "=" * 70)
    print("✅ INSPECTION COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    inspect_assets()
