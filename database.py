import sqlite3
import pandas as pd
import datetime
import os
from typing import Optional, List, Dict, Any
from config import DB_PATH, INITIAL_CAPITAL, JEPQ_TARGET_PCT, SGOV_TARGET_PCT

__all__ = [
    "init_db", "get_connection", "get_positions", "update_position",
    "get_nav_history", "record_nav", "record_brokerage_nav",
    "get_trades_history", "record_trade", "update_trade_classification",
    "execute_live_us_trade", "get_cash_transactions", "record_cash_transaction",
    "get_hk_ipo_history", "record_hk_ipo", "set_initial_hk_ipo_cum",
    "get_hk_ipo_trades_history", "record_hk_ipo_trade", "sync_hk_ipo_pnl_to_nav",
    "get_latest_kids_returns", "init_kids_ledger_table",
    "record_kids_cash_transaction", "get_kids_cash_ledger", "get_kids_account_summary",
    "get_cloud_market_prices_latest_dates", "fetch_cloud_market_prices", "upsert_cloud_market_price_rows",
    "get_supabase_credentials", "fetch_supabase_df"
]

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Current Positions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS positions (
        ticker TEXT PRIMARY KEY,
        shares REAL NOT NULL,
        cost_basis REAL NOT NULL,
        layer TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)
    try:
        cursor.execute("ALTER TABLE positions ADD COLUMN account TEXT DEFAULT ''")
    except Exception:
        pass
    
    # 2. Trades History Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        ticker TEXT NOT NULL,
        action TEXT NOT NULL,
        shares REAL NOT NULL,
        price REAL NOT NULL,
        total_val REAL NOT NULL,
        fee REAL DEFAULT 0.0,
        pnl REAL DEFAULT 0.0,
        layer TEXT NOT NULL,
        reason TEXT
    )
    """)
    try:
        cursor.execute("ALTER TABLE trades ADD COLUMN fee REAL DEFAULT 0.0")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE trades ADD COLUMN category TEXT DEFAULT 'STRATEGY'")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE trades ADD COLUMN is_strategy INTEGER DEFAULT 1")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE trades ADD COLUMN account TEXT DEFAULT '老虎证券 - 综合账户 (638812)'")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE cash_transactions ADD COLUMN account TEXT DEFAULT '老虎证券 - 综合账户 (638812)'")
    except Exception:
        pass
    
    # 3. NAV History Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS nav_history (
        date TEXT PRIMARY KEY,
        nav REAL NOT NULL,
        cash REAL NOT NULL,
        jepq_val REAL NOT NULL,
        sgov_val REAL NOT NULL,
        trend_val REAL NOT NULL
    )
    """)
    
    # 4. Pending Actions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pending_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        ticker TEXT NOT NULL,
        action TEXT NOT NULL,
        target_val REAL NOT NULL,
        reason TEXT NOT NULL,
        status TEXT DEFAULT 'PENDING'
    )
    """)
    
    # 5. HK Stock IPO Profits Table (港股打新收益)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hk_ipo_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        monthly_profit REAL NOT NULL,
        cum_profit REAL NOT NULL,
        notes TEXT
    )
    """)
    
    # 6. Account Cash Deposit/Withdrawal Table (出入金明细)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cash_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        type TEXT NOT NULL,
        amount REAL NOT NULL,
        notes TEXT
    )
    """)

    # 7. HK/US Single IPO Trades Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hk_ipo_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker_name TEXT,
        market TEXT,
        margin_principal REAL,
        allocated_shares REAL,
        ipo_fee REAL,
        won_shares REAL,
        won_price REAL,
        sell_price REAL,
        trade_fee REAL,
        total_fee REAL,
        profit_amt REAL,
        roi REAL,
        multiplier REAL,
        hiro_capital REAL,
        hiro_profit REAL,
        hiro_return REAL,
        caspar_capital REAL,
        caspar_profit REAL,
        caspar_return REAL,
        exchange_rate REAL,
        hkd_principal REAL,
        hkd_total_fee REAL,
        hkd_profit REAL,
        start_date TEXT,
        settle_date TEXT
    )
    """)

    # 8. Kids Cash Flow Ledger Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS kids_cash_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        kid_name TEXT,
        action_type TEXT,
        amount REAL,
        balance_after REAL,
        notes TEXT
    )
    """)

    conn.commit()
    conn.close()

def record_cash_transaction(date_str, trans_type, amount, notes="", account=None):
    if not account:
        account = "Charles Schwab (嘉信理财)" if ("Schwab" in str(notes) or "嘉信" in str(notes)) else "老虎证券 - 综合账户 (638812)"
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(cash_transactions)")
    cols = [r[1] for r in cursor.fetchall()]
    if 'account' in cols:
        cursor.execute("""
        INSERT INTO cash_transactions (date, type, amount, notes, account)
        VALUES (?, ?, ?, ?, ?)
        """, (date_str, trans_type.upper(), amount, notes, account))
    else:
        cursor.execute("""
        INSERT INTO cash_transactions (date, type, amount, notes)
        VALUES (?, ?, ?, ?)
        """, (date_str, trans_type.upper(), amount, notes))
    conn.commit()
    conn.close()

def get_cash_transactions():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM cash_transactions ORDER BY date ASC", conn)
    conn.close()
    return df

def record_hk_ipo(date_str, monthly_profit, notes=""):
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get last cumulative profit
    cursor.execute("SELECT cum_profit FROM hk_ipo_records ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    prev_cum = row[0] if row else 0.0
    new_cum = prev_cum + monthly_profit
    
    cursor.execute("""
    INSERT INTO hk_ipo_records (date, monthly_profit, cum_profit, notes)
    VALUES (?, ?, ?, ?)
    """, (date_str, monthly_profit, new_cum, notes))
    conn.commit()
    conn.close()
    return new_cum

def set_initial_hk_ipo_cum(date_str, initial_cum_profit, notes="初始累计收益"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO hk_ipo_records (date, monthly_profit, cum_profit, notes)
    VALUES (?, ?, ?, ?)
    """, (date_str, initial_cum_profit, initial_cum_profit, notes))
    conn.commit()
    conn.close()

