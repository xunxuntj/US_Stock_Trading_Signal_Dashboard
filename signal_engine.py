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

def ensure_latest_market_data():
    """ Automatically check if local data CSVs are stale and fetch latest daily bars silently """
    try:
        import datetime, os, pandas as pd, yfinance as yf
        from config import DATA_DIR, BASE_TICKERS
        today = datetime.date.today()
        spy_path = os.path.join(DATA_DIR, "SPY.csv")
        if os.path.exists(spy_path):
            df_spy = pd.read_csv(spy_path)
            if not df_spy.empty and 'Date' in df_spy.columns:
                last_date = pd.to_datetime(df_spy['Date'].iloc[-1]).date()
                # If local data is more than 1 day old on a weekday, fetch fresh bars
                if (today - last_date).days >= 1:
                    for t in list(set(BASE_TICKERS + ["JEPQ", "SGOV"])):
                        try:
                            tk = yf.Ticker(t)
                            df_new = tk.history(period="5d")
                            if not df_new.empty:
                                csv_file = os.path.join(DATA_DIR, f"{t}.csv")
                                if os.path.exists(csv_file):
                                    df_old = pd.read_csv(csv_file)
                                    if 'Date' in df_old.columns:
                                        df_old['Date'] = pd.to_datetime(df_old['Date'])
                                        df_old = df_old.set_index('Date')
                                    df_new.index = pd.to_datetime(df_new.index).tz_localize(None)
                                    df_comb = pd.concat([df_old, df_new]).loc[~pd.concat([df_old, df_new]).index.duplicated(keep='last')].sort_index()
                                    df_comb.to_csv(csv_file)
                                    
                                    # Sync fresh bars to Supabase Cloud market_prices table
                                    cloud_rows = []
                                    for idx_dt, r_bar in df_new.iterrows():
                                        cloud_rows.append({
                                            "ticker": t,
                                            "date": idx_dt.strftime('%Y-%m-%d'),
                                            "open": float(r_bar['Open']) if pd.notnull(r_bar.get('Open')) else None,
                                            "high": float(r_bar['High']) if pd.notnull(r_bar.get('High')) else None,
                                            "low": float(r_bar['Low']) if pd.notnull(r_bar.get('Low')) else None,
                                            "close": float(r_bar['Close']) if pd.notnull(r_bar.get('Close')) else None,
                                            "volume": int(r_bar['Volume']) if pd.notnull(r_bar.get('Volume')) else None
                                        })
                                    if cloud_rows:
                                        database.upsert_cloud_market_price_rows(cloud_rows)
                        except Exception:
                            pass
    except Exception as e:
        print(f"ensure_latest_market_data error: {e}")

def generate_v229_signals():
    """ Runs daily scan on latest market data to check for v2.29 Buy/Sell signals """
    ensure_latest_market_data()
    data = be.prepare_data(DATA_DIR)
    spy_df = data["SPY"]
    latest_date = spy_df.index[-1]
    prev_date = spy_df.index[-2] if len(spy_df) >= 2 else latest_date
    
    date_str = datetime.date.today().strftime("%Y-%m-%d")
    
    current_prices = {t: data[t].loc[latest_date, 'Close'] for t in data if latest_date in data[t].index}
    if "S5FI" in data and not data["S5FI"].empty:
        if latest_date in data["S5FI"].index:
            s5fi_val = float(data["S5FI"].loc[latest_date, "Close"])
        else:
            s5fi_val = float(data["S5FI"]["Close"].iloc[-1])
    else:
        s5fi_val = 50.0
    
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
