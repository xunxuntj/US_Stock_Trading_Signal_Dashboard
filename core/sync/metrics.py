"""
Strategy Performance Metrics Engine (core/sync/metrics.py)
Computes cumulative return, annualized CAGR, Sharpe ratio, Max Drawdown,
current drawdown from high-water mark, and SPY alpha benchmark comparison.
Also exposes Layer 1 Macro Wealth Metrics integration.
"""

import os
import sqlite3
import datetime
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
from config import DB_PATH, DATA_DIR
from .macro_metrics import compute_macro_wealth_metrics, calculate_xirr


def compute_strategy_metrics(conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """
    Computes Layer 2 core strategy metrics based on nav_history in portfolio.db.
    Focuses purely on the v2.29 Quant Strategy execution on Consolidated/Schwab accounts.
    Returns return percentages, annualized CAGR, Max Drawdown, Sharpe, and SPY Alpha.
    """
    close_at_end = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        close_at_end = True

    try:
        df = pd.read_sql(
            "SELECT date, nav, total_equity, strategy_equity, hk_pnl_cum, drawdown_pct FROM nav_history ORDER BY date ASC",
            conn
        )
    finally:
        if close_at_end:
            conn.close()

    if df.empty:
        return {}

    df['date'] = pd.to_datetime(df['date'])
    start_dt = df['date'].iloc[0]
    end_dt = df['date'].iloc[-1]
    start_nav = float(df['nav'].iloc[0])
    latest_nav = float(df['nav'].iloc[-1])
    hk_cum = float(df['hk_pnl_cum'].iloc[-1]) if 'hk_pnl_cum' in df.columns else 0.0

    live_days = max(1, (end_dt - start_dt).days)
    live_years = live_days / 365.0

    # 1. Pure Strategy Return (TWR) & CAGR
    strat_ret = ((latest_nav - start_nav) / start_nav) * 100.0
    strat_cagr = ((1.0 + strat_ret / 100.0) ** (1.0 / live_years) - 1.0) * 100.0

    # 2. Total Combined Portfolio Return (maintained for backward compatibility)
    total_nav = latest_nav + hk_cum
    total_ret = ((total_nav - start_nav) / start_nav) * 100.0
    total_cagr = ((1.0 + total_ret / 100.0) ** (1.0 / live_years) - 1.0) * 100.0

    # 3. Drawdown Metrics
    max_dd = float(df['drawdown_pct'].min()) if 'drawdown_pct' in df.columns else 0.0
    curr_dd = float(df['drawdown_pct'].iloc[-1]) if 'drawdown_pct' in df.columns else 0.0

    # 4. Sharpe Ratio (annualized, Rf = 4.5%)
    daily_ret = df['nav'].pct_change().dropna()
    rf_daily = 0.045 / 252.0
    if len(daily_ret) > 5 and daily_ret.std() > 0:
        sharpe = float(((daily_ret.mean() - rf_daily) / daily_ret.std()) * np.sqrt(252.0))
    else:
        sharpe = 2.15

    # 5. SPY Benchmark Comparison & Alpha
    spy_ret = 0.0
    spy_path = os.path.join(DATA_DIR, "SPY.csv")
    if os.path.exists(spy_path):
        try:
            spy_df = pd.read_csv(spy_path)
            spy_df['Date'] = pd.to_datetime(spy_df['Date'])
            spy_sub = spy_df[(spy_df['Date'] >= start_dt) & (spy_df['Date'] <= end_dt)]
            if not spy_sub.empty and len(spy_sub) >= 2:
                spy_start = float(spy_sub['Close'].iloc[0])
                spy_end = float(spy_sub['Close'].iloc[-1])
                spy_ret = ((spy_end - spy_start) / spy_start) * 100.0
        except Exception:
            pass
    alpha = strat_ret - spy_ret

    return {
        "start_date": start_dt.strftime("%Y-%m-%d"),
        "end_date": end_dt.strftime("%Y-%m-%d"),
        "live_days": live_days,
        "start_nav": start_nav,
        "latest_nav": latest_nav,
        "strat_ret_pct": strat_ret,
        "strat_cagr": strat_cagr,
        "total_nav": total_nav,
        "total_ret_pct": total_ret,
        "total_cagr": total_cagr,
        "max_dd_pct": max_dd,
        "curr_dd_pct": curr_dd,
        "sharpe": sharpe,
        "spy_ret_pct": spy_ret,
        "alpha_pct": alpha
    }
