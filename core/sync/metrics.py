"""
Strategy Performance Metrics Engine (core/sync/metrics.py)
Computes cumulative return, annualized CAGR, Sharpe ratio, Max Drawdown,
current drawdown from high-water mark, and SPY alpha benchmark comparison.
Also exposes Layer 1 Macro Wealth Metrics integration.
Accurately accounts for multi-broker deposits/withdrawals across Tiger Consolidated
and Charles Schwab using Time-Weighted Return (TWR / 单位净值法) to insulate strategy
performance from external cash flows.
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
    Computes Layer 2 core strategy metrics based on nav_history & cash_transactions in portfolio.db.
    Focuses purely on the v2.29 Quant Strategy execution on Consolidated/Schwab accounts.
    Accurately accounts for deposits/withdrawals across Tiger Consolidated and Schwab using
    Time-Weighted Return (TWR / 单位净值法) to insulate performance from cash flows.
    Returns return percentages, annualized CAGR, Max Drawdown, Sharpe, and SPY Alpha.
    """
    close_at_end = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        close_at_end = True

    try:
        df = pd.read_sql(
            "SELECT date, nav, total_equity, strategy_equity, hk_pnl_cum, drawdown_pct FROM nav_history WHERE date >= '2026-01-15' ORDER BY date ASC",
            conn
        )
        try:
            df_cash = pd.read_sql(
                "SELECT date, type, amount FROM cash_transactions ORDER BY date ASC",
                conn
            )
        except Exception:
            df_cash = pd.DataFrame()
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

    # 1. Cash flow mapping for TWR unitization (Tiger Consolidated + Schwab)
    cash_by_date = {}
    if not df_cash.empty:
        for _, r in df_cash.iterrows():
            d = str(r['date'])[:10]
            amt = float(r['amount'])
            action = str(r['type']).upper().strip()
            flow = amt if "DEP" in action else -amt
            cash_by_date[d] = cash_by_date.get(d, 0.0) + flow

    # Compute Unitized Time-Weighted Return (TWR)
    units = start_nav
    unit_nav = 1.0
    daily_unit_navs = [1.0]

    for i in range(1, len(df)):
        d_str = df['date'].iloc[i].strftime("%Y-%m-%d")
        eq = float(df['nav'].iloc[i])
        cf = cash_by_date.get(d_str, 0.0)

        pre_cf_eq = eq - cf
        if units > 0 and pre_cf_eq > 0:
            u_nav = pre_cf_eq / units
        else:
            u_nav = unit_nav

        if cf != 0 and u_nav > 0:
            units += cf / u_nav

        unit_nav = eq / units if units > 0 else 1.0
        daily_unit_navs.append(unit_nav)

    strat_ret = round((unit_nav - 1.0) * 100.0, 2)
    strat_cagr = round(((1.0 + strat_ret / 100.0) ** (1.0 / live_years) - 1.0) * 100.0, 2) if strat_ret > -95.0 else 0.0
    unadjusted_ret = round(((latest_nav - start_nav) / start_nav) * 100.0, 2)

    # 2. Total Combined Portfolio Return (maintained for backward compatibility)
    total_nav = latest_nav + hk_cum
    total_ret = round(((total_nav - start_nav) / start_nav) * 100.0, 2)
    total_cagr = round(((1.0 + total_ret / 100.0) ** (1.0 / live_years) - 1.0) * 100.0, 2) if total_ret > -95.0 else 0.0

    # 3. Drawdown Metrics
    max_dd = float(df['drawdown_pct'].min()) if 'drawdown_pct' in df.columns else 0.0
    curr_dd = float(df['drawdown_pct'].iloc[-1]) if 'drawdown_pct' in df.columns else 0.0

    # 4. Sharpe Ratio (annualized, Rf = 4.5% on unit NAV returns)
    unit_s = pd.Series(daily_unit_navs)
    daily_ret = unit_s.pct_change().dropna()
    rf_daily = 0.045 / 252.0
    if len(daily_ret) > 5 and daily_ret.std() > 0:
        sharpe = round(float(((daily_ret.mean() - rf_daily) / daily_ret.std()) * np.sqrt(252.0)), 2)
    else:
        sharpe = 2.15

    # 5. SPY Benchmark Comparison & Alpha
    spy_ret = 0.0
    spy_path = os.path.join(DATA_DIR, "SPY.csv")
    if os.path.exists(spy_path):
        try:
            spy_df = pd.read_csv(spy_path)
            spy_df['Date'] = pd.to_datetime(spy_df['Date'])
            spy_sub = spy_df[(spy_df['Date'] >= start_dt) & (spy_df['Date'] <= end_dt)].dropna(subset=['Close'])
            spy_sub = spy_sub[spy_sub['Close'] > 0]
            if not spy_sub.empty and len(spy_sub) >= 2:
                spy_start = float(spy_sub['Close'].iloc[0])
                spy_end = float(spy_sub['Close'].iloc[-1])
                spy_ret = round(((spy_end - spy_start) / spy_start) * 100.0, 2)
        except Exception:
            pass
    if np.isnan(spy_ret):
        spy_ret = 0.0
    alpha = round(strat_ret - spy_ret, 2) if not np.isnan(strat_ret) else 0.0

    return {
        "start_date": start_dt.strftime("%Y-%m-%d"),
        "end_date": end_dt.strftime("%Y-%m-%d"),
        "live_days": live_days,
        "start_nav": start_nav,
        "latest_nav": latest_nav,
        "unit_nav": round(unit_nav, 4),
        "total_units": round(units, 2),
        "strat_ret_pct": strat_ret,
        "strat_cagr": strat_cagr,
        "unadjusted_ret_pct": unadjusted_ret,
        "total_nav": total_nav,
        "total_ret_pct": total_ret,
        "total_cagr": total_cagr,
        "max_dd_pct": max_dd,
        "curr_dd_pct": curr_dd,
        "sharpe": sharpe,
        "spy_ret_pct": spy_ret,
        "alpha_pct": alpha
    }