def get_hk_ipo_history():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM hk_ipo_records ORDER BY date ASC", conn)
    conn.close()
    return df

def get_supabase_credentials():
    url = None
    key = None
    try:
        import streamlit as st
        if hasattr(st, "secrets") and st.secrets:
            url = st.secrets.get("SUPABASE_URL")
            key = st.secrets.get("SUPABASE_KEY") or st.secrets.get("SUPABASE_SECRET_KEY")
    except Exception:
        pass
    if not url:
        url = os.environ.get("SUPABASE_URL") or "https://eoqpkgnkbbadvppucxej.supabase.co"
        key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SECRET_KEY") or "sb_publishable_YH5zDJNieHeqO61hkzovcA_YIBbWzia"
    return str(url), str(key)

def fetch_supabase_df(table_name, select="*", order=None):
    url, key = get_supabase_credentials()
    if not url or not key:
        return None
    try:
        import httpx
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache"
        }
        sep = "&" if "?" in table_name else "?"
        req_url = f"{url}/rest/v1/{table_name}{sep}select={select}"
        if order:
            req_url += f"&order={order}"
        r = httpx.get(req_url, headers=headers, timeout=5.0)
        if r.status_code == 200 and r.json():
            df = pd.DataFrame(r.json())
            # Convert all numeric columns to float/int to prevent Streamlit UI TypeError/KeyError
            for col in df.columns:
                if col not in ['date', 'ticker', 'action', 'layer', 'reason', 'notes', 'kid_name', 'action_type', 'ticker_name', 'market', 'start_date', 'settle_date', 'source', 'type', 'updated_at']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            return df
    except Exception as e:
        print(f"Supabase REST fetch error for {table_name}: {e}")
    return None

def get_positions():
    def _ensure_account(df):
        if df is None or df.empty:
            return df
        if 'account' not in df.columns:
            df['account'] = ''
        def _assign_acc(row):
            acc = str(row.get('account') or '').strip()
            t = str(row.get('ticker') or '').upper().strip()
            if t in ['MSFT', 'GOOG', 'GOOGL', 'NVDY', 'WBA.CVR']:
                return '老虎证券 - 环球账户 (U9959007)'
            if t in ['SGOV', '931CVR013']:
                return '老虎证券 - 综合账户 (638812)'
            if acc and ('U9959007' in acc or '环球' in acc):
                return '老虎证券 - 环球账户 (U9959007)'
            if acc and ('638812' in acc or '综合' in acc):
                return '老虎证券 - 综合账户 (638812)'
            if acc:
                return acc
            return '老虎证券 - 综合账户 (638812)'
        df['account'] = df.apply(_assign_acc, axis=1)
        return df

    df_cloud = fetch_supabase_df("positions", order="ticker.asc")
    if df_cloud is not None and not df_cloud.empty:
        if 'shares' in df_cloud.columns:
            df_cloud['shares'] = pd.to_numeric(df_cloud['shares'], errors='coerce')
            df_cloud = df_cloud[df_cloud['shares'] > 0.00001].copy()
        return _ensure_account(df_cloud)
    conn = get_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM positions WHERE shares > 0.00001", conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return _ensure_account(df)

