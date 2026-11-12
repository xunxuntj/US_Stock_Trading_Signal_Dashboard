import os
import sys
import sqlite3
import httpx
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from database import get_supabase_credentials

def sync_2026_nav_to_supabase():
    url, key = get_supabase_credentials()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates"
    }
    conn = sqlite3.connect("portfolio.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM nav_history WHERE date >= '2026-01-01' ORDER BY date ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    print(f"Total 2026 NAV rows to sync: {len(rows)}")
    batch_size = 25
    success_count = 0
    with httpx.Client(timeout=30.0) as client:
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i+batch_size]
            cleaned_batch = []
            for item in batch:
                c_item = {k: v for k, v in item.items() if v is not None}
                cleaned_batch.append(c_item)
            
            for retry in range(3):
                try:
                    resp = client.post(f"{url}/rest/v1/nav_history?on_conflict=date", json=cleaned_batch, headers=headers)
                    if resp.status_code in [200, 201, 204]:
                        success_count += len(batch)
                        print(f"✅ Synced batch {i}..{i+len(batch)-1} ({batch[0]['date']} to {batch[-1]['date']})")
                        break
                    else:
                        print(f"⚠️ Batch {i} failed: {resp.status_code} {resp.text}")
                except Exception as e:
                    print(f"⚠️ Exception on batch {i} (attempt {retry+1}): {e}")
                    time.sleep(2)
            time.sleep(0.5)

    print(f"\n🎉 Successfully synced {success_count}/{len(rows)} records to Supabase!")

if __name__ == "__main__":
    sync_2026_nav_to_supabase()
