"""
Comprehensive Broker Historical Data Pull & Audit Correlation Engine
(scripts/pull_all_historical_broker_data.py)

Fetches complete historical records from Tiger Brokers OpenAPI and Charles Schwab:
1. All filled orders (2026-01-01 to present) across quarterly slices
2. All funding / cash transactions / deposits / withdrawals / dividends / fees
3. Historical asset analytics & daily equity
4. Detailed cross-correlation with current database (trades, cash_transactions, nav_history)
5. Generates structured comparison report for user audit BEFORE mutating production DB.
"""

import os
import sys
import json
import sqlite3
import datetime
from typing import Dict, List, Any, Optional
import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.broker.tiger_connector import TigerBrokerConnector
from core.broker.schwab_connector import SchwabBrokerConnector


def format_ts(val: Any) -> str:
    """Format millisecond timestamp or string date to YYYY-MM-DD HH:MM:SS."""
    if not val:
        return ""
    try:
        f_val = float(val)
        if f_val > 1e11:  # milliseconds
            f_val = f_val / 1000.0
        return datetime.datetime.fromtimestamp(f_val).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return str(val)[:19]


def _parse_and_append_order(o: Any, account_id: str, all_orders: List[Dict[str, Any]], seen_order_ids: set):
    """Normalize and append an order or transaction record from Tiger API."""
    o_id = str(getattr(o, 'order_id', getattr(o, 'id', '')))
    if not o_id or o_id in seen_order_ids:
        return
    seen_order_ids.add(o_id)

    raw_sym = getattr(o, 'symbol', None)
    if not raw_sym and hasattr(o, 'contract'):
        raw_sym = getattr(o.contract, 'symbol', '')
    sym = str(raw_sym or '').upper().strip()
    if not sym:
        return

    action = str(getattr(o, 'action', 'BUY')).upper()
    raw_filled = float(getattr(o, 'filled', getattr(o, 'filled_quantity', getattr(o, 'quantity', 0.0))) or 0.0)
    pos_scale = float(getattr(o, 'quantity_scale', getattr(o, 'filled_scale', 1.0)) or 1.0)
    filled_qty = raw_filled / pos_scale if pos_scale > 1.0 else raw_filled

    avg_p = float(getattr(o, 'avg_fill_price', getattr(o, 'filled_price', getattr(o, 'price', 0.0))) or 0.0)
    comm = float(getattr(o, 'commission', 0.0) or 0.0)
    pnl = float(getattr(o, 'realized_pnl', 0.0) or 0.0)
    t_time = format_ts(getattr(o, 'trade_time', getattr(o, 'transacted_at', getattr(o, 'order_time', ''))))

    all_orders.append({
        "order_id": o_id,
        "account": account_id,
        "date": t_time[:10] if t_time else "",
        "time": t_time,
        "ticker": sym,
        "action": action,
        "shares": filled_qty,
        "price": avg_p,
        "total_value": round(filled_qty * avg_p, 2),
        "commission": comm,
        "realized_pnl": pnl,
        "status": str(getattr(o, 'status', 'FILLED'))
    })


def fetch_tiger_historical_orders(conn: TigerBrokerConnector, account_id: str) -> List[Dict[str, Any]]:
    """Fetch all filled orders across 45-day time windows from 2026-01-01 to present using multiple Tiger endpoints."""
    if not conn._client:
        return []

    client = conn._client
    all_orders = []
    seen_order_ids = set()

    # Generate 45-day sliding windows from 2026-01-01 to today
    intervals = []
    cur_d = datetime.date(2026, 1, 1)
    today = datetime.date.today()
    while cur_d <= today:
        next_d = min(cur_d + datetime.timedelta(days=45), today)
        intervals.append((cur_d.strftime("%Y-%m-%d"), next_d.strftime("%Y-%m-%d")))
        cur_d = next_d + datetime.timedelta(days=1)

    for s_date, e_date in intervals:
        s_dt = datetime.datetime.strptime(s_date, "%Y-%m-%d")
        e_dt = datetime.datetime.strptime(e_date, "%Y-%m-%d") + datetime.timedelta(days=1, microseconds=-1)
        s_ts = int(s_dt.timestamp() * 1000)
        e_ts = int(e_dt.timestamp() * 1000)

        # 1. client.get_filled_orders with pure millisecond timestamps
        try:
            orders = client.get_filled_orders(account=account_id, start_time=s_ts, end_time=e_ts)
            if orders:
                for o in orders:
                    _parse_and_append_order(o, account_id, all_orders, seen_order_ids)
        except Exception as e:
            print(f"ℹ️ Note: get_filled_orders for {account_id} ({s_date} to {e_date}): {e}")

        # 2. client.get_orders with OrderStatus.FILLED
        try:
            from tigeropen.common.consts import OrderStatus
            gen_orders = client.get_orders(account=account_id, states=[OrderStatus.FILLED], start_time=s_ts, end_time=e_ts)
            if gen_orders:
                orders_list = gen_orders.result if hasattr(gen_orders, 'result') else (gen_orders if isinstance(gen_orders, list) else [])
                for o in orders_list:
                    _parse_and_append_order(o, account_id, all_orders, seen_order_ids)
        except Exception as e:
            pass

        # 3. For Prime Account (e.g. 638812), query get_transactions
        try:
            s_yyyymmdd = s_date.replace("-", "")
            e_yyyymmdd = e_date.replace("-", "")
            txs = client.get_transactions(account=account_id, since_date=s_yyyymmdd, to_date=e_yyyymmdd)
            if txs:
                tx_list = txs.result if hasattr(txs, 'result') else (txs if isinstance(txs, list) else [])
                for tx in tx_list:
                    _parse_and_append_order(tx, account_id, all_orders, seen_order_ids)
        except Exception:
            pass

    # Sort chronologically
    all_orders.sort(key=lambda x: (x["time"], x["order_id"]))
    return all_orders