def update_position(ticker, shares, cost_basis, layer, account=""):
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if shares <= 0:
        cursor.execute("DELETE FROM positions WHERE ticker = ?", (ticker,))
    else:
        cursor.execute("""
        INSERT INTO positions (ticker, shares, cost_basis, layer, updated_at, account)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
            shares = excluded.shares,
            cost_basis = excluded.cost_basis,
            layer = excluded.layer,
            updated_at = excluded.updated_at,
            account = excluded.account
        """, (ticker, shares, cost_basis, layer, now_str, account))
    conn.commit()
    conn.close()

    # Cloud Sync to Supabase
    url, key = get_supabase_credentials()
    if url and key:
        try:
            import httpx
            headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            if shares <= 0:
                # Fully delete the closed position from Supabase Cloud
                httpx.delete(f"{url}/rest/v1/positions?ticker=eq.{ticker}", headers=headers, timeout=5.0)
            else:
                headers["Prefer"] = "resolution=merge-duplicates"
                base_p = {
                    "ticker": ticker, "shares": float(shares), "cost_basis": float(cost_basis), "layer": layer, "updated_at": now_str
                }
                full_p = dict(base_p)
                full_p["account"] = str(account)
                r = httpx.post(f"{url}/rest/v1/positions", json=[full_p], headers=headers, timeout=5.0)
                if r.status_code >= 400:
                    httpx.post(f"{url}/rest/v1/positions", json=[base_p], headers=headers, timeout=5.0)
        except Exception as e:
            print(f"Supabase update_position sync error: {e}")

def record_trade(date_str, ticker, action, shares, price, total_val, fee=0.0, pnl=0.0, layer="TREND", reason="", category="STRATEGY", is_strategy=1, account=None):
    if not account:
        account = _assign_acc(ticker)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(trades)")
    cols = [r[1] for r in cursor.fetchall()]
    if 'account' in cols:
        cursor.execute("""
        INSERT INTO trades (date, ticker, action, shares, price, total_val, fee, pnl, layer, reason, category, is_strategy, account)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (date_str, ticker, action, shares, price, total_val, fee, pnl, layer, reason, category, int(is_strategy), account))
    else:
        cursor.execute("""
        INSERT INTO trades (date, ticker, action, shares, price, total_val, fee, pnl, layer, reason, category, is_strategy)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (date_str, ticker, action, shares, price, total_val, fee, pnl, layer, reason, category, int(is_strategy)))
    conn.commit()
    conn.close()

    # Cloud Sync to Supabase
    url, key = get_supabase_credentials()
    if url and key:
        try:
            import httpx
            headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            base_payload = {
                "date": str(date_str), "ticker": ticker, "action": action, "shares": float(shares),
                "price": float(price), "total_val": float(total_val), "fee": float(fee), "pnl": float(pnl),
                "layer": layer, "reason": str(reason)
            }
            full_payload = dict(base_payload)
            full_payload["category"] = category
            full_payload["is_strategy"] = int(is_strategy)
            r = httpx.post(f"{url}/rest/v1/trades", json=[full_payload], headers=headers, timeout=5.0)
            if r.status_code >= 400:
                httpx.post(f"{url}/rest/v1/trades", json=[base_payload], headers=headers, timeout=5.0)
        except Exception as e:
            print(f"Supabase record_trade sync error: {e}")

