import os
import sys
import datetime
import pandas as pd

from database import init_db, get_positions, update_position, record_trade, record_nav
from signal_engine import generate_v229_signals
from notifier import format_telegram_card, send_notification
from config import INITIAL_CAPITAL, JEPQ_TARGET_PCT, SGOV_TARGET_PCT
import download_data

def main():
    init_db()
    
    # Auto-fetch live real-time market closes from Yahoo Finance
    print("Fetching live real-time market closes...")
    try:
        download_data.main()
    except Exception as e:
        print(f"Warning: Live data download skipped: {e}")
    
    # Check if positions exist, if empty initialize $100k starting portfolio
    pos_df = get_positions()
    if pos_df.empty:
        print("Initializing new $100,000 portfolio (JEPQ 60% / SGOV 40%)...")
        update_position("JEPQ", 60000.0 / 50.0, 60000.0, "L0") # approx init
        update_position("SGOV", 40000.0 / 100.0, 40000.0, "SGOV")
        record_nav(datetime.datetime.now().strftime("%Y-%m-%d"), INITIAL_CAPITAL, 0.0, 60000.0, 40000.0, 0.0)

    date_str, nav, s5fi_val, actions = generate_v229_signals()
    card_text = format_telegram_card(date_str, nav, s5fi_val, actions)
    send_notification(card_text)
    
    print(f"Scan complete for {date_str}. Database synchronized.")

if __name__ == "__main__":
    main()
