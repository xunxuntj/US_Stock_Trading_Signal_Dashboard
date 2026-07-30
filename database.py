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
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM nav_history WHERE total_equity IS NOT NULL ORDER BY date ASC",
        conn)
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

def get_hk_ipo_trades_history():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM hk_ipo_trades ORDER BY id DESC", conn)
    conn.close()
    return df

def get_latest_kids_returns():
    conn = get_connection()
    df = pd.read_sql_query("SELECT hiro_return, caspar_return FROM hk_ipo_trades ORDER BY id DESC LIMIT 1", conn)
    conn.close()
    if not df.empty:
        h_ret = float(df['hiro_return'].iloc[0]) if pd.notnull(df['hiro_return'].iloc[0]) and df['hiro_return'].iloc[0] > 0 else 143.84
        c_ret = float(df['caspar_return'].iloc[0]) if pd.notnull(df['caspar_return'].iloc[0]) and df['caspar_return'].iloc[0] > 0 else 143.79
        return h_ret, c_ret
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
    conn.commit()
    conn.close()

def record_kids_cash_transaction(date_str, kid_name, action_type, amount, notes):
    """
    action_type: 'DEPOSIT' (入金), 'WITHDRAWAL' (微信提现), 'IPO_SETTLE' (打新结算)
    """
    init_kids_ledger_table()
    conn = get_connection()
    cursor = conn.cursor()
    
    df_curr = pd.read_sql_query(
        "SELECT balance_after FROM kids_cash_ledger WHERE kid_name = ? ORDER BY id DESC LIMIT 1",
        conn, params=(kid_name,)
    )
    if not df_curr.empty and pd.notnull(df_curr['balance_after'].iloc[0]):
        curr_bal = float(df_curr['balance_after'].iloc[0])
    else:
        h_latest, c_latest = get_latest_kids_returns()
        curr_bal = h_latest if kid_name == 'HIRO' else c_latest

    if action_type == 'WITHDRAWAL':
        net_change = -abs(amount)
    else:
        net_change = amount

    new_bal = curr_bal + net_change

    cursor.execute("""
    INSERT INTO kids_cash_ledger (date, kid_name, action_type, amount, balance_after, notes)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (date_str, kid_name, action_type, net_change, new_bal, notes))
    conn.commit()
    conn.close()
    return new_bal

def get_kids_cash_ledger():
    init_kids_ledger_table()
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM kids_cash_ledger ORDER BY id DESC", conn)
    conn.close()
    return df

def get_kids_account_summary(kid_name):
    """Compute total treasury balance, total IPO profit, total deposit, and total withdrawal for HIRO or CASPAR."""
    init_kids_ledger_table()
    conn = get_connection()
    
    df_bal = pd.read_sql_query(
        "SELECT balance_after FROM kids_cash_ledger WHERE kid_name = ? ORDER BY id DESC LIMIT 1",
        conn, params=(kid_name,)
    )
    if not df_bal.empty and pd.notnull(df_bal['balance_after'].iloc[0]):
        tot_bal = float(df_bal['balance_after'].iloc[0])
    else:
        h_ret, c_ret = get_latest_kids_returns()
        tot_bal = h_ret if kid_name == 'HIRO' else c_ret
        
    df_dep = pd.read_sql_query(
        "SELECT SUM(amount) as s FROM kids_cash_ledger WHERE kid_name = ? AND action_type = 'DEPOSIT'",
        conn, params=(kid_name,)
    )
    tot_dep = float(df_dep['s'].iloc[0]) if not df_dep.empty and pd.notnull(df_dep['s'].iloc[0]) else 0.0

    df_wd = pd.read_sql_query(
        "SELECT SUM(amount) as s FROM kids_cash_ledger WHERE kid_name = ? AND action_type = 'WITHDRAWAL'",
        conn, params=(kid_name,)
    )
    tot_wd = abs(float(df_wd['s'].iloc[0])) if not df_wd.empty and pd.notnull(df_wd['s'].iloc[0]) else 0.0

    col_prof = 'hiro_profit' if kid_name == 'HIRO' else 'caspar_profit'
    df_prof = pd.read_sql_query(f"SELECT SUM({col_prof}) as s FROM hk_ipo_trades", conn)
    tot_ipo_prof = float(df_prof['s'].iloc[0]) if not df_prof.empty and pd.notnull(df_prof['s'].iloc[0]) else 0.0

    conn.close()
    return {
        "balance": tot_bal,
        "ipo_profit": tot_ipo_prof,
        "total_deposit": tot_dep,
        "total_withdrawal": tot_wd
    }