def update_trade_classification(trade_id: int, category: str, is_strategy: int, layer: Optional[str] = None, reason: Optional[str] = None):
    conn = get_connection()
    cursor = conn.cursor()
    fields = ["category = ?", "is_strategy = ?"]
    params = [category, int(is_strategy)]
    if layer:
        fields.append("layer = ?")
        params.append(layer)
    if reason is not None:
        fields.append("reason = ?")
        params.append(reason)
    params.append(trade_id)
    sql = f"UPDATE trades SET {', '.join(fields)} WHERE id = ?"
    cursor.execute(sql, params)
    conn.commit()
    conn.close()

    url, key = get_supabase_credentials()
    if url and key:
        try:
            import httpx
            headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {"category": category, "is_strategy": int(is_strategy)}
            if layer:
                payload["layer"] = layer
            if reason is not None:
                payload["reason"] = reason
            httpx.patch(f"{url}/rest/v1/trades?id=eq.{trade_id}", json=payload, headers=headers, timeout=5.0)
        except Exception as e:
            print(f"Supabase update_trade_classification error: {e}")

def execute_live_us_trade(date_str, ticker, action, price, shares, fee=0.0, layer="TREND", reason="实盘手工登记", category="STRATEGY", is_strategy=1):
    total_val = price * shares
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT shares, cost_basis FROM positions WHERE ticker = ?", (ticker,))
    row = cursor.fetchone()
    current_shares = row[0] if row else 0.0
    current_cost = row[1] if row else price
    if layer == "TREND":
        layer = "L0" if ticker == "JEPQ" else ("SGOV" if ticker == "SGOV" else ("L2" if ticker == "QLD" else ("Non-Equity" if ticker in ["GLD", "TLT", "DBC", "BITO"] else ("L1" if ticker in ["SPY", "QQQ", "SOXX"] else "TREND"))))
    pos_df = get_positions()
    existing_row = pos_df[pos_df['ticker'] == ticker] if not pos_df.empty and 'ticker' in pos_df.columns else pd.DataFrame()
    if not existing_row.empty:
        current_shares = float(existing_row.iloc[0]['shares'])
        current_cost = float(existing_row.iloc[0]['cost_basis'])
        if str(existing_row.iloc[0]['layer']) in ['L0', 'SGOV', 'L1', 'L2', 'Non-Equity', 'LEGACY']:
            layer = str(existing_row.iloc[0]['layer'])
    
    pnl = 0.0
    if action.upper() == "BUY":
        new_shares = current_shares + shares
        new_cost = (current_shares * current_cost + total_val + fee) / new_shares if new_shares > 0 else price
        update_position(ticker, new_shares, new_cost, layer)
    else: # SELL
        new_shares = max(0.0, current_shares - shares)
        pnl = (price - current_cost) * shares - fee
        update_position(ticker, new_shares, current_cost if new_shares > 0 else 0.0, layer)

    record_trade(date_str, ticker, action.upper(), shares, price, total_val, fee, pnl, layer, reason, category=category, is_strategy=is_strategy)


def record_nav(date_str, nav, cash, jepq_val, sgov_val, trend_val,
               total_equity=None, strategy_equity=None, hk_pnl_cum=0.0,
               high_water_mark=None, drawdown_pct=0.0, source='CALCULATED'):
    """Write a NAV row. If total_equity not given, uses nav as both total and strategy."""
    if total_equity is None:
        total_equity = nav
    if strategy_equity is None:
        strategy_equity = nav
    if high_water_mark is None:
        high_water_mark = total_equity
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO nav_history
        (date, nav, cash, jepq_val, sgov_val, trend_val,
         total_equity, strategy_equity, hk_pnl_cum, high_water_mark, drawdown_pct, source)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (date_str, nav, cash, jepq_val, sgov_val, trend_val,
           total_equity, strategy_equity, hk_pnl_cum, high_water_mark, drawdown_pct, source))
    conn.commit()
    conn.close()

    # Cloud Sync to Supabase
    url, key = get_supabase_credentials()
    if url and key:
        try:
            import httpx
            headers = {
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates"
            }
            payload = [{
                "date": str(date_str),
                "nav": float(nav),
                "cash": float(cash),
                "jepq_val": float(jepq_val),
                "sgov_val": float(sgov_val),
                "trend_val": float(trend_val),
                "total_equity": float(total_equity),
                "strategy_equity": float(strategy_equity),
                "hk_pnl_cum": float(hk_pnl_cum),
                "high_water_mark": float(high_water_mark),
                "drawdown_pct": float(drawdown_pct),
                "source": str(source)
            }]
            httpx.post(f"{url}/rest/v1/nav_history?on_conflict=date", json=payload, headers=headers, timeout=5.0)
        except Exception as e:
            print(f"Supabase record_nav sync error: {e}")


