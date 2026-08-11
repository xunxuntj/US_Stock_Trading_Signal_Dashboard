import sqlite3
import pandas as pd
import datetime
from config import DB_PATH, INITIAL_CAPITAL, JEPQ_TARGET_PCT, SGOV_TARGET_PCT

import os

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

def record_cash_transaction(date_str, trans_type, amount, notes=""):
    conn = get_connection()
    cursor = conn.cursor()
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
        if hasattr(st, "secrets"):
            url = st.secrets.get("SUPABASE_URL")
            key = st.secrets.get("SUPABASE_KEY") or st.secrets.get("SUPABASE_SECRET_KEY")
    except Exception:
        pass
    if not url:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SECRET_KEY")
    return url, key

def fetch_supabase_df(table_name, select="*", order=None):
    url, key = get_supabase_credentials()
    if not url or not key:
        return None
    try:
        import httpx
        headers = {"apikey": key, "Authorization": f"Bearer {key}"}
        req_url = f"{url}/rest/v1/{table_name}?select={select}"
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
    df_cloud = fetch_supabase_df("positions", order="ticker.asc")
    if df_cloud is not None and not df_cloud.empty:
        return df_cloud
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM positions", conn)
    conn.close()
    return df

def update_position(ticker, shares, cost_basis, layer):
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if shares <= 0:
        cursor.execute("DELETE FROM positions WHERE ticker = ?", (ticker,))
    else:
        cursor.execute("""
        INSERT INTO positions (ticker, shares, cost_basis, layer, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
            shares = excluded.shares,
            cost_basis = excluded.cost_basis,
            updated_at = excluded.updated_at
        """, (ticker, shares, cost_basis, layer, now_str))
    conn.commit()
    conn.close()

    # Cloud Sync to Supabase
    url, key = get_supabase_credentials()
    if url and key:
        try:
            import httpx
            headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"}
            httpx.post(f"{url}/rest/v1/positions", json=[{
                "ticker": ticker, "shares": float(shares), "cost_basis": float(cost_basis), "layer": layer, "updated_at": now_str
            }], headers=headers, timeout=5.0)
        except Exception as e:
            print(f"Supabase update_position sync error: {e}")

def record_trade(date_str, ticker, action, shares, price, total_val, fee=0.0, pnl=0.0, layer="TREND", reason=""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO trades (date, ticker, action, shares, price, total_val, fee, pnl, layer, reason)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (date_str, ticker, action, shares, price, total_val, fee, pnl, layer, reason))
    conn.commit()
    conn.close()

    # Cloud Sync to Supabase
    url, key = get_supabase_credentials()
    if url and key:
        try:
            import httpx
            headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            httpx.post(f"{url}/rest/v1/trades", json=[{
                "date": str(date_str), "ticker": ticker, "action": action, "shares": float(shares),
                "price": float(price), "total_val": float(total_val), "fee": float(fee), "pnl": float(pnl),
                "layer": layer, "reason": str(reason)
            }], headers=headers, timeout=5.0)
        except Exception as e:
            print(f"Supabase record_trade sync error: {e}")

def execute_live_us_trade(date_str, ticker, action, price, shares, fee=0.0, layer="TREND", reason="实盘手工登记"):
    total_val = price * shares
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT shares, cost_basis FROM positions WHERE ticker = ?", (ticker,))
    row = cursor.fetchone()
    current_shares = row[0] if row else 0.0
    current_cost = row[1] if row else price
    
    pnl = 0.0
    if action.upper() == "BUY":
        new_shares = current_shares + shares
        new_cost = (current_shares * current_cost + total_val + fee) / new_shares if new_shares > 0 else price
        update_position(ticker, new_shares, new_cost, layer)
    else: # SELL
        new_shares = max(0.0, current_shares - shares)
        pnl = (price - current_cost) * shares - fee
        update_position(ticker, new_shares, current_cost if new_shares > 0 else 0.0, layer)

    record_trade(date_str, ticker, action.upper(), shares, price, total_val, fee, pnl, layer, reason)


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
    df_cloud = fetch_supabase_df("nav_history", order="date.asc")
    if df_cloud is not None and not df_cloud.empty:
        # Ensure all expected columns exist to prevent KeyError on Streamlit UI
        for col in ['total_equity', 'strategy_equity', 'jepq_val', 'sgov_val', 'trend_val', 'hk_pnl_cum', 'high_water_mark', 'drawdown_pct']:
            if col not in df_cloud.columns:
                df_cloud[col] = df_cloud['nav'] if 'nav' in df_cloud.columns else 0.0
        df_cloud = df_cloud[df_cloud['total_equity'].notnull()]
        if not df_cloud.empty:
            return df_cloud
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM nav_history WHERE total_equity IS NOT NULL ORDER BY date ASC",
        conn)
    conn.close()
    return df

