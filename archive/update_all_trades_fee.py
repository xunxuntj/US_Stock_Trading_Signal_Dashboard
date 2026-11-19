import pandas as pd
import sqlite3
import os

# 1. Read Transactions sheet starting from row 1
xl = pd.ExcelFile('temp_excel.xlsx')
df = xl.parse('Transactions', skiprows=1)

print("Parsed Transactions shape:", df.shape)
print("Columns:", df.columns.tolist())

# Connect to database
conn = sqlite3.connect('portfolio.db')
cursor = conn.cursor()

updated_count = 0
for idx, row in df.iterrows():
    if pd.isnull(row['Date']) or pd.isnull(row['Ticker']):
        continue
    
    trade_id = idx + 1 # Trade ID 1-indexed
    fee_val = float(row['Fee']) if pd.notnull(row['Fee']) else 0.0
    
    cursor.execute("UPDATE trades SET fee = ? WHERE id = ?", (fee_val, trade_id))
    updated_count += 1

conn.commit()
print(f"✓ Successfully updated explicit fee for {updated_count} historical trades in portfolio.db!")

print("\n=== SAMPLE TRADES WITH EXPLICIT FEE FROM EXCEL ===")
df_trades = pd.read_sql_query("SELECT id, date, ticker, action, shares, price, total_val, fee, pnl, reason FROM trades ORDER BY id ASC LIMIT 20", conn)
print(df_trades.to_string())

conn.close()
os.remove('temp_excel.xlsx')