def record_brokerage_nav(date_str, total_equity, hk_pnl_cum=0.0):
    """Record a manually-entered Tiger Brokerage equity snapshot."""
    strategy_equity = total_equity - hk_pnl_cum
    conn = get_connection()
    cursor = conn.cursor()
    # Compute running HWM from latest stored
    df_existing = pd.read_sql_query(
        "SELECT high_water_mark FROM nav_history WHERE high_water_mark IS NOT NULL ORDER BY date DESC LIMIT 1",
        conn)
    hwm = float(df_existing['high_water_mark'].iloc[0]) if not df_existing.empty else total_equity
    hwm = max(hwm, total_equity)
    dd = (total_equity - hwm) / hwm * 100.0 if hwm > 0 else 0.0
    cursor.execute("""
    INSERT OR REPLACE INTO nav_history
        (date, nav, cash, jepq_val, sgov_val, trend_val,
         total_equity, strategy_equity, hk_pnl_cum, high_water_mark, drawdown_pct, source)
    VALUES (?, ?, 0, 0, 0, 0, ?, ?, ?, ?, ?, 'BROKERAGE')
    """, (date_str, strategy_equity, total_equity, strategy_equity, hk_pnl_cum, hwm, dd))
    conn.commit()
    conn.close()


def get_nav_history():
    conn = get_connection()
    df_local = pd.read_sql_query(
        "SELECT * FROM nav_history WHERE total_equity IS NOT NULL ORDER BY date ASC",
        conn)
    conn.close()

    df_cloud = fetch_supabase_df("nav_history", order="date.asc")
    if df_cloud is not None and not df_cloud.empty:
        # Ensure all expected columns exist to prevent KeyError on Streamlit UI
        for col in ['total_equity', 'strategy_equity', 'jepq_val', 'sgov_val', 'trend_val', 'hk_pnl_cum', 'high_water_mark', 'drawdown_pct']:
            if col not in df_cloud.columns:
                df_cloud[col] = df_cloud['nav'] if 'nav' in df_cloud.columns else 0.0
        df_cloud = df_cloud[df_cloud['total_equity'].notnull()]
        
        # Merge cloud and local so no historical date is ever omitted
        if not df_local.empty and not df_cloud.empty:
            df_merged = pd.concat([df_cloud, df_local]).drop_duplicates(subset=['date'], keep='first').sort_values('date').reset_index(drop=True)
            return df_merged
        if not df_cloud.empty:
            return df_cloud
    return df_local

def get_trades_history():
    df_cloud = fetch_supabase_df("trades", select="*", order="id.desc")
    if df_cloud is not None and not df_cloud.empty:
        if 'id' in df_cloud.columns:
            df_cloud['id'] = pd.to_numeric(df_cloud['id'], errors='coerce')
            df_cloud = df_cloud.sort_values(by="id", ascending=False).reset_index(drop=True)
        if 'category' not in df_cloud.columns:
            df_cloud['category'] = 'STRATEGY'
        else:
            df_cloud['category'] = df_cloud['category'].fillna('STRATEGY')
        if 'is_strategy' not in df_cloud.columns:
            df_cloud['is_strategy'] = 1
        else:
            df_cloud['is_strategy'] = pd.to_numeric(df_cloud['is_strategy'].fillna(1), errors='coerce').astype(int)
        return df_cloud
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM trades ORDER BY id DESC", conn)
    conn.close()
    if 'category' not in df.columns:
        df['category'] = 'STRATEGY'
    if 'is_strategy' not in df.columns:
        df['is_strategy'] = 1
    return df

def get_pending_actions():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM pending_actions WHERE status = 'PENDING' ORDER BY id ASC", conn)
    conn.close()
    return df