def fetch_tiger_historical_funding(conn: TigerBrokerConnector, account_id: str) -> List[Dict[str, Any]]:
    """Fetch funding history, cash deposits/withdrawals, dividends, and interest."""
    if not conn._client:
        return []

    client = conn._client
    funding_records = []
    seen_keys = set()

    # 1. get_funding_history
    try:
        f_list = client.get_funding_history()
        if f_list is not None:
            if isinstance(f_list, list) and len(f_list) > 0:
                for item in f_list:
                    raw_d = getattr(item, 'date', getattr(item, 'updated_at', ''))
                    d_str = format_ts(raw_d)[:10] if raw_d else ""
                    t_type = str(getattr(item, 'type', getattr(item, 'funding_type', ''))).upper()
                    amt = float(getattr(item, 'amount', 0.0) or 0.0)
                    desc = str(getattr(item, 'remark', getattr(item, 'comment', '')))
                    curr = str(getattr(item, 'currency', 'USD'))
                    key = (account_id, d_str, t_type, round(amt, 2), curr)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        funding_records.append({
                            "source": "get_funding_history",
                            "account": account_id,
                            "date": d_str,
                            "type": t_type,
                            "amount": amt,
                            "currency": curr,
                            "description": desc
                        })
            elif hasattr(f_list, 'empty') and not f_list.empty:
                for _, r in f_list.iterrows():
                    raw_d = r.get('date', r.get('updated_at', ''))
                    d_str = format_ts(raw_d)[:10] if raw_d else ""
                    t_type = str(r.get('type', r.get('funding_type', ''))).upper()
                    amt = float(r.get('amount', 0.0) or 0.0)
                    desc = str(r.get('remark', r.get('comment', '')))
                    curr = str(r.get('currency', 'USD'))
                    key = (account_id, d_str, t_type, round(amt, 2), curr)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        funding_records.append({
                            "source": "get_funding_history",
                            "account": account_id,
                            "date": d_str,
                            "type": t_type,
                            "amount": amt,
                            "currency": curr,
                            "description": desc
                        })
    except Exception as e:
        print(f"⚠️ get_funding_history ({account_id}) exception: {e}")

    # 2. get_fund_details (DEPOSIT, WITHDRAW, DIVIDEND, FEE)
    for f_type in [None, 'DEPOSIT', 'WITHDRAW', 'DIVIDEND', 'FEE']:
        try:
            res_df = client.get_fund_details(
                seg_types=['SEC'],
                account=account_id,
                fund_type=f_type,
                start_date='2026-01-01',
                end_date=datetime.date.today().strftime('%Y-%m-%d'),
                limit=100
            )
            if res_df is not None and hasattr(res_df, 'empty') and not res_df.empty:
                for _, r in res_df.iterrows():
                    raw_d = r.get('business_date', r.get('date', ''))
                    d_str = format_ts(raw_d)[:10] if raw_d else ""
                    rec_type = str(r.get('type', r.get('fund_type', f_type or 'FUNDING'))).upper()
                    amt = float(r.get('amount', 0.0) or 0.0)
                    curr = str(r.get('currency', 'USD'))
                    desc = str(r.get('desc', r.get('remark', '')))
                    key = (account_id, d_str, rec_type, round(amt, 2), curr)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        funding_records.append({
                            "source": "get_fund_details",
                            "account": account_id,
                            "date": d_str,
                            "type": rec_type,
                            "amount": amt,
                            "currency": curr,
                            "description": desc
                        })
        except Exception:
            pass

    funding_records.sort(key=lambda x: (x["date"], x["amount"]))
    return funding_records


