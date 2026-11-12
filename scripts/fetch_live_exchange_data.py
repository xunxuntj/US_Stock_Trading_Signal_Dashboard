"""
Direct Real-Time Exchange Data Pull (scripts/fetch_live_exchange_data.py)
Fetches live account balances, all active positions, and recent filled orders
directly from Tiger Brokers OpenAPI and Charles Schwab API.
"""

import os
import sys
import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.broker.tiger_connector import TigerBrokerConnector
from core.broker.schwab_connector import SchwabBrokerConnector


def fetch_all():
    print("=" * 80)
    print("🚀 LIVE BROKERAGE / EXCHANGE POSITIONS & BALANCES REAL-TIME PULL")
    print(f"🕒 Pull Time (UTC): {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # 1. Tiger Brokers
    tiger_id = os.getenv("TIGER_ID")
    raw_tiger_accounts = os.getenv("TIGER_ACCOUNT", "638812,U9959007").strip()
    tiger_accounts = [a.strip() for a in raw_tiger_accounts.split(",") if a.strip()]

    print(f"Tiger ID Configured: {'YES' if tiger_id else 'NO'}")
    print(f"Tiger Accounts to inspect: {tiger_accounts}")

    for acc in tiger_accounts:
        acc_label = "老虎证券 - 综合账户 (638812)" if "638812" in acc else f"老虎证券 - 环球账户 ({acc})"
        print(f"\n{'#'*30} {acc_label} {'#'*30}")
        conn = TigerBrokerConnector(account_id=acc, account_name=acc_label)
        print(f"Live Connected: {conn.is_live_connected()}")

        # Balance
        try:
            bal = conn.get_account_balance()
            print(f"💰 Account Balance:")
            print(f"   • Total Equity:     ${bal.total_equity:,.2f}")
            print(f"   • Cash Balance:     ${bal.cash:,.2f}")
            print(f"   • Market Value:     ${bal.market_value:,.2f}")
            print(f"   • Vault / 钱袋子:    ${getattr(bal, 'vault_balance', 0.0):,.2f}")
            print(f"   • Accrued Dividend: ${getattr(bal, 'accrued_dividend', 0.0):,.2f}")
            print(f"   • Buying Power:     ${getattr(bal, 'buying_power', 0.0):,.2f}")
        except Exception as e:
            print(f"❌ Error getting balance: {e}")

        # Positions via Connector
        try:
            conn_pos = conn.get_positions()
            print(f"\n📦 Positions (Parsed via Connector): {len(conn_pos)} found")
            for p in conn_pos:
                print(f"   • {p.ticker:<10} | Shares: {p.shares:<12} | Cost: ${p.cost_basis:<9.2f} | Price: ${p.market_price:<9.2f} | MktVal: ${p.market_value:<11.2f} | Layer: {p.layer}")
        except Exception as e:
            print(f"❌ Error in conn.get_positions: {e}")

        # Raw Positions via TradeClient
        if conn._client:
            try:
                raw_positions = conn._client.get_positions(account=acc)
                print(f"\n🔍 RAW Client get_positions({acc}): {len(raw_positions) if raw_positions else 0} items")
                if raw_positions:
                    for rp in raw_positions:
                        sym = getattr(rp, 'symbol', None)
                        if not sym and hasattr(rp, 'contract'):
                            sym = getattr(rp.contract, 'symbol', '')
                        sec_type = getattr(rp.contract, 'sec_type', '') if hasattr(rp, 'contract') else ''
                        curr = getattr(rp.contract, 'currency', '') if hasattr(rp, 'contract') else ''
                        qty = getattr(rp, 'quantity', None)
                        pos_qty = getattr(rp, 'position_qty', None)
                        pos_scale = getattr(rp, 'position_scale', None)
                        salable = getattr(rp, 'salable_qty', None)
                        avg_cost = getattr(rp, 'average_cost', None)
                        mkt_price = getattr(rp, 'market_price', None)
                        mkt_val = getattr(rp, 'market_value', None)
                        print(f"   [RAW ITEM] Symbol: {sym} ({sec_type}/{curr}) | quantity={qty} | position_qty={pos_qty} | scale={pos_scale} | salable={salable} | avg_cost={avg_cost} | mkt_price={mkt_price} | mkt_val={mkt_val}")
                else:
                    print("   [RAW Client get_positions]: returned None or empty list")
            except Exception as e:
                print(f"❌ RAW client.get_positions error: {e}")

        # Filled orders (past 14 days)
        if conn._client:
            try:
                start_d = (datetime.datetime.now() - datetime.timedelta(days=14)).strftime('%Y-%m-%d')
                end_d = datetime.datetime.now().strftime('%Y-%m-%d')
                orders = conn._client.get_filled_orders(account=acc, start_date=start_d, end_date=end_d)
                print(f"\n📋 Filled Orders (Past 14 days): {len(orders) if orders else 0} orders")
                if orders:
                    for o in orders:
                        sym = getattr(o.contract, 'symbol', '') if hasattr(o, 'contract') else getattr(o, 'symbol', '')
                        action = getattr(o, 'action', '')
                        filled = getattr(o, 'filled', getattr(o, 'filled_quantity', 0))
                        avg_p = getattr(o, 'avg_fill_price', 0)
                        t_time = getattr(o, 'trade_time', getattr(o, 'order_time', ''))
                        print(f"   • [{action}] {sym:<10} Qty: {filled:<8} Price: ${avg_p:<8.2f} Time: {t_time}")
            except Exception as e:
                print(f"❌ Error getting filled orders: {e}")

    # 2. Charles Schwab
    print(f"\n{'#'*30} CHARLES SCHWAB (56169533) {'#'*30}")
    schwab = SchwabBrokerConnector(account_name="Charles Schwab (嘉信理财)")
    print(f"Live Connected: {schwab.is_live_connected()}")
    try:
        s_bal = schwab.get_account_balance()
        print(f"💰 Schwab Balance: Total=${s_bal.total_equity:,.2f}, Cash=${s_bal.cash:,.2f}, MktVal=${s_bal.market_value:,.2f}")
    except Exception as e:
        print(f"❌ Schwab balance error: {e}")
    try:
        s_pos = schwab.get_positions()
        print(f"📦 Schwab Positions: {len(s_pos)} found")
        for sp in s_pos:
            print(f"   • {sp.ticker:<10} | Shares: {sp.shares:<10} | Cost: ${sp.cost_basis} | Price: ${sp.market_price} | MktVal: ${sp.market_value}")
    except Exception as e:
        print(f"❌ Schwab positions error: {e}")

    print("\n" + "=" * 80)
    print("✅ PULL COMPLETED")
    print("=" * 80)


if __name__ == '__main__':
    fetch_all()
