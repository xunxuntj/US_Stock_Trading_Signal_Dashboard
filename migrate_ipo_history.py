import sqlite3
import pandas as pd
import os, shutil

def migrate_ipo():
    db_path = 'portfolio.db'
    excel_path = 'IPOHistory_20260730.xlsx'
    
    # temp_ipo_migration.xlsx already copied via PowerShell
    temp_excel = 'temp_ipo_migration.xlsx'
    
    df = pd.read_excel(temp_excel, sheet_name='港美股打新记录')
    
    # Filter valid trade rows (non-null ticker name)
    df_valid = df[df['股票名称'].notnull()].copy()
    print(f"Found {len(df_valid)} valid IPO trade rows.")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create hk_ipo_trades table
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
    
    # Clear existing table data for clean re-import
    cursor.execute("DELETE FROM hk_ipo_trades")
    
    inserted = 0
    for _, r in df_valid.iterrows():
        ticker = str(r['股票名称']).strip()
        market = str(r['市场']).strip() if pd.notnull(r['市场']) else 'HK'
        margin_p = float(r['打新本金']) if pd.notnull(r['打新本金']) else 0.0
        alloc_s = float(r['配签数']) if pd.notnull(r['配签数']) else 0.0
        ipo_fee = float(r['打新费用']) if pd.notnull(r['打新费用']) else 0.0
        
        won_s = float(r['中签数']) if pd.notnull(r['中签数']) else 0.0
        won_p = float(r['中签价']) if pd.notnull(r['中签价']) else None
        sell_p = float(r['卖出价']) if pd.notnull(r['卖出价']) else None
        trade_fee = float(r['交易费用']) if pd.notnull(r['交易费用']) else 0.0
        total_fee = float(r['费用合计']) if pd.notnull(r['费用合计']) else 0.0
        
        profit = float(r['收益额']) if pd.notnull(r['收益额']) else 0.0
        roi = float(r['单次收益率']) if pd.notnull(r['单次收益率']) else 0.0
        mult = float(r['结算系数']) if pd.notnull(r['结算系数']) else 1.0
        
        hiro_cap = float(r['张恺霖\n投资本金']) if pd.notnull(r.get('张恺霖\n投资本金')) else 0.0
        hiro_prof = float(r['张恺霖\n投资收益']) if pd.notnull(r.get('张恺霖\n投资收益')) else 0.0
        hiro_ret = float(r['张恺霖\n投资返还']) if pd.notnull(r.get('张恺霖\n投资返还')) else 0.0
        
        caspar_cap = float(r['张忻霖\n投资本金']) if pd.notnull(r.get('张忻霖\n投资本金')) else 0.0
        caspar_prof = float(r['张忻霖\n投资收益']) if pd.notnull(r.get('张忻霖\n投资收益')) else 0.0
        caspar_ret = float(r['张忻霖\n投资返还']) if pd.notnull(r.get('张忻霖\n投资返还')) else 0.0
        
        ex_rate = float(r['汇率']) if pd.notnull(r['汇率']) else 1.0
        hkd_p = float(r['港币\n保证金折算']) if pd.notnull(r.get('港币\n保证金折算')) else margin_p
        hkd_fee = float(r['港币\n总费用支出']) if pd.notnull(r.get('港币\n总费用支出')) else total_fee
        hkd_profit = float(r['港币\n收益额折算']) if pd.notnull(r.get('港币\n收益额折算')) else profit
        
        # Start Date (X col)
        raw_start = r.get('Unnamed: 23')
        start_date = None
        if pd.notnull(raw_start):
            try:
                start_date = pd.to_datetime(raw_start).strftime('%Y-%m-%d')
            except Exception:
                start_date = str(raw_start)[:10]
                
        # Settle Date (Y col / Date)
        raw_settle = r.get('Date')
        settle_date = None
        if pd.notnull(raw_settle):
            try:
                settle_date = pd.to_datetime(raw_settle).strftime('%Y-%m-%d')
            except Exception:
                settle_date = str(raw_settle)[:10]
                
        cursor.execute("""
        INSERT INTO hk_ipo_trades (
            ticker_name, market, margin_principal, allocated_shares, ipo_fee,
            won_shares, won_price, sell_price, trade_fee, total_fee,
            profit_amt, roi, multiplier,
            hiro_capital, hiro_profit, hiro_return,
            caspar_capital, caspar_profit, caspar_return,
            exchange_rate, hkd_principal, hkd_total_fee, hkd_profit,
            start_date, settle_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ticker, market, margin_p, alloc_s, ipo_fee,
            won_s, won_p, sell_p, trade_fee, total_fee,
            profit, roi, mult,
            hiro_cap, hiro_prof, hiro_ret,
            caspar_cap, caspar_prof, caspar_ret,
            ex_rate, hkd_p, hkd_fee, hkd_profit,
            start_date, settle_date
        ))
        inserted += 1
        
    conn.commit()
    conn.close()
    
    if os.path.exists(temp_excel):
        os.remove(temp_excel)
        
    print(f"Successfully migrated {inserted} IPO trade records into hk_ipo_trades table!")

if __name__ == "__main__":
    migrate_ipo()
