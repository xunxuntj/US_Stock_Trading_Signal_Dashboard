import sqlite3
import pandas as pd
import datetime
from config import DB_PATH, INITIAL_CAPITAL, JEPQ_TARGET_PCT, SGOV_TARGET_PCT

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

def get_positions():
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

def record_trade(date_str, ticker, action, shares, price, total_val, fee=0.0, pnl=0.0, layer="TREND", reason=""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO trades (date, ticker, action, shares, price, total_val, fee, pnl, layer, reason)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (date_str, ticker, action, shares, price, total_val, fee, pnl, layer, reason))
    conn.commit()
    conn.close()

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


def record_nav(date_str, nav, cash, jepq_val, sgov_val, trend_val):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO nav_history (date, nav, cash, jepq_val, sgov_val, trend_val)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (date_str, nav, cash, jepq_val, sgov_val, trend_val))
    conn.commit()
    conn.close()

def get_nav_history():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM nav_history ORDER BY date ASC", conn)
    conn.close()
    return df

def get_trades_history():
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
