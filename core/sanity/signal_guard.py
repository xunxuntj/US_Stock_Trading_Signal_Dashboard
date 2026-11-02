"""
Technical Signal Guard (core/sanity/signal_guard.py)
Provides exhaustive position exit scanning, canonical layer normalization,
and signal idempotency (deduplication) to eliminate exit signal blind spots
(such as the historic SOXX bug) and prevent false/duplicate alerts.
"""

import os
import hashlib
import sqlite3
import datetime
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
from config import (
    EQUITY_L1_TICKERS, EQUITY_L2_WHITELIST, NON_EQUITY_TICKERS,
    BASE_TICKERS, DB_PATH
)

# Canonical Layer Mapping based on Strategy Execution Card
CANONICAL_LAYER_MAP = {
    "JEPQ": "L0",
    "SGOV": "SGOV",
    "SPY": "L1",
    "QQQ": "L1",
    "SOXX": "L1",
    "QLD": "L2",
    "GLD": "Non-Equity",
    "TLT": "Non-Equity",
    "DBC": "Non-Equity",
    "BITO": "Non-Equity",
}

# L2 Parent Map
L2_PARENT_MAP = {
    "QLD": "QQQ",
    "SOXX": "QQQ", # If traded as L2 child
}

EXEMPT_EXIT_LAYERS = ["L0", "L0+", "SGOV", "LEGACY", "CASH"]


def get_canonical_layer(ticker: str, recorded_layer: Optional[str] = None) -> str:
    """
    Resolve the true canonical layer for any ticker.
    Prevents blind spots caused by manually mis-tagged layers (e.g. 'TREND' vs 'L1').
    """
    t_upper = ticker.upper().strip()
    if t_upper in CANONICAL_LAYER_MAP:
        return CANONICAL_LAYER_MAP[t_upper]
    if recorded_layer:
        return recorded_layer
    return "TREND"


def init_signal_cache_table(conn: Optional[sqlite3.Connection] = None):
    """Ensure sent_signals_cache table exists in SQLite database."""
    close_at_end = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        close_at_end = True

    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sent_signals_cache (
        fingerprint TEXT PRIMARY KEY,
        date TEXT NOT NULL,
        ticker TEXT NOT NULL,
        action TEXT NOT NULL,
        target_val REAL,
        sent_at TEXT NOT NULL
    )
    """)
    conn.commit()
    if close_at_end:
        conn.close()


def is_signal_already_sent(date_str: str, ticker: str, action: str, conn: Optional[sqlite3.Connection] = None) -> bool:
    """Check if this signal was already dispatched today."""
    init_signal_cache_table(conn)
    close_at_end = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        close_at_end = True

    fingerprint = hashlib.sha256(f"{date_str}_{ticker.upper()}_{action.upper()}".encode()).hexdigest()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM sent_signals_cache WHERE fingerprint = ?", (fingerprint,))
    row = cursor.fetchone()
    if close_at_end:
        conn.close()
    return row is not None


def mark_signal_sent(date_str: str, ticker: str, action: str, target_val: float, conn: Optional[sqlite3.Connection] = None):
    """Record that a signal has been successfully dispatched."""
    init_signal_cache_table(conn)
    close_at_end = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        close_at_end = True

    fingerprint = hashlib.sha256(f"{date_str}_{ticker.upper()}_{action.upper()}".encode()).hexdigest()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO sent_signals_cache (fingerprint, date, ticker, action, target_val, sent_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (fingerprint, date_str, ticker.upper(), action.upper(), float(target_val), now_str))
    conn.commit()
    if close_at_end:
        conn.close()


def exhaustive_scan_trend_exits(
    positions_df: pd.DataFrame,
    data_dict: Dict[str, pd.DataFrame],
    latest_date: Any,
    date_str: str
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Exhaustively scans EVERY active position for exit conditions.
    Guarantees zero blind spot:
    1. Normalizes layer so mis-tagged 'TREND' or 'L1' behaves correctly.
    2. Verifies both self ST_trend and L2 parent ST_trend.
    3. Returns list of exit actions and technical sanity warnings.
    """
    actions = []
    warnings = []

    if positions_df.empty:
        return actions, warnings

    for _, pos in positions_df.iterrows():
        ticker = str(pos['ticker']).upper().strip()
        shares = float(pos.get('shares', 0.0))
        if shares <= 0.0001:
            continue

        raw_layer = str(pos.get('layer', '')).strip()
        canonical_layer = get_canonical_layer(ticker, raw_layer)

        # Bottom assets (L0, SGOV, LEGACY) are exempt from trend exits
        if canonical_layer in EXEMPT_EXIT_LAYERS or ticker in ["JEPQ", "SGOV", "NVDA"]:
            continue

        if ticker not in data_dict:
            warnings.append(f"Position {ticker} ({shares} shares) exists in DB but market data is missing!")
            continue

        df_t = data_dict[ticker]
        if latest_date not in df_t.index:
            warnings.append(f"Position {ticker} missing bar for latest date {latest_date}")
            continue

        st_trend = df_t.loc[latest_date, 'ST_trend']
        current_price = float(df_t.loc[latest_date, 'Close'])

        # L2 logic: check self or parent QQQ
        if canonical_layer == "L2" or ticker in ["QLD"]:
            parent_ticker = L2_PARENT_MAP.get(ticker, "QQQ")
            parent_st = None
            if parent_ticker in data_dict and latest_date in data_dict[parent_ticker].index:
                parent_st = data_dict[parent_ticker].loc[latest_date, 'ST_trend']
            else:
                warnings.append(f"Parent ticker {parent_ticker} data missing for L2 exit check on {ticker}")

            if st_trend == -1:
                actions.append({
                    "date": date_str,
                    "ticker": ticker,
                    "action": "SELL",
                    "target_val": round(shares * current_price, 2),
                    "shares": shares,
                    "price": current_price,
                    "reason": f"Exit L2 ({ticker}): SuperTrend turned Bearish (-1)",
                    "layer": canonical_layer
                })
            elif parent_st == -1:
                actions.append({
                    "date": date_str,
                    "ticker": ticker,
                    "action": "SELL",
                    "target_val": round(shares * current_price, 2),
                    "shares": shares,
                    "price": current_price,
                    "reason": f"Exit L2 ({ticker}): Parent {parent_ticker} SuperTrend turned Bearish (-1)",
                    "layer": canonical_layer
                })
        else:
            # L1 or Non-Equity trend
            if st_trend == -1:
                actions.append({
                    "date": date_str,
                    "ticker": ticker,
                    "action": "SELL",
                    "target_val": round(shares * current_price, 2),
                    "shares": shares,
                    "price": current_price,
                    "reason": f"Exit {canonical_layer} ({ticker}): SuperTrend turned Bearish (-1)",
                    "layer": canonical_layer
                })

    return actions, warnings
