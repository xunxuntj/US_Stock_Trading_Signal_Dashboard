import os
import sys
import datetime
import pandas as pd

from database import (
    init_db, get_positions, update_position, record_trade,
    record_nav, record_brokerage_nav, get_hk_ipo_history
)
from signal_engine import generate_v229_signals
from notifier import format_telegram_card, send_notification
from config import INITIAL_CAPITAL, JEPQ_TARGET_PCT, SGOV_TARGET_PCT, DATA_DIR


def compute_hk_pnl_cum(date_str):
    """Return latest HK IPO cumulative profit as of date_str."""
    df_hk = get_hk_ipo_history()
    if df_hk.empty:
        return 0.0
    ym = date_str[:7]
    # Filter records with month <= date_str's month, sorted by date ascending
    valid = df_hk[df_hk['date'].str[:7] <= ym].sort_values('date', ascending=True)
    if not valid.empty and pd.notnull(valid.iloc[-1]['cum_profit']):
        return float(valid.iloc[-1]['cum_profit'])
    return 0.0


def load_latest_price(ticker):
    """Load most recent closing price from downloaded CSV."""
    fpath = os.path.join(DATA_DIR, f'{ticker}.csv')
    if not os.path.exists(fpath):
        return None
    df = pd.read_csv(fpath)
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values('Date')
    return float(df['Close'].iloc[-1]) if not df.empty else None


def main():
    init_db()

    # Auto-fetch live real-time market closes from Yahoo Finance
    print("Fetching live real-time market closes...")
    try:
        import download_data
        download_data.main()
    except Exception as e:
        print(f"Warning: Live data download skipped: {e}")

    # Check if positions exist, if empty initialize portfolio
    pos_df = get_positions()
    if pos_df.empty:
        print("Initializing new $100,000 portfolio (JEPQ 60% / SGOV 40%)...")
        update_position("JEPQ", 60000.0 / 50.0, 60000.0, "L0")
        update_position("SGOV", 40000.0 / 100.0, 40000.0, "SGOV")

    date_str, nav, s5fi_val, actions = generate_v229_signals()
    card_text = format_telegram_card(date_str, nav, s5fi_val, actions)
    send_notification(card_text)

    # ── Auto-record real NAV from positions × live prices ──────────────────────
    try:
        pos_df = get_positions()
        holdings = {row['ticker']: float(row['shares']) for _, row in pos_df.iterrows()}

        total_mkt_val = 0.0
        for ticker, shares in holdings.items():
            price = load_latest_price(ticker)
            if price:
                total_mkt_val += shares * price

        cash = 1617.84  # Updated when cash transactions change
        hk_cum = compute_hk_pnl_cum(date_str)
        total_equity = total_mkt_val + cash + hk_cum
        strategy_equity = total_equity - hk_cum

        # Running HWM: pull from latest nav_history
        import sqlite3
        from config import DATA_DIR as _
        conn = sqlite3.connect('portfolio.db')
        cursor = conn.cursor()
        cursor.execute("SELECT high_water_mark FROM nav_history WHERE high_water_mark IS NOT NULL ORDER BY date DESC LIMIT 1")
        row_hwm = cursor.fetchone()
        conn.close()
        hwm = float(row_hwm[0]) if row_hwm else total_equity
        hwm = max(hwm, total_equity)
        dd_pct = (total_equity - hwm) / hwm * 100.0 if hwm > 0 else 0.0

        jepq_price = load_latest_price('JEPQ') or 0
        sgov_price  = load_latest_price('SGOV') or 0
        jepq_val = holdings.get('JEPQ', 0) * jepq_price
        sgov_val  = holdings.get('SGOV', 0) * sgov_price

        record_nav(
            date_str, strategy_equity, cash, jepq_val, sgov_val, 0.0,
            total_equity=total_equity,
            strategy_equity=strategy_equity,
            hk_pnl_cum=hk_cum,
            high_water_mark=hwm,
            drawdown_pct=dd_pct,
            source='CALCULATED'
        )
        print(f"NAV recorded: {date_str} | Total=${total_equity:,.2f} | Strategy=${strategy_equity:,.2f} | Source=CALCULATED")
    except Exception as e:
        print(f"Warning: NAV auto-record failed: {e}")

    print(f"Scan complete for {date_str}. Database synchronized.")


if __name__ == "__main__":
    main()
