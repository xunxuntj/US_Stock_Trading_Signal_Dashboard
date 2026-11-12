import os
import sys
import time
import sqlite3
import httpx
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import DB_PATH
from database import get_supabase_credentials


def fix_2026_nav_and_drawdown():
    bak_path = "portfolio.db.bak_20261112_151845"
    if not os.path.exists(bak_path):
        print(f"❌ Backup {bak_path} not found!")
        return

    # 1. Read clean 2026-01-15 to 2026-09-21 from backup
    c_bak = sqlite3.connect(bak_path)
    c_bak.row_factory = sqlite3.Row
    df_early = pd.read_sql_query(
        "SELECT * FROM nav_history WHERE date >= '2026-01-15' AND date <= '2026-09-21' ORDER BY date ASC",
        c_bak
    )
    c_bak.close()

    # 2. Read calibrated 2026-09-22 onwards from current production db
    c_cur = sqlite3.connect(DB_PATH)
    df_late = pd.read_sql_query(
        "SELECT * FROM nav_history WHERE date >= '2026-09-22' ORDER BY date ASC",
        c_cur
    )

    df_2026 = pd.concat([df_early, df_late]).drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)

    # 3. Recalculate HWM & Drawdown strictly from 2026-01-15
    hwm = float(df_2026["total_equity"].iloc[0])
    for idx, row in df_2026.iterrows():
        eq = float(row["total_equity"])
        if eq > hwm:
            hwm = eq
        dd = (eq - hwm) / hwm * 100.0 if hwm > 0 else 0.0
        df_2026.at[idx, "high_water_mark"] = round(hwm, 2)
        df_2026.at[idx, "drawdown_pct"] = round(dd, 4)

    print(f"📊 Recalibrated 2026 rows: {len(df_2026)}")
    print(f"📌 Start: {df_2026['date'].iloc[0]} (${df_2026['total_equity'].iloc[0]:,.2f})")
    print(f"📌 End:   {df_2026['date'].iloc[-1]} (${df_2026['total_equity'].iloc[-1]:,.2f})")
    print(f"📉 2026 Max Drawdown: {df_2026['drawdown_pct'].min():.2f}% on {df_2026.loc[df_2026['drawdown_pct'].idxmin(), 'date']}")

    # 4. Write back to portfolio.db
    cur = c_cur.cursor()
    for _, r in df_2026.iterrows():
        cur.execute("""
            INSERT OR REPLACE INTO nav_history
            (date, nav, cash, jepq_val, sgov_val, trend_val, total_equity, strategy_equity, hk_pnl_cum, high_water_mark, drawdown_pct, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(r["date"])[:10],
            float(r["nav"]) if pd.notnull(r["nav"]) else float(r["strategy_equity"]),
            float(r["cash"]) if pd.notnull(r["cash"]) else 0.0,
            float(r["jepq_val"]) if pd.notnull(r["jepq_val"]) else 0.0,
            float(r["sgov_val"]) if pd.notnull(r["sgov_val"]) else 0.0,
            float(r["trend_val"]) if pd.notnull(r["trend_val"]) else 0.0,
            float(r["total_equity"]),
            float(r["strategy_equity"]) if pd.notnull(r["strategy_equity"]) else float(r["total_equity"]),
            float(r["hk_pnl_cum"]) if pd.notnull(r["hk_pnl_cum"]) else 0.0,
            float(r["high_water_mark"]),
            float(r["drawdown_pct"]),
            str(r["source"])
        ))
    c_cur.commit()
    c_cur.close()
    print("✅ Updated portfolio.db successfully.")

    # 5. Sync 2026 rows to Supabase Cloud
    url, key = get_supabase_credentials()
    if url and key:
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates"
        }
        rows_list = df_2026.to_dict(orient="records")
        batch_size = 30
        synced = 0
        with httpx.Client(timeout=30.0) as client:
            for i in range(0, len(rows_list), batch_size):
                batch = []
                for item in rows_list[i:i+batch_size]:
                    clean_item = {}
                    for k, v in item.items():
                        if pd.notnull(v):
                            clean_item[k] = str(v)[:10] if k == "date" else v
                    batch.append(clean_item)
                for retry in range(3):
                    try:
                        resp = client.post(f"{url}/rest/v1/nav_history?on_conflict=date", json=batch, headers=headers)
                        if resp.status_code in [200, 201, 204]:
                            synced += len(batch)
                            break
                        else:
                            print(f"⚠️ Supabase batch {i} error: {resp.status_code} {resp.text}")
                    except Exception as e:
                        print(f"⚠️ Supabase retry {retry+1} exception: {e}")
                        time.sleep(2)
                time.sleep(0.3)
        print(f"☁️ Synced {synced}/{len(rows_list)} recalibrated 2026 rows to Supabase.")


if __name__ == "__main__":
    fix_2026_nav_and_drawdown()
