import os
import pandas as pd
import numpy as np
import datetime
import backtest_engine as be
from config import (
    DATA_DIR, EQUITY_L1_TICKERS, EQUITY_L2_WHITELIST, NON_EQUITY_TICKERS,
    S5FI_L1_THRESHOLD, S5FI_L2_THRESHOLD, MAX_TREND_CAPACITY_PCT,
    SINGLE_POSITION_CAP_PCT, L2_POSITION_CAP_PCT
)
from database import get_positions, get_connection

def generate_v229_signals():
    """ Runs daily scan on latest market data to check for v2.29 Buy/Sell signals """
    data = be.prepare_data(DATA_DIR)
    spy_df = data["SPY"]
    latest_date = spy_df.index[-1]
    prev_date = spy_df.index[-2] if len(spy_df) >= 2 else latest_date
    
    date_str = latest_date.strftime("%Y-%m-%d")
    
    current_prices = {t: data[t].loc[latest_date, 'Close'] for t in data if latest_date in data[t].index}
    s5fi_val = float(data["S5FI"].loc[latest_date, "Close"]) if "S5FI" in data and latest_date in data["S5FI"].index else 50.0
    
    positions_df = get_positions()
    current_positions = {row['ticker']: row for _, row in positions_df.iterrows()} if not positions_df.empty else {}
    
    actions = []
    
    # 1. Exit Checks for Active Trend Positions
    for ticker, pos in current_positions.items():
        layer = pos['layer']
        if layer in ['L0', 'SGOV']:
            continue
        if ticker not in data or latest_date not in data[ticker].index:
            continue
            
        df_t = data[ticker]
        st_trend = df_t.loc[latest_date, 'ST_trend']
        
        if layer == 'L2':
            # Check L2 self or parent ST_trend
            parent_ticker = "QQQ" if ticker in ["SOXX", "QLD"] else "SPY"
            parent_st = data[parent_ticker].loc[latest_date, 'ST_trend'] if parent_ticker in data and latest_date in data[parent_ticker].index else -1
            if st_trend == -1 or parent_st == -1:
                actions.append({
                    "date": date_str, "ticker": ticker, "action": "SELL",
                    "target_val": pos['shares'] * current_prices[ticker],
                    "reason": f"Exit L2 ({ticker}): SuperTrend turned Bearish (-1)",
                    "layer": layer
                })
        elif layer in ['L1', 'Non-Equity']:
            if st_trend == -1:
                actions.append({
                    "date": date_str, "ticker": ticker, "action": "SELL",
                    "target_val": pos['shares'] * current_prices[ticker],
                    "reason": f"Exit {layer} ({ticker}): SuperTrend turned Bearish (-1)",
                    "layer": layer
                })
                
    # Calculate Current NAV & Active Trend Capacity
    trend_val = sum(pos['shares'] * current_prices[pos['ticker']] for t, pos in current_positions.items() if pos['layer'] not in ['L0', 'SGOV'] and pos['ticker'] in current_prices)
    jepq_val = current_positions['JEPQ']['shares'] * current_prices['JEPQ'] if 'JEPQ' in current_positions else 0.0
    sgov_val = current_positions['SGOV']['shares'] * current_prices['SGOV'] if 'SGOV' in current_positions else 0.0
    nav = trend_val + jepq_val + sgov_val
    if nav <= 0:
        nav = 100000.0
        
    # 2. Entry Checks
    # Equity L1
    for t in EQUITY_L1_TICKERS:
        if t in current_positions or any(a['ticker'] == t for a in actions):
            continue
        df_t = data[t]
        if latest_date not in df_t.index or prev_date not in df_t.index:
            continue
        row = df_t.loc[latest_date]
        prev_trend = df_t.loc[prev_date, 'ST_trend']
        
        if row['Close'] > row['EMA200'] and row['ST_trend'] == 1 and prev_trend == -1:
            if s5fi_val >= S5FI_L1_THRESHOLD:
                target_val = nav * SINGLE_POSITION_CAP_PCT
                if trend_val + target_val <= nav * MAX_TREND_CAPACITY_PCT:
                    actions.append({
                        "date": date_str, "ticker": t, "action": "BUY",
                        "target_val": target_val,
                        "reason": f"L1 Entry ({t}): Price > EMA200, ST flipped Bullish (+1), S5FI ({s5fi_val:.1f}%) >= 45%",
                        "layer": "L1"
                    })
                    
    # Equity L2
    for l1_t in EQUITY_L1_TICKERS:
        if l1_t not in current_positions or current_positions[l1_t]['layer'] != 'L1':
            continue
        if data[l1_t].loc[latest_date, 'ST_trend'] != 1:
            continue
        for l2_t in EQUITY_L2_WHITELIST[l1_t]:
            if l2_t in current_positions or any(a['ticker'] == l2_t for a in actions):
                continue
            if latest_date not in data[l2_t].index:
                continue
            if data[l2_t].loc[latest_date, 'ST_trend'] == 1 and s5fi_val >= S5FI_L2_THRESHOLD:
                target_val = nav * L2_POSITION_CAP_PCT
                if trend_val + target_val <= nav * MAX_TREND_CAPACITY_PCT:
                    actions.append({
                        "date": date_str, "ticker": l2_t, "action": "BUY",
                        "target_val": target_val,
                        "reason": f"L2 Entry ({l2_t}): Parent L1 ({l1_t}) Bullish, ST Bullish (+1), S5FI ({s5fi_val:.1f}%) >= 55%",
                        "layer": "L2"
                    })
                    
    # Non-Equity L1
    for t in NON_EQUITY_TICKERS:
        if t not in data or t in current_positions or any(a['ticker'] == t for a in actions):
            continue
        df_t = data[t]
        if latest_date not in df_t.index or prev_date not in df_t.index:
            continue
        row = df_t.loc[latest_date]
        prev_trend = df_t.loc[prev_date, 'ST_trend']
        
        if row['Close'] > row['EMA200'] and row['ST_trend'] == 1 and prev_trend == -1:
            target_val = nav * SINGLE_POSITION_CAP_PCT
            if trend_val + target_val <= nav * MAX_TREND_CAPACITY_PCT:
                actions.append({
                    "date": date_str, "ticker": t, "action": "BUY",
                    "target_val": target_val,
                    "reason": f"Non-Equity Entry ({t}): Price > EMA200, ST flipped Bullish (+1) (S5FI Exempt)",
                    "layer": "Non-Equity"
                })

    return date_str, nav, s5fi_val, actions
