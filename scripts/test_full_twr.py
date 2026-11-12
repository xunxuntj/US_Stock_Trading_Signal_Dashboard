import json
import sqlite3
import pandas as pd
import numpy as np

def test_full_twr():
    # 1. Load full nav_history
    conn = sqlite3.connect("portfolio.db")
    df_nav = pd.read_sql_query("SELECT date, total_equity FROM nav_history WHERE total_equity IS NOT NULL AND total_equity > 0 ORDER BY date ASC", conn)
    conn.close()

    df_nav['date'] = pd.to_datetime(df_nav['date'])
    df_nav = df_nav.drop_duplicates(subset=['date'], keep='last').sort_values('date').reset_index(drop=True)
    print(f"Total NAV records: {len(df_nav)}, range: {df_nav['date'].iloc[0]} to {df_nav['date'].iloc[-1]}")

    # 2. Load cash flows from broker_funding and cash_transactions
    cash_flows = {}
    try:
        data = json.load(open("data/broker_audit_comparison.json"))
        for item in data.get("broker_funding", []):
            d = item.get("date", "")[:10]
            # only deposits / withdrawals (type '1' or containing DEPOSIT/WITHDRAW/TRANSFER)
            t = str(item.get("type", "")).upper()
            amt = float(item.get("amount", 0.0) or 0.0)
            curr = item.get("currency", "USD")
            rate = 1.0 if curr == "USD" else (0.75 if curr == "SGD" else (0.128 if curr == "HKD" else 1.0))
            amt_usd = amt * rate
            if t in ['1', 'DEPOSIT', 'FUNDS TRANSFER IN'] and amt_usd > 10.0:
                cash_flows[d] = cash_flows.get(d, 0.0) + amt_usd
            elif t in ['2', 'WITHDRAW', 'WITHDRAWAL', 'FUNDS TRANSFER OUT'] and amt_usd > 10.0:
                cash_flows[d] = cash_flows.get(d, 0.0) - amt_usd
    except Exception as e:
        print("Funding load error:", e)

    # Add from cash_transactions
    conn = sqlite3.connect("portfolio.db")
    cur = conn.cursor()
    cur.execute("SELECT date, type, amount FROM cash_transactions")
    for d, t, a in cur.fetchall():
        d_str = str(d)[:10]
        amt = float(a)
        flow = amt if "DEP" in t.upper() else -amt
        # avoid double counting if already present
        if d_str not in cash_flows:
            cash_flows[d_str] = cash_flows.get(d_str, 0.0) + flow
    conn.close()

    print(f"Total cash flow dates: {len(cash_flows)}")

    # 3. Unitization calculation
    start_equity = float(df_nav['total_equity'].iloc[0])
    units = start_equity
    unit_nav = 1.0
    unit_navs = [1.0]

    for i in range(1, len(df_nav)):
        d_str = df_nav['date'].iloc[i].strftime("%Y-%m-%d")
        eq = float(df_nav['total_equity'].iloc[i])
        cf = cash_flows.get(d_str, 0.0)

        pre_cf_eq = eq - cf
        if units > 0 and pre_cf_eq > 0:
            u_nav = pre_cf_eq / units
        else:
            u_nav = unit_nav

        if cf != 0 and u_nav > 0:
            units += cf / u_nav

        unit_nav = eq / units if units > 0 else 1.0
        unit_navs.append(unit_nav)

    df_nav['unit_nav'] = unit_navs
    print(f"Initial Unit NAV: {df_nav['unit_nav'].iloc[0]:.4f}")
    print(f"2026-01-15 Unit NAV: {df_nav[df_nav['date'] >= '2026-01-15']['unit_nav'].iloc[0]:.4f}")
    print(f"Latest Unit NAV: {df_nav['unit_nav'].iloc[-1]:.4f}")
    print(f"Full History Cumulative TWR: +{(df_nav['unit_nav'].iloc[-1] - 1.0) * 100:.2f}%")

if __name__ == "__main__":
    test_full_twr()