def fetch_tiger_asset_analytics(conn: TigerBrokerConnector, account_id: str) -> List[Dict[str, Any]]:
    """Fetch daily historical asset / equity analytics from Tiger."""
    if not conn._client:
        return []

    client = conn._client
    records = []
    try:
        analytics = client.get_analytics_asset(
            account=account_id,
            start_date="2026-01-01",
            end_date=datetime.date.today().strftime("%Y-%m-%d")
        )
        if analytics:
            history_list = []
            if isinstance(analytics, dict) and 'history' in analytics:
                history_list = analytics['history'] or []
            elif hasattr(analytics, 'history'):
                history_list = getattr(analytics, 'history', [])
            elif isinstance(analytics, list):
                history_list = analytics

            for item in history_list:
                raw_d = item.get('dt') if isinstance(item, dict) else getattr(item, 'dt', None)
                if not raw_d:
                    raw_ts = item.get('date') if isinstance(item, dict) else getattr(item, 'date', None)
                    raw_d = format_ts(raw_ts)[:10] if raw_ts else ""
                
                tot_eq = float(item.get('net_liquidation', item.get('total_equity', 0.0)) if isinstance(item, dict) else getattr(item, 'net_liquidation', getattr(item, 'total_equity', 0.0)) or 0.0)
                cash_val = float(item.get('cash', 0.0) if isinstance(item, dict) else getattr(item, 'cash', 0.0) or 0.0)
                gp_val = float(item.get('gross_position_value', 0.0) if isinstance(item, dict) else getattr(item, 'gross_position_value', 0.0) or 0.0)

                records.append({
                    "account": account_id,
                    "date": str(raw_d),
                    "total_equity": tot_eq,
                    "cash": cash_val,
                    "gross_position_value": gp_val
                })
    except Exception as e:
        print(f"⚠️ get_analytics_asset ({account_id}) exception: {e}")

    records.sort(key=lambda x: x["date"])
    return records