def resolve_pending_action(action_id, new_status="CONFIRMED"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE pending_actions SET status = ? WHERE id = ?", (new_status, action_id))
    conn.commit()
    conn.close()

def get_hk_ipo_trades_history():
    df_cloud = fetch_supabase_df("hk_ipo_trades", order="id.desc")
    if df_cloud is not None and not df_cloud.empty:
        return df_cloud
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM hk_ipo_trades ORDER BY id DESC", conn)
    conn.close()
    return df

def get_latest_kids_returns():
    """Returns dynamic accumulated total asset balance for Hiro and Caspar (e.g. 165.29, 165.23 RMB)."""
    try:
        from core.ipo.tracker import get_dynamic_kids_available_capital
        return get_dynamic_kids_available_capital()
    except Exception:
        return 165.29, 165.23

def sync_hk_ipo_pnl_to_nav():
    """Sync cumulative HK IPO profit from hk_ipo_trades to latest nav_history."""
    conn = get_connection()
    df_trades = pd.read_sql_query("SELECT hkd_profit FROM hk_ipo_trades", conn)
    total_hkd = float(df_trades['hkd_profit'].sum()) if not df_trades.empty else 0.0
    total_usd = total_hkd / 7.8
    
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE nav_history 
    SET hk_pnl_cum = ?,
        total_equity = strategy_equity + ?
    WHERE date = (SELECT MAX(date) FROM nav_history)
    """, (total_usd, total_usd))
    conn.commit()
    conn.close()

def record_hk_ipo_trade(
    ticker_name, market, margin_principal, allocated_shares, ipo_fee,
    won_shares, won_price, sell_price, trade_fee,
    hiro_capital, caspar_capital, multiplier,
    start_date, settle_date
):
    total_fee = ipo_fee + trade_fee
    if won_shares > 0 and won_price is not None and sell_price is not None:
        profit_amt = (sell_price - won_price) * won_shares - total_fee
    else:
        profit_amt = -total_fee
        
    roi = profit_amt / margin_principal if margin_principal > 0 else 0.0
    # Educational incentive: 5x/10x on profits, 1x on losses (protects child motivation)
    effective_mult = multiplier if roi > 0 else 1.0
    
    hiro_profit = round(hiro_capital * roi * effective_mult, 2)
    hiro_return = round(hiro_capital + hiro_profit, 2)
    
    caspar_profit = round(caspar_capital * roi * effective_mult, 2)
    caspar_return = round(caspar_capital + caspar_profit, 2)
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO hk_ipo_trades (
        ticker_name, market, margin_principal, allocated_shares, ipo_fee,
        won_shares, won_price, sell_price, trade_fee, total_fee,
        profit_amt, roi, multiplier,
        hiro_capital, hiro_profit, hiro_return,
        caspar_capital, caspar_profit, caspar_return,
        exchange_rate, hkd_principal, hkd_total_fee, hkd_profit,
        start_date, settle_date
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1.0, ?, ?, ?, ?, ?)
    """, (
        ticker_name, market, margin_principal, allocated_shares, ipo_fee,
        won_shares, won_price, sell_price, trade_fee, total_fee,
        profit_amt, roi, multiplier,
        hiro_capital, hiro_profit, hiro_return,
        caspar_capital, caspar_profit, caspar_return,
        margin_principal, total_fee, profit_amt,
        start_date, settle_date
    ))
    conn.commit()
    conn.close()
    
    # Auto sync total profit to NAV history table
    sync_hk_ipo_pnl_to_nav()
    
    # Sync to Supabase Cloud hk_ipo_trades table
    url, key = get_supabase_credentials()
    if url and key:
        try:
            import httpx
            headers = {
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            }
            # Self-Healing: Compute next_id to prevent Postgres sequence offset 409 conflicts
            df_cur = fetch_supabase_df("hk_ipo_trades", select="id", order="id.desc")
            next_id = 1
            if df_cur is not None and not df_cur.empty and 'id' in df_cur.columns:
                next_id = int(df_cur['id'].max()) + 1

            payload = {
                "id": next_id,
                "ticker_name": ticker_name,
                "market": market,
                "margin_principal": float(margin_principal),
                "allocated_shares": float(allocated_shares),
                "ipo_fee": float(ipo_fee),
                "won_shares": float(won_shares),
                "won_price": float(won_price) if won_price is not None else None,
                "sell_price": float(sell_price) if sell_price is not None else None,
                "trade_fee": float(trade_fee),
                "total_fee": float(total_fee),
                "profit_amt": float(profit_amt),
                "roi": float(roi),
                "multiplier": float(multiplier),
                "hiro_capital": float(hiro_capital),
                "hiro_profit": float(hiro_profit),
                "hiro_return": float(hiro_return),
                "caspar_capital": float(caspar_capital),
                "caspar_profit": float(caspar_profit),
                "caspar_return": float(caspar_return),
                "exchange_rate": 1.0,
                "hkd_principal": float(margin_principal),
                "hkd_total_fee": float(total_fee),
                "hkd_profit": float(profit_amt),
                "start_date": start_date,
                "settle_date": settle_date
            }
            resp = httpx.post(f"{url}/rest/v1/hk_ipo_trades", json=payload, headers=headers, timeout=10.0)
            if resp.status_code not in [200, 201, 204]:
                print(f"record_hk_ipo_trade Supabase Sync Warning: {resp.status_code} {resp.text}")
            else:
                print(f"✅ Successfully inserted HK IPO trade to Supabase Cloud with id={next_id}!")
        except Exception as e:
            print(f"record_hk_ipo_trade Supabase Sync Exception: {e}")