def get_trades_history():
    df_cloud = fetch_supabase_df("trades", select="*", order="id.desc")
    if df_cloud is not None and not df_cloud.empty:
        if 'id' in df_cloud.columns:
            df_cloud['id'] = pd.to_numeric(df_cloud['id'], errors='coerce')
            df_cloud = df_cloud.sort_values(by="id", ascending=False).reset_index(drop=True)
        return df_cloud
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM trades ORDER BY id DESC", conn)
    conn.close()
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
    """Returns baseline accumulated total asset balance for Hiro (143.84 RMB) and Caspar (143.79 RMB)."""
    return 143.84, 143.79

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
    
    hiro_profit = hiro_capital * roi * multiplier
    hiro_return = hiro_capital + hiro_profit
    
    caspar_profit = caspar_capital * roi * multiplier
    caspar_return = caspar_capital + caspar_profit
    
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
    
    # Log kids IPO settlement
    if hiro_profit != 0:
        record_kids_cash_transaction(settle_date, 'HIRO', 'IPO_SETTLE', hiro_profit, f"{ticker_name} 打新结算收益")
    if caspar_profit != 0:
        record_kids_cash_transaction(settle_date, 'CASPAR', 'IPO_SETTLE', caspar_profit, f"{ticker_name} 打新结算收益")

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

def get_kids_cash_ledger():
    df_cloud = fetch_supabase_df("kids_cash_ledger", order="id.asc")
    if df_cloud is not None and not df_cloud.empty:
        return df_cloud
    init_kids_ledger_table()
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM kids_cash_ledger ORDER BY id ASC", conn)
    conn.close()
    return df

def get_kids_account_summary(kid_name):
    init_kids_ledger_table()
    conn = get_connection()
    
    # 1. Net Cash Deposits and Withdrawals from kids_cash_ledger
    df_ledger = pd.read_sql_query(
        "SELECT action_type, amount FROM kids_cash_ledger WHERE kid_name = ?",
        conn, params=(kid_name,)
    )
    tot_dep = float(df_ledger[df_ledger['action_type'] == 'DEPOSIT']['amount'].sum()) if not df_ledger.empty else 100.0
    tot_wd  = float(df_ledger[df_ledger['action_type'] == 'WITHDRAWAL']['amount'].sum()) if not df_ledger.empty else 0.0
    
    # 2. Cumulative IPO Profits from hk_ipo_trades
    df_trades = pd.read_sql_query("SELECT id, hiro_profit, caspar_profit FROM hk_ipo_trades ORDER BY id ASC", conn)
    conn.close()
    
    if kid_name == 'HIRO':
        # Active profits starting at 首钢朗泽 (ID >= 93)
        active_prof = float(df_trades[df_trades['id'] >= 93]['hiro_profit'].sum()) if not df_trades.empty else 43.85
        # Early settled profits before 首钢朗泽 (ID < 93)
        early_settled_prof = float(df_trades[df_trades['id'] < 93]['hiro_profit'].sum()) if not df_trades.empty else -0.43
    else:
        # Active profits starting at 创想三维 (ID >= 92)
        active_prof = float(df_trades[df_trades['id'] >= 92]['caspar_profit'].sum()) if not df_trades.empty else 43.80
        # Early settled profits before 创想三维 (ID < 92)
        early_settled_prof = float(df_trades[df_trades['id'] < 92]['caspar_profit'].sum()) if not df_trades.empty else -6.71
        
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
