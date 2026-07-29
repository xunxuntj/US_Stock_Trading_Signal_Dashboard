import sqlite3
import pandas as pd
import shutil, os

# ─── Step 1: Upgrade nav_history schema ───────────────────────────────────────
conn = sqlite3.connect('portfolio.db')
cursor = conn.cursor()

new_cols = [
    ("total_equity",    "REAL"),
    ("strategy_equity", "REAL"),
    ("hk_pnl_cum",      "REAL"),
    ("high_water_mark", "REAL"),
    ("drawdown_pct",    "REAL"),
    ("source",          "TEXT"),
]
for col, ctype in new_cols:
    try:
        cursor.execute(f"ALTER TABLE nav_history ADD COLUMN {col} {ctype}")
        print(f"  ✓ Added column: {col}")
    except Exception:
        print(f"  (skipped {col}, already exists)")

conn.commit()
conn.close()
print("Step 1 complete: schema upgraded.\n")

# ─── Step 2: Parse Daily_Equity from Excel ────────────────────────────────────
# temp_nav2.xlsx already copied by PowerShell

xl = pd.ExcelFile('temp_nav2.xlsx')
df_eq = xl.parse('Daily_Equity', header=2)
df_eq = df_eq.dropna(subset=['Date']).copy()
df_eq['Date'] = pd.to_datetime(df_eq['Date'])

col_total    = 'Total Brokerage Equity / 券商总净值 (手动输入)'
col_strategy = 'Strategy Equity / 策略净值 (自动计算)'
col_hwm      = 'High Water Mark'
col_dd       = 'Drawdown'
col_hk       = 'Accumulated HK PnL / 港股打新累计盈亏 (自动匹配)'

df_brokerage = df_eq[df_eq[col_total].notnull()].copy()
print(f"Step 2: Found {len(df_brokerage)} rows with real brokerage data from Excel.")
print(f"  Date range: {df_brokerage['Date'].min().date()} → {df_brokerage['Date'].max().date()}")

print()

# Cleanup
try:
    os.remove('temp_nav2.xlsx')
except Exception:
    pass


# ─── Step 3: Insert/replace nav_history rows ─────────────────────────────────
conn = sqlite3.connect('portfolio.db')
cursor = conn.cursor()

inserted = 0
for _, row in df_brokerage.iterrows():
    d_str   = row['Date'].strftime('%Y-%m-%d')
    total   = float(row[col_total])
    strat   = float(row[col_strategy]) if pd.notnull(row[col_strategy]) else total
    hwm     = float(row[col_hwm])      if pd.notnull(row[col_hwm])      else total
    dd      = float(row[col_dd])       if pd.notnull(row[col_dd])       else 0.0
    hk_cum  = float(row[col_hk])       if pd.notnull(row[col_hk])       else 0.0

    # nav column keeps strategy_equity for backward compat
    cursor.execute("""
        INSERT OR REPLACE INTO nav_history
            (date, nav, cash, jepq_val, sgov_val, trend_val,
             total_equity, strategy_equity, hk_pnl_cum, high_water_mark, drawdown_pct, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (d_str, strat, 0.0, 0.0, 0.0, 0.0,
          total, strat, hk_cum, hwm, dd * 100.0, 'BROKERAGE'))
    inserted += 1

# Step 4: Insert 2026-01-15 anchor point
cursor.execute("""
    INSERT OR REPLACE INTO nav_history
        (date, nav, cash, jepq_val, sgov_val, trend_val,
         total_equity, strategy_equity, hk_pnl_cum, high_water_mark, drawdown_pct, source)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", ('2026-01-15', 99215.41, 5830.88, 72800.0, 0.0, 37300.0,
      99215.41, 99215.41, 0.0, 99215.41, 0.0, 'INITIAL'))
conn.commit()
print(f"Step 3: Inserted {inserted} BROKERAGE rows + 1 INITIAL anchor (2026-01-15 $99,215.41).")

# ─── Step 5: Fill CALCULATED rows (2026-07-25 → today) ───────────────────────
from database import get_positions, get_connection, get_hk_ipo_history
from config import DATA_DIR
import datetime, numpy as np

df_hk = get_hk_ipo_history()
# Build a date → hk_pnl_cum lookup by month
hk_monthly = {}
for _, r in df_hk.iterrows():
    if pd.notnull(r['cum_profit']):
        hk_monthly[r['date'][:7]] = float(r['cum_profit'])  # 'YYYY-MM'

def get_hk_cum(date_str):
    ym = date_str[:7]
    # find most recent month <= ym
    candidates = [v for k, v in hk_monthly.items() if k <= ym]
    return max(candidates) if candidates else 0.0

# Load price CSVs
price_cache = {}
for ticker in ['JEPQ', 'SGOV', 'NVDA']:
    fpath = os.path.join(DATA_DIR, f'{ticker}.csv')
    if os.path.exists(fpath):
        df_p = pd.read_csv(fpath)
        df_p['Date'] = pd.to_datetime(df_p['Date'])
        price_cache[ticker] = df_p.set_index('Date')['Close']

pos_df = get_positions()
holdings = {row['ticker']: float(row['shares']) for _, row in pos_df.iterrows()}

# Which dates need CALCULATED fill?
last_brokerage = df_brokerage['Date'].max()
today = pd.Timestamp.today().normalize()
fill_dates = pd.bdate_range(last_brokerage + pd.Timedelta(days=1), today)

hwm_running = float(df_brokerage[col_hwm].iloc[-1])
calc_inserted = 0

for d in fill_dates:
    d_str = d.strftime('%Y-%m-%d')
    hk_cum = get_hk_cum(d_str)

    val = 0.0
    for ticker, shares in holdings.items():
        if ticker in price_cache:
            series = price_cache[ticker]
            # find latest available price on or before this date
            avail = series[series.index <= d]
            if not avail.empty:
                val += shares * float(avail.iloc[-1])
            else:
                val += shares * float(series.iloc[0])

    # Add cash remainder + HK profits
    cash = 1617.84
    total = val + cash + hk_cum
    strat = total - hk_cum
    hwm_running = max(hwm_running, total)
    dd = (total - hwm_running) / hwm_running * 100.0 if hwm_running > 0 else 0.0

    cursor.execute("""
        INSERT OR REPLACE INTO nav_history
            (date, nav, cash, jepq_val, sgov_val, trend_val,
             total_equity, strategy_equity, hk_pnl_cum, high_water_mark, drawdown_pct, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (d_str, strat, cash, 0.0, 0.0, 0.0,
          total, strat, hk_cum, hwm_running, dd, 'CALCULATED'))
    calc_inserted += 1

conn.commit()
conn.close()

print(f"Step 5: Inserted {calc_inserted} CALCULATED rows ({last_brokerage.date()} → {today.date()}).")
print("\n=== DONE ===")
print("Run 'git add portfolio.db && git commit && git push' to sync.")