def init_kids_ledger_table():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS kids_cash_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        kid_name TEXT,
        action_type TEXT,
        amount REAL,
        balance_after REAL,
        notes TEXT
    )
    """)
    
    # Seed baseline records if empty with true 100 RMB deposits
    cursor.execute("SELECT COUNT(*) FROM kids_cash_ledger")
    cnt = cursor.fetchone()[0]
    if cnt == 0:
        cursor.execute("INSERT INTO kids_cash_ledger (date, kid_name, action_type, amount, balance_after, notes) VALUES (?, ?, ?, ?, ?, ?)",
                       ('2026-06-01', 'CASPAR', 'DEPOSIT', 100.0, 100.0, '创想三维打新首次入金'))
        cursor.execute("INSERT INTO kids_cash_ledger (date, kid_name, action_type, amount, balance_after, notes) VALUES (?, ?, ?, ?, ?, ?)",
                       ('2026-06-02', 'HIRO', 'DEPOSIT', 100.0, 100.0, '首钢朗泽打新首次入金'))
    conn.commit()
    conn.close()

def record_kids_cash_transaction(date_str, kid_name, action_type, amount, notes):
    """
    action_type: 'DEPOSIT' (入金), 'WITHDRAWAL' (微信提现)
    """
    init_kids_ledger_table()
    conn = get_connection()
    cursor = conn.cursor()
    
    # Calculate current balance from ledger deposits/withdrawals + IPO profit
    summary = get_kids_account_summary(kid_name)
    curr_bal = summary['balance']

    if action_type == 'WITHDRAWAL':
        net_change = -abs(amount)
    else:
        net_change = amount

    new_bal = curr_bal + net_change

    cursor.execute("""
    INSERT INTO kids_cash_ledger (date, kid_name, action_type, amount, balance_after, notes)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (date_str, kid_name, action_type, amount, new_bal, notes))
    conn.commit()
    conn.close()
    
    # Sync to Supabase kids_cash_ledger table with Self-Healing Next ID
    url, key = get_supabase_credentials()
    if url and key:
        try:
            import httpx
            headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            df_cur_k = fetch_supabase_df("kids_cash_ledger", select="id", order="id.desc")
            next_kid_id = 1
            if df_cur_k is not None and not df_cur_k.empty and 'id' in df_cur_k.columns:
                next_kid_id = int(df_cur_k['id'].max()) + 1
            payload = {
                "id": next_kid_id,
                "date": date_str,
                "kid_name": kid_name,
                "action_type": action_type,
                "amount": float(amount),
                "balance_after": float(new_bal),
                "notes": notes
            }
            httpx.post(f"{url}/rest/v1/kids_cash_ledger", json=payload, headers=headers, timeout=5.0)
        except Exception:
            pass

    return new_bal

def get_kids_cash_ledger():
    df_cloud = fetch_supabase_df("kids_cash_ledger", order="date.asc")
    if df_cloud is not None and not df_cloud.empty:
        return df_cloud
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM kids_cash_ledger ORDER BY date ASC", conn)
    conn.close()
    return df

def get_cloud_market_prices_latest_dates(tickers=None):
    """ Efficiently fetch latest alignment date for each ticker from Supabase market_prices """
    url, key = get_supabase_credentials()
    if not url or not key:
        return {}
    if tickers is None:
        tickers = ["DBC", "SPY", "QQQ", "SOXX", "QLD", "GLD", "TLT", "BITO", "JEPQ", "SGOV"]
    import httpx
    headers = {"apikey": str(key), "Authorization": f"Bearer {str(key)}"}
    result = {}
    for t in tickers:
        for _ in range(2):
            try:
                r = httpx.get(f"{str(url)}/rest/v1/market_prices?ticker=eq.{t}&select=date&order=date.desc&limit=1", headers=headers, timeout=4.0)
                if r.status_code == 200 and r.json():
                    result[t] = str(r.json()[0]['date'])[:10]
                    break
            except Exception:
                pass
    return result

