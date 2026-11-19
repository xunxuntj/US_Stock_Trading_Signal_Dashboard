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
    "get_supabase_credentials", "fetch_supabase_df",
    "save_broker_refresh_token", "get_broker_refresh_token",
    "save_account_balances", "get_account_balances"
]

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Current Positions Table (Composite PK: ticker + account so multi-broker holdings never collide)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS positions (
        ticker TEXT NOT NULL,
        shares REAL NOT NULL,
        cost_basis REAL NOT NULL,
        layer TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        account TEXT NOT NULL DEFAULT '老虎证券 - 综合账户',
        PRIMARY KEY (ticker, account)
    )
    """)
    cursor.execute("PRAGMA table_info(positions)")
    pos_cols_info = cursor.fetchall()
    pk_cols = [r[1] for r in pos_cols_info if r[5] > 0]
    col_names = [r[1] for r in pos_cols_info]
    if "account" not in col_names or pk_cols == ["ticker"]:
        # Seamless migration from single-ticker PK to composite (ticker, account) PK
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS positions_v2 (
            ticker TEXT NOT NULL,
            shares REAL NOT NULL,
            cost_basis REAL NOT NULL,
            layer TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            account TEXT NOT NULL DEFAULT '老虎证券 - 综合账户',
            PRIMARY KEY (ticker, account)
        )
        """)
        if "account" in col_names:
            cursor.execute("""
            INSERT OR REPLACE INTO positions_v2 (ticker, shares, cost_basis, layer, updated_at, account)
            SELECT ticker, shares, cost_basis, layer, updated_at,
                   CASE WHEN account IS NULL OR TRIM(account) = '' THEN '老虎证券 - 综合账户' ELSE account END
            FROM positions
            """)
        else:
            cursor.execute("""
            INSERT OR REPLACE INTO positions_v2 (ticker, shares, cost_basis, layer, updated_at, account)
            SELECT ticker, shares, cost_basis, layer, updated_at, '老虎证券 - 综合账户'
            FROM positions
            """)
        cursor.execute("DROP TABLE positions")
        cursor.execute("ALTER TABLE positions_v2 RENAME TO positions")
    
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
        cursor.execute("ALTER TABLE trades ADD COLUMN account TEXT DEFAULT '老虎证券 - 综合账户'")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE cash_transactions ADD COLUMN account TEXT DEFAULT '老虎证券 - 综合账户'")
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

    # 9. Broker OAuth Tokens Table (e.g. Charles Schwab 7-day refresh token sync)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS broker_tokens (
        broker TEXT PRIMARY KEY,
        refresh_token TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)

    # 10. Per-Account Live Cash & Equity Snapshots Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS account_balances (
        account TEXT PRIMARY KEY,
        broker TEXT NOT NULL,
        equity REAL NOT NULL,
        cash REAL NOT NULL,
        market_value REAL NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()