def run_full_audit():
    print("=" * 80)
    print("🔍 COMPREHENSIVE BROKER EXCHANGE HISTORICAL AUDIT & CROSS-CORRELATION")
    print(f"🕒 Timestamp (UTC): {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # 1. Load Local Database
    db_path = "portfolio.db"
    conn_db = sqlite3.connect(db_path)
    df_db_trades = pd.read_sql_query("SELECT * FROM trades ORDER BY date ASC, id ASC", conn_db)
    df_db_cash = pd.read_sql_query("SELECT * FROM cash_transactions ORDER BY date ASC, id ASC", conn_db)
    df_db_nav = pd.read_sql_query("SELECT * FROM nav_history ORDER BY date ASC", conn_db)
    conn_db.close()

    print(f"\n📂 Current Local Database Records:")
    print(f"   • trades:             {len(df_db_trades)} rows (ID {df_db_trades['id'].min()} to {df_db_trades['id'].max()})")
    print(f"   • cash_transactions:  {len(df_db_cash)} rows")
    print(f"   • nav_history:        {len(df_db_nav)} rows ({df_db_nav['date'].min()} to {df_db_nav['date'].max()})")

    # 2. Initialize Broker Connectors
    raw_tiger_accounts = os.getenv("TIGER_ACCOUNT", "638812,U9959007").strip()
    tiger_accounts = [a.strip() for a in raw_tiger_accounts.split(",") if a.strip()]

    all_broker_orders: List[Dict[str, Any]] = []
    all_broker_funding: List[Dict[str, Any]] = []
    all_broker_analytics: List[Dict[str, Any]] = []

    for acc in tiger_accounts:
        acc_label = "老虎证券 - 综合账户 (638812)" if "638812" in acc else f"老虎证券 - 环球账户 ({acc})"
        print(f"\n{'='*30} Querying Tiger Account: {acc} ({acc_label}) {'='*30}")
        conn = TigerBrokerConnector(account_id=acc, account_name=acc_label)
        print(f"Live Connected: {conn.is_live_connected()}")

        if conn.is_live_connected():
            orders = fetch_tiger_historical_orders(conn, acc)
            print(f"✅ Found {len(orders)} filled orders in Tiger API for {acc}")
            all_broker_orders.extend(orders)

            funding = fetch_tiger_historical_funding(conn, acc)
            print(f"✅ Found {len(funding)} funding/cash records for {acc}")
            all_broker_funding.extend(funding)

            analytics = fetch_tiger_asset_analytics(conn, acc)
            print(f"✅ Found {len(analytics)} asset analytics records for {acc}")
            all_broker_analytics.extend(analytics)

    # 3. Charles Schwab API status
    print(f"\n{'='*30} Querying Charles Schwab (56169533) {'='*30}")
    schwab = SchwabBrokerConnector(account_name="Charles Schwab (嘉信理财)")
    print(f"Schwab Live Connected: {schwab.is_live_connected()}")
    try:
        schwab_bal = schwab.get_account_balance()
        print(f"💰 Schwab Balance: Total=${schwab_bal.total_equity:,.2f}, Cash=${schwab_bal.cash:,.2f}")
    except Exception as e:
        print(f"Schwab balance check: {e}")

    # 4. Compare Broker Orders vs DB Trades
    print("\n" + "=" * 80)
    print("📊 1. TRADES & ORDERS CROSS-CORRELATION AUDIT")
    print("=" * 80)

    df_broker_orders = pd.DataFrame(all_broker_orders) if all_broker_orders else pd.DataFrame()

    matched_pairs = []
    unmatched_db = []
    unmatched_broker = []

    # Map DB trades
    used_broker_indices = set()

    if not df_db_trades.empty:
        for idx, db_row in df_db_trades.iterrows():
            d_date = str(db_row['date'])[:10]
            d_tkr = str(db_row['ticker']).upper().strip()
            d_act = str(db_row['action']).upper().strip()
            d_shares = float(db_row['shares'])
            d_price = float(db_row['price'])
            d_fee = float(db_row.get('fee', 0.0) or 0.0)
            d_notes = str(db_row.get('reason', db_row.get('notes', '')) or '')

            # Search match in broker orders
            match_found = False
            if not df_broker_orders.empty:
                for b_idx, b_row in df_broker_orders.iterrows():
                    if b_idx in used_broker_indices:
                        continue
                    b_date = str(b_row['date'])[:10]
                    b_tkr = str(b_row['ticker']).upper().strip()
                    b_act = str(b_row['action']).upper().strip()
                    b_shares = float(b_row['shares'])
                    b_price = float(b_row['price'])

                    # Ticker & Action match
                    if b_tkr == d_tkr and b_act == d_act:
                        # Date match (or within 1 day due to UTC vs EST timezone difference)
                        date_close = False
                        try:
                            d1 = datetime.datetime.strptime(d_date, "%Y-%m-%d")
                            d2 = datetime.datetime.strptime(b_date, "%Y-%m-%d")
                            date_close = abs((d1 - d2).days) <= 1
                        except Exception:
                            date_close = (d_date == b_date)

                        # Shares match (within 0.1 share)
                        shares_close = abs(b_shares - d_shares) < 0.1

                        if date_close and shares_close:
                            used_broker_indices.add(b_idx)
                            matched_pairs.append({
                                "db_id": db_row['id'],
                                "date": d_date,
                                "ticker": d_tkr,
                                "action": d_act,
                                "db_shares": d_shares,
                                "broker_shares": b_shares,
                                "db_price": d_price,
                                "broker_price": b_price,
                                "price_diff": round(b_price - d_price, 4),
                                "db_fee": d_fee,
                                "broker_fee": b_row['commission'],
                                "fee_diff": round(b_row['commission'] - d_fee, 2),
                                "broker_order_id": b_row['order_id'],
                                "account": b_row['account'],
                                "db_notes": d_notes
                            })
                            match_found = True
                            break

            if not match_found:
                unmatched_db.append({
                    "db_id": db_row['id'],
                    "date": d_date,
                    "ticker": d_tkr,
                    "action": d_act,
                    "shares": d_shares,
                    "price": d_price,
                    "fee": d_fee,
                    "reason": d_notes,
                    "category": db_row.get('category', '')
                })

    if not df_broker_orders.empty:
        for b_idx, b_row in df_broker_orders.iterrows():
            if b_idx not in used_broker_indices:
                unmatched_broker.append(b_row.to_dict())

    print(f"\n✅ Matched Trades (found in both DB and Broker API): {len(matched_pairs)}")
    print(f"ℹ️ Unmatched in DB (in DB but not returned by recent Broker API window): {len(unmatched_db)}")
    print(f"🆕 Unmatched in Broker (in Broker API but missing from DB!): {len(unmatched_broker)}")

    if unmatched_broker:
        print("\n🚨 NEW / MISSING ORDERS FOUND IN BROKER API (NEED TO INGEST TO DB):")
        for u in unmatched_broker:
            print(f"   • OrderID: {u['order_id']} | Date: {u['date']} {u['time'][11:19]} | [{u['action']}] {u['ticker']:<8} | Shares: {u['shares']:<10} | Price: ${u['price']:<8.2f} | Comm: ${u['commission']} | Acc: {u['account']}")

    if matched_pairs:
        print(f"\n🔍 Sample Matched Trades (Showing first 5 of {len(matched_pairs)}):")
        for m in matched_pairs[:5]:
            print(f"   • ID {m['db_id']:<3} | {m['date']} [{m['action']}] {m['ticker']:<6} | DB P: ${m['db_price']:<7.2f} Broker P: ${m['broker_price']:<7.2f} (Diff: ${m['price_diff']:+0.2f}) | DB Fee: ${m['db_fee']} Broker Fee: ${m['broker_fee']} | Notes: '{m['db_notes']}'")

    if unmatched_db:
        print(f"\n⚠️ Database Trades not returned by Broker API (Showing first 5 of {len(unmatched_db)}):")
        for u in unmatched_db[:5]:
            print(f"   • ID {u['db_id']:<3} | {u['date']} [{u['action']}] {u['ticker']:<6} | {u['shares']} sh @ ${u['price']} | Reason: '{u['reason']}'")

    # 5. Compare Cash Transactions
    print("\n" + "=" * 80)
    print("💰 2. CASH TRANSACTIONS / FUNDING AUDIT")
    print("=" * 80)
    print(f"Current DB cash_transactions: {len(df_db_cash)} rows")
    for _, cr in df_db_cash.iterrows():
        print(f"   • ID {cr['id']} | Date: {cr['date']} | Type: {cr['type']:<10} | Amount: ${cr['amount']:>10.2f} | Notes: {cr.get('notes', '')}")

    print(f"\nBroker Funding records fetched: {len(all_broker_funding)} rows")
    funding_2026 = [bf for bf in all_broker_funding if str(bf.get('date', '')) >= '2026-01-01']
    print(f"Broker Funding in 2026: {len(funding_2026)} records")
    for bf in funding_2026[:15]:
        print(f"   • [{bf['source']}] Date: {bf['date']} | Type: {bf['type']:<12} | Amount: ${bf['amount']} {bf['currency']} | Acc: {bf['account']} | Desc: {bf['description']}")

    # 5b. Compare NAV History
    print("\n" + "=" * 80)
    print("📈 3. DAILY NAV HISTORY AUDIT")
    print("=" * 80)
    print(f"Current DB nav_history: {len(df_db_nav)} rows ({df_db_nav['date'].min()} to {df_db_nav['date'].max()})")
    if all_broker_analytics:
        print(f"Broker Daily Analytics fetched: {len(all_broker_analytics)} rows")
        for sb in all_broker_analytics[-10:]:
            print(f"   • Date: {sb['date']} | Total Equity: ${sb['total_equity']:,.2f} | Cash: ${sb['cash']:,.2f} | Acc: {sb['account']}")

    # 6. Save Complete Audit Artifacts
    os.makedirs("data", exist_ok=True)
    audit_summary = {
        "audit_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "summary": {
            "total_broker_orders": len(all_broker_orders),
            "total_db_trades": len(df_db_trades),
            "matched_trades": len(matched_pairs),
            "broker_orders_missing_in_db": len(unmatched_broker),
            "db_trades_unmatched_in_api": len(unmatched_db),
            "total_db_cash_txs": len(df_db_cash),
            "total_broker_funding_records": len(all_broker_funding),
            "total_broker_analytics_records": len(all_broker_analytics)
        },
        "matched_trades": matched_pairs,
        "unmatched_broker_orders": unmatched_broker,
        "unmatched_db_trades": unmatched_db,
        "broker_funding": all_broker_funding,
        "broker_analytics": all_broker_analytics
    }

    with open("data/broker_audit_comparison.json", "w", encoding="utf-8") as f:
        json.dump(audit_summary, f, ensure_ascii=False, indent=2)

    if unmatched_broker:
        df_unmatched_b = pd.DataFrame(unmatched_broker)
        df_unmatched_b.to_csv("data/missing_broker_orders.csv", index=False, encoding="utf-8")

    print("\n" + "=" * 80)
    print("✅ AUDIT COMPARISON SAVED TO data/broker_audit_comparison.json")
    print("=" * 80)


if __name__ == '__main__':
    run_full_audit()