def fetch_cloud_market_prices(ticker):
    """ Fetch historical price data from Supabase Cloud market_prices table """
    df_cloud = fetch_supabase_df(f"market_prices?ticker=eq.{ticker}", order="date.desc&limit=1000")
    if df_cloud is not None and not df_cloud.empty:
        df_cloud['Date'] = pd.to_datetime(df_cloud['date'])
        df_cloud = df_cloud.rename(columns={
            'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'
        })
        for c in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if c in df_cloud.columns:
                df_cloud[c] = pd.to_numeric(df_cloud[c], errors='coerce')
        df_cloud = df_cloud.sort_values('Date').reset_index(drop=True)
        return df_cloud
    return None

def upsert_cloud_market_price_rows(rows):
    """ Upsert a list of daily price bar dictionaries to Supabase market_prices table """
    url, key = get_supabase_credentials()
    if url and key and rows:
        try:
            import httpx
            url_str = str(url)
            key_str = str(key)
            headers = {
                "apikey": key_str,
                "Authorization": f"Bearer {key_str}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates"
            }
            # Explicitly specify on_conflict=ticker,date for PostgREST UPSERT
            httpx.post(f"{url_str}/rest/v1/market_prices?on_conflict=ticker,date", json=rows, headers=headers, timeout=15.0)
        except Exception as e:
            print(f"upsert_cloud_market_price_rows error: {e}")

def get_kids_account_summary(kid_name):
    init_kids_ledger_table()
    
    # 1. Net Cash Deposits and Withdrawals from kids_cash_ledger (Cloud first)
    df_ledger = get_kids_cash_ledger()
    if df_ledger is not None and not df_ledger.empty and 'kid_name' in df_ledger.columns:
        df_k = df_ledger[df_ledger['kid_name'] == kid_name]
        tot_dep = float(df_k[df_k['action_type'] == 'DEPOSIT']['amount'].sum()) if not df_k.empty else 100.0
        tot_wd  = float(df_k[df_k['action_type'] == 'WITHDRAWAL']['amount'].sum()) if not df_k.empty else 0.0
    else:
        tot_dep = 100.0
        tot_wd = 0.0
    
    # 2. Cumulative IPO Profits from hk_ipo_trades (Cloud first)
    df_trades = get_hk_ipo_trades_history()
    
    if df_trades is not None and not df_trades.empty and 'id' in df_trades.columns:
        df_trades['id'] = pd.to_numeric(df_trades['id'], errors='coerce')
        if 'hiro_profit' in df_trades.columns:
            df_trades['hiro_profit'] = pd.to_numeric(df_trades['hiro_profit'], errors='coerce').fillna(0.0)
        if 'caspar_profit' in df_trades.columns:
            df_trades['caspar_profit'] = pd.to_numeric(df_trades['caspar_profit'], errors='coerce').fillna(0.0)
            
        if kid_name == 'HIRO':
            # Active profits starting at 首钢朗泽 (ID >= 93)
            active_prof = float(df_trades[df_trades['id'] >= 93]['hiro_profit'].sum())
            # Early settled profits before 首钢朗泽 (ID < 93)
            early_settled_prof = float(df_trades[df_trades['id'] < 93]['hiro_profit'].sum())
        else:
            # Active profits starting at 创想三维 (ID >= 92)
            active_prof = float(df_trades[df_trades['id'] >= 92]['caspar_profit'].sum())
            # Early settled profits before 创想三维 (ID < 92)
            early_settled_prof = float(df_trades[df_trades['id'] < 92]['caspar_profit'].sum())
    else:
        active_prof = 65.29 if kid_name == 'HIRO' else 65.23
        early_settled_prof = -0.43 if kid_name == 'HIRO' else -6.71
        
    tot_bal = (tot_dep - tot_wd) + active_prof
    lifetime_total_profit = active_prof + early_settled_prof
    
    return {
        'balance': tot_bal,
        'active_profit': active_prof,
        'early_settled_profit': early_settled_prof,
        'total_deposit': tot_dep,
        'total_withdrawal': tot_wd,
        'lifetime_total_profit': lifetime_total_profit
    }