def record_cash_transaction(date_str, trans_type, amount, notes="", account=None):
    if not account:
        account = "Charles Schwab (嘉信理财)" if ("Schwab" in str(notes) or "嘉信" in str(notes)) else "老虎证券 - 综合账户"
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
            # Convert only numeric columns; preserve all text/ID/token/account columns intact
            str_cols = {
                'date', 'ticker', 'action', 'layer', 'reason', 'notes', 'kid_name',
                'action_type', 'ticker_name', 'market', 'start_date', 'settle_date',
                'source', 'type', 'updated_at', 'account', 'category', 'broker', 'refresh_token'
            }
            for col in df.columns:
                if col not in str_cols:
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

        # Build fallback account map from local positions and recent trades (handles Supabase tables lacking 'account' col)
        trade_acc_map = {}
        if (df['account'].fillna('').astype(str).str.strip() == '').any():
            try:
                conn_loc = get_connection()
                loc_rows = conn_loc.execute("SELECT ticker, account FROM positions WHERE account IS NOT NULL AND account != ''").fetchall()
                conn_loc.close()
                for tk, ac in loc_rows:
                    trade_acc_map[str(tk).upper().strip()] = str(ac).strip()
            except Exception:
                pass
            try:
                df_tr_acc = get_trades_history()
                if df_tr_acc is not None and not df_tr_acc.empty and 'account' in df_tr_acc.columns:
                    for _, trow in df_tr_acc.iterrows():
                        tk = str(trow.get('ticker') or '').upper().strip()
                        ac = str(trow.get('account') or '').strip()
                        if tk and tk not in trade_acc_map and ac:
                            trade_acc_map[tk] = ac
            except Exception:
                pass

        def _assign_acc(row):
            acc = str(row.get('account') or '').strip()
            if acc.lower() == 'nan':
                acc = ''
            t = str(row.get('ticker') or '').upper().strip()
            if not acc and t in trade_acc_map:
                acc = trade_acc_map[t]
            if acc and ('SCHWAB' in acc.upper() or '嘉信' in acc):
                if '老虎' in acc or '综合' in acc or '环球' in acc:
                    return acc
                return 'Charles Schwab (嘉信理财)'
            if acc and ('U9959007' in acc or '环球' in acc) and ('综合' not in acc):
                return '老虎证券 - 环球账户'
            if acc and ('638812' in acc or '综合' in acc) and ('环球' not in acc):
                return '老虎证券 - 综合账户'
            if acc:
                return acc
            return '老虎证券 - 综合账户'
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
    acc_norm = str(account or "").strip() or "老虎证券 - 综合账户"
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if shares <= 0:
        if account:
            cursor.execute("DELETE FROM positions WHERE ticker = ? AND account = ?", (ticker, acc_norm))
        else:
            cursor.execute("DELETE FROM positions WHERE ticker = ?", (ticker,))
    else:
        cursor.execute("""
        INSERT INTO positions (ticker, shares, cost_basis, layer, updated_at, account)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, account) DO UPDATE SET
            shares = excluded.shares,
            cost_basis = excluded.cost_basis,
            layer = excluded.layer,
            updated_at = excluded.updated_at
        """, (ticker, shares, cost_basis, layer, now_str, acc_norm))
    conn.commit()
    conn.close()

    # Cloud Sync to Supabase
    url, key = get_supabase_credentials()
    if url and key:
        try:
            import httpx
            import urllib.parse
            headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            if shares <= 0:
                if account:
                    enc_acc = urllib.parse.quote(acc_norm, safe="")
                    r_del = httpx.delete(
                        f"{url}/rest/v1/positions?ticker=eq.{ticker}&account=eq.{enc_acc}",
                        headers=headers, timeout=5.0
                    )
                    if r_del.status_code >= 400:
                        httpx.delete(f"{url}/rest/v1/positions?ticker=eq.{ticker}", headers=headers, timeout=5.0)
                else:
                    httpx.delete(f"{url}/rest/v1/positions?ticker=eq.{ticker}", headers=headers, timeout=5.0)
            else:
                headers["Prefer"] = "resolution=merge-duplicates"
                base_p = {
                    "ticker": ticker, "shares": float(shares), "cost_basis": float(cost_basis), "layer": layer, "updated_at": now_str
                }
                full_p = dict(base_p)
                full_p["account"] = acc_norm
                r = httpx.post(f"{url}/rest/v1/positions?on_conflict=ticker,account", json=[full_p], headers=headers, timeout=5.0)
                if r.status_code >= 400:
                    # Fallback if Supabase positions table still uses single-column PK
                    r2 = httpx.post(f"{url}/rest/v1/positions", json=[full_p], headers=headers, timeout=5.0)
                    if r2.status_code >= 400:
                        httpx.post(f"{url}/rest/v1/positions", json=[base_p], headers=headers, timeout=5.0)
        except Exception as e:
            print(f"Supabase update_position sync error: {e}")

def record_trade(date_str, ticker, action, shares, price, total_val, fee=0.0, pnl=0.0, layer="TREND", reason="", category="STRATEGY", is_strategy=1, account=None):
    if not account:
        r_u = str(reason or "").upper()
        if "SCHWAB" in r_u or "嘉信" in r_u:
            account = "Charles Schwab (嘉信理财)"
        else:
            account = "老虎证券 - 综合账户"
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
            full_payload["account"] = str(account)
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
        if 'account' not in df_cloud.columns:
            df_cloud['account'] = ''

        def _infer_trade_acc(row):
            acc = str(row.get('account') or '').strip()
            if acc and acc.lower() != 'nan':
                return acc
            rsn = str(row.get('reason') or '').upper()
            if 'SCHWAB' in rsn or '嘉信' in rsn:
                return 'Charles Schwab (嘉信理财)'
            return '老虎证券 - 综合账户'

        df_cloud['account'] = df_cloud.apply(_infer_trade_acc, axis=1)
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


def save_broker_refresh_token(broker: str, refresh_token: str):
    """Persist latest broker OAuth refresh token to local SQLite and Supabase Cloud."""
    broker_key = str(broker).upper().strip()
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS broker_tokens (
            broker TEXT PRIMARY KEY,
            refresh_token TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)
        cur.execute("""
        INSERT INTO broker_tokens (broker, refresh_token, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(broker) DO UPDATE SET
            refresh_token = excluded.refresh_token,
            updated_at = excluded.updated_at
        """, (broker_key, refresh_token, now_iso))
        conn.commit()
    finally:
        conn.close()

    url, key = get_supabase_credentials()
    if url and key:
        try:
            import httpx
            headers = {
                "apikey": str(key),
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates"
            }
            payload = [{"broker": broker_key, "refresh_token": refresh_token, "updated_at": now_iso}]
            r = httpx.post(
                f"{url}/rest/v1/broker_tokens?on_conflict=broker",
                json=payload, headers=headers, timeout=10.0
            )
            if r.status_code < 400:
                return True, "synced_to_cloud"
            return False, f"Supabase HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            return False, str(e)
    return False, "no_supabase_credentials"


def get_broker_refresh_token(broker: str = "SCHWAB"):
    """Fetch latest broker refresh token (Cloud first, fallback to local SQLite). Returns (token, updated_at)."""
    broker_key = str(broker).upper().strip()
    df_cloud = fetch_supabase_df(f"broker_tokens?broker=eq.{broker_key}")
    if df_cloud is not None and not df_cloud.empty:
        row = df_cloud.iloc[0]
        tok = str(row.get("refresh_token") or "").strip()
        upd = str(row.get("updated_at") or "").strip()
        if tok:
            return tok, upd

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT refresh_token, updated_at FROM broker_tokens WHERE broker = ?", (broker_key,))
        row = cur.fetchone()
        if row and row[0]:
            return str(row[0]).strip(), str(row[1] or "").strip()
    except Exception:
        pass
    finally:
        conn.close()

    return None, None


def _supabase_post_with_retry(req_url: str, payload: list, headers: dict, retries: int = 2, timeout: float = 10.0):
    """Execute a Supabase REST POST with brief exponential backoff on transient failures."""
    import time
    import httpx
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = httpx.post(req_url, json=payload, headers=headers, timeout=timeout)
            if r.status_code < 500:
                return r
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            last_err = str(e)
        if attempt < retries:
            time.sleep(0.5 * (2 ** attempt))
    raise RuntimeError(f"Supabase POST failed after {retries + 1} attempts: {last_err}")


def save_account_balances(accounts_detail: List[Dict[str, Any]]):
    """Persist per-account real cash & equity snapshots to local SQLite and Supabase Cloud."""
    if not accounts_detail:
        return False, "empty"
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows_to_sync = []
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS account_balances (
            account TEXT PRIMARY KEY,
            broker TEXT NOT NULL,
            equity REAL NOT NULL,
            cash REAL NOT NULL,
            market_value REAL NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)
        for acc in accounts_detail:
            acc_name = str(acc.get("account_name") or "").strip()
            if not acc_name:
                continue
            broker_name = str(acc.get("broker") or "UNKNOWN").upper().strip()
            eq = round(float(acc.get("equity", 0.0) or 0.0), 2)
            cash = round(float(acc.get("cash", 0.0) or 0.0), 2)
            mkt = round(float(acc.get("market_value", 0.0) or 0.0), 2)
            cur.execute("""
            INSERT INTO account_balances (account, broker, equity, cash, market_value, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(account) DO UPDATE SET
                broker = excluded.broker,
                equity = excluded.equity,
                cash = excluded.cash,
                market_value = excluded.market_value,
                updated_at = excluded.updated_at
            """, (acc_name, broker_name, eq, cash, mkt, now_iso))
            rows_to_sync.append({
                "account": acc_name,
                "broker": broker_name,
                "equity": eq,
                "cash": cash,
                "market_value": mkt,
                "updated_at": now_iso,
            })
        conn.commit()
    finally:
        conn.close()

    url, key = get_supabase_credentials()
    if url and key and rows_to_sync:
        try:
            headers = {
                "apikey": str(key),
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates",
            }
            r = _supabase_post_with_retry(
                f"{url}/rest/v1/account_balances?on_conflict=account",
                rows_to_sync, headers=headers
            )
            if r.status_code < 400:
                return True, "synced_to_cloud"
            return False, f"Supabase HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            return False, str(e)
    return False, "local_only"


def get_account_balances() -> Dict[str, Dict[str, Any]]:
    """Fetch latest per-account balance snapshots (Cloud first, fallback to local SQLite)."""
    df_cloud = fetch_supabase_df("account_balances")
    if df_cloud is not None and not df_cloud.empty and "account" in df_cloud.columns:
        return {
            str(r["account"]).strip(): {
                "broker": str(r.get("broker") or ""),
                "equity": float(r.get("equity") or 0.0),
                "cash": float(r.get("cash") or 0.0),
                "market_value": float(r.get("market_value") or 0.0),
                "updated_at": str(r.get("updated_at") or ""),
            }
            for _, r in df_cloud.iterrows()
        }

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT account, broker, equity, cash, market_value, updated_at FROM account_balances")
        rows = cur.fetchall()
        return {
            str(r[0]).strip(): {
                "broker": str(r[1] or ""),
                "equity": float(r[2] or 0.0),
                "cash": float(r[3] or 0.0),
                "market_value": float(r[4] or 0.0),
                "updated_at": str(r[5] or ""),
            }
            for r in rows
        }
    except Exception:
        return {}
    finally:
        conn.close()
