import os
import json
import pandas as pd
import numpy as np

def calculate_supertrend(df, period=10, multiplier=3):
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    
    hl2 = (high + low) / 2
    basic_ub = hl2 + multiplier * atr
    basic_lb = hl2 - multiplier * atr
    
    final_ub = basic_ub.copy()
    final_lb = basic_lb.copy()
    trend = pd.Series(1, index=df.index)
    
    for i in range(1, len(df)):
        if basic_ub.iloc[i] < final_ub.iloc[i-1] or close.iloc[i-1] > final_ub.iloc[i-1]:
            final_ub.iloc[i] = basic_ub.iloc[i]
        else:
            final_ub.iloc[i] = final_ub.iloc[i-1]
            
        if basic_lb.iloc[i] > final_lb.iloc[i-1] or close.iloc[i-1] < final_lb.iloc[i-1]:
            final_lb.iloc[i] = basic_lb.iloc[i]
        else:
            final_lb.iloc[i] = final_lb.iloc[i-1]
            
        if trend.iloc[i-1] == 1:
            if close.iloc[i] < final_lb.iloc[i-1]:
                trend.iloc[i] = -1
            else:
                trend.iloc[i] = 1
        else:
            if close.iloc[i] > final_ub.iloc[i-1]:
                trend.iloc[i] = 1
            else:
                trend.iloc[i] = -1
                
    return trend, final_ub, final_lb

def prepare_data(data_dir="data"):
    tickers = ["SPY", "QQQ", "SOXX", "TQQQ", "QUAL", "JEPQ", "QLD", "PSQ", "SH", "QID", "GLD", "TLT", "DBC", "BITO", "SGOV", "^VIX"]
    data = {}
    
    for ticker in tickers:
        # Option C Architecture: Priority fetch from Supabase Cloud market_prices table (Single Source of Truth)
        df = None
        try:
            from database import fetch_cloud_market_prices
            df_cloud = fetch_cloud_market_prices(ticker)
            if df_cloud is not None and not df_cloud.empty and len(df_cloud) >= 50:
                df = df_cloud
        except Exception:
            pass
            
        if df is None or df.empty:
            file_path = os.path.join(data_dir, f"{ticker}.csv")
            if os.path.exists(file_path):
                df = pd.read_csv(file_path)
                df['Date'] = pd.to_datetime(df['Date'])
            else:
                print(f"Warning: Missing data for {ticker}, skipping.")
                continue
        
        rename_dict = {}
        for col in df.columns:
            if col != 'Date':
                base_name = col.split('_')[0]
                rename_dict[col] = base_name
        df = df.rename(columns=rename_dict)
        
        # Ensure 'Dividends' column exists and is filled
        if 'Dividends' not in df.columns:
            df['Dividends'] = 0.0
        else:
            df['Dividends'] = df['Dividends'].fillna(0.0)
            
        # Calculate ATR(20) for dynamic position sizing
        high = df['High']
        low = df['Low']
        close = df['Close']
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['ATR'] = tr.ewm(span=20, adjust=False).mean()
            
        # EMA200
        df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
        
        # DEMA200
        ema1 = df['Close'].ewm(span=200, adjust=False).mean()
        ema2 = ema1.ewm(span=200, adjust=False).mean()
        df['DEMA200'] = 2 * ema1 - ema2
        
        # Slopes (for v1.0)
        df['EMA200_up'] = df['EMA200'] > df['EMA200'].shift(1)
        df['DEMA200_up'] = df['DEMA200'] > df['DEMA200'].shift(1)
        
        # SuperTrend (10, 3)
        st_trend, st_ub, st_lb = calculate_supertrend(df, period=10, multiplier=3)
        df['ST_trend'] = st_trend
        df['ST_ub'] = st_ub
        df['ST_lb'] = st_lb
        
        data[ticker] = df.set_index('Date')
        
    # Load S5FI if it exists
    s5fi_path = os.path.join(data_dir, "S5FI.csv")
    if os.path.exists(s5fi_path):
        s5fi_df = pd.read_csv(s5fi_path)
        s5fi_df['Date'] = pd.to_datetime(s5fi_df['Date'])
        data["S5FI"] = s5fi_df.set_index('Date')
        print("Loaded S5FI market breadth data.")
    else:
        print("Warning: S5FI.csv not found in data directory.")
        
    return data

def run_standalone_backtest(data, start_date="2021-06-08", end_date="2026-06-08", wait_days=4, use_ma_slope=False, use_trailing_stop=True, use_reinvest_div=False, use_atr_sizing=False, use_market_breadth=False, s5fi_l1_threshold=40.0, s5fi_l2_threshold=60.0, use_panic_exit=False, use_qld_leverage=False, short_mode=None):
    """
    Mode A: Standalone L1/L2 Trend System ($35,000 initial capital).
    Parameterized version for v1.0, v1.9, v2.0, v2.1, v2.2.
    """
    initial_capital = 35000.0
    cash = initial_capital
    nav = initial_capital
    
    positions = {}
    equity_curve = []
    trade_log = []
    
    l1_tickers = ["SPY", "QQQ", "SOXX"]
    l2_whitelist = {
        "SPY": ["QQQ"],
        "QQQ": ["SOXX", "QLD" if use_qld_leverage else "TQQQ"],
        "SOXX": []
    }
    
    cooling_days = {t: 0 for t in l1_tickers}
    all_dates = sorted(data["SPY"].loc[start_date:end_date].index)
    
    for idx, date in enumerate(all_dates):
        current_prices = {}
        for t in data:
            if date in data[t].index:
                current_prices[t] = data[t].loc[date, 'Close']
            else:
                current_prices[t] = None
        
        # Check Standalone L1/L2 Dividends paid to Cash
        if use_reinvest_div:
            for t, pos in list(positions.items()):
                if t in data and date in data[t].index:
                    t_div = data[t].loc[date, "Dividends"]
                    if t_div > 0 and pos['qty'] > 0:
                        div_val = pos['qty'] * t_div
                        cash += div_val
                        trade_log.append({
                            "Type": "DIVIDEND_PAYOUT",
                            "Ticker": t,
                            "Layer": pos['layer'],
                            "Date": date.strftime("%Y-%m-%d"),
                            "Price": current_prices[t],
                            "Value": div_val,
                            "Reason": f"Received {t} dividend: {t_div:.4f}/share paid to cash"
                        })

        # Calculate NAV and update peak price
        position_value = 0.0
        for t, pos in positions.items():
            price = current_prices[t]
            if price is not None:
                position_value += pos['qty'] * price
                if pos['layer'] == 'L2':
                    pos['peak_price'] = max(pos.get('peak_price', pos['entry_price']), price)
            else:
                position_value += pos['qty'] * pos['entry_price']
                
        nav = cash + position_value
        equity_curve.append({
            "Date": date.strftime("%Y-%m-%d"),
            "NAV": float(nav),
            "Cash": float(cash),
            "PositionsValue": float(position_value),
            "Positions": {t: float(pos['qty'] * current_prices[t]) for t, pos in positions.items()}
        })
        
        for t in cooling_days:
            if cooling_days[t] > 0:
                cooling_days[t] -= 1
                
        # 1. Check Exits (Execute next day open)
        to_sell = []
        for t, pos in list(positions.items()):
            df_t = data[t]
            if date not in df_t.index:
                continue
                
            st_trend = df_t.loc[date, 'ST_trend']
            
            # Exit L2
            if pos['layer'] == 'L2':
                parent = pos['parent_ticker']
                df_parent = data[parent]
                parent_st_trend = df_parent.loc[date, 'ST_trend'] if date in df_parent.index else -1
                
                # Trailing stop check (if enabled)
                is_trailing_stop = False
                if use_trailing_stop:
                    price_today = current_prices[t]
                    peak = pos.get('peak_price', pos['entry_price'])
                    is_trailing_stop = (price_today is not None) and (price_today <= peak * 0.90)
                
                is_panic_exit = False
                if use_panic_exit and "S5FI" in data and date in data["S5FI"].index:
                    s5fi_val = float(data["S5FI"].loc[date, "Close"])
                    if s5fi_val < 20.0:
                        is_panic_exit = True
                        
                if st_trend == -1 or parent_st_trend == -1 or is_trailing_stop or is_panic_exit:
                    to_sell.append(t)
                    if is_panic_exit:
                        pos['exit_reason'] = "S5FI breadth panic exit (<20%)"
                    elif is_trailing_stop:
                        pos['exit_reason'] = "Trailing Stop-loss (10% from peak)"
                    else:
                        pos['exit_reason'] = "SuperTrend turned Bearish (Exit L2)"
            
            # Exit Short
            elif pos['layer'] == 'Short':
                parent = pos['parent_ticker']
                df_parent = data[parent]
                parent_st_trend = df_parent.loc[date, 'ST_trend'] if date in df_parent.index else 1
                
                s5fi_recovered = False
                if use_market_breadth and "S5FI" in data and date in data["S5FI"].index:
                    s5fi_val = float(data["S5FI"].loc[date, "Close"])
                    if s5fi_val >= s5fi_l1_threshold:
                        s5fi_recovered = True
                        
                price_today = current_prices[t]
                is_stop_loss = (price_today is not None) and (price_today <= pos['entry_price'] * 0.95)
                
                if parent_st_trend == 1 or s5fi_recovered or is_stop_loss:
                    to_sell.append(t)
                    if is_stop_loss:
                        pos['exit_reason'] = "Short Hard Stop-loss (5% loss)"
                    elif s5fi_recovered:
                        pos['exit_reason'] = f"S5FI Breadth Recovered (>= {s5fi_l1_threshold}%)"
                    else:
                        pos['exit_reason'] = f"Parent {parent} SuperTrend turned Bullish (Exit Short)"
                        
            # Exit Short
            elif pos['layer'] == 'Short':
                parent = pos['parent_ticker']
                df_parent = data[parent]
                parent_st_trend = df_parent.loc[date, 'ST_trend'] if date in df_parent.index else 1
                
                s5fi_recovered = False
                if use_market_breadth and "S5FI" in data and date in data["S5FI"].index:
                    s5fi_val = float(data["S5FI"].loc[date, "Close"])
                    if s5fi_val >= s5fi_l1_threshold:
                        s5fi_recovered = True
                        
                price_today = current_prices[t]
                is_stop_loss = (price_today is not None) and (price_today <= pos['entry_price'] * 0.95)
                
                if parent_st_trend == 1 or s5fi_recovered or is_stop_loss:
                    to_sell.append(t)
                    if is_stop_loss:
                        pos['exit_reason'] = "Short Hard Stop-loss (5% loss)"
                    elif s5fi_recovered:
                        pos['exit_reason'] = f"S5FI Breadth Recovered (>= {s5fi_l1_threshold}%)"
                    else:
                        pos['exit_reason'] = f"Parent {parent} SuperTrend turned Bullish (Exit Short)"
                        
            # Exit L1
            elif pos['layer'] == 'L1':
                if st_trend == -1:
                    to_sell.append(t)
                    pos['exit_reason'] = "SuperTrend turned Bearish (Exit L1)"
                    cooling_days[t] = wait_days
                    
        to_sell_sorted = []
        for t in to_sell:
            if positions[t]['layer'] == 'Short':
                to_sell_sorted.append(t)
        for t in to_sell:
            if positions[t]['layer'] == 'L2':
                to_sell_sorted.append(t)
        for t in to_sell:
            if positions[t]['layer'] == 'L1':
                to_sell_sorted.append(t)
                
        if idx < len(all_dates) - 1:
            next_date = all_dates[idx + 1]
            for t in to_sell_sorted:
                pos = positions.pop(t)
                next_open = data[t].loc[next_date, 'Open']
                sell_val = pos['qty'] * next_open
                cash += sell_val
                
                trade_log.append({
                    "Type": "SELL",
                    "Ticker": t,
                    "Layer": pos['layer'],
                    "Date": next_date.strftime("%Y-%m-%d"),
                    "Price": next_open,
                    "Value": sell_val,
                    "EntryPrice": pos['entry_price'],
                    "EntryDate": pos['entry_date'].strftime("%Y-%m-%d"),
                    "ReturnPct": (next_open / pos['entry_price'] - 1) * 100,
                    "Profit": sell_val - (pos['qty'] * pos['entry_price']),
                    "Reason": pos.get('exit_reason', f"SuperTrend turned Bearish (Exit {pos['layer']})")
                })
                
        # 2. Check Entries (Execute next day open)
        if idx < len(all_dates) - 1:
            next_date = all_dates[idx + 1]
            
            # L1 Entries
            for t in l1_tickers:
                if t in positions:
                    continue
                if cooling_days[t] > 0:
                    continue
                    
                df_t = data[t]
                if date not in df_t.index or next_date not in df_t.index:
                    continue
                
                row = df_t.loc[date]
                prev_idx = df_t.index.get_loc(date) - 1
                if prev_idx < 0:
                    continue
                prev_trend = df_t.iloc[prev_idx]['ST_trend']
                
                # Check Entry Logic based on MA Slope Parameter
                if use_ma_slope:
                    # v1.0: Price > EMA200 & Price > DEMA200, Slopes rising
                    price_above_ma = (row['Close'] > row['EMA200']) and (row['Close'] > row['DEMA200'])
                    ma_rising = row['EMA200_up'] and row['DEMA200_up']
                    st_turned_bullish = (row['ST_trend'] == 1) and (prev_trend == -1)
                    entry_signal = price_above_ma and ma_rising and st_turned_bullish
                    reason_str = "EMA & DEMA > 200, MAs rising, SuperTrend turned Bullish (L1 Entry)"
                else:
                    # v1.9 / v2.0: Price > EMA200, SuperTrend turns Bullish
                    price_above_ma = row['Close'] > row['EMA200']
                    st_turned_bullish = (row['ST_trend'] == 1) and (prev_trend == -1)
                    entry_signal = price_above_ma and st_turned_bullish
                    reason_str = "Price > EMA200, SuperTrend turned Bullish (L1 Entry)"
                
                if entry_signal:
                    if use_market_breadth and "S5FI" in data and date in data["S5FI"].index:
                        s5fi_val = float(data["S5FI"].loc[date, "Close"])
                        if s5fi_val < s5fi_l1_threshold:
                            entry_signal = False
                            
                if entry_signal:
                    target_val = nav * 0.10
                    if use_atr_sizing:
                        atr_pct = data[t].loc[date, 'ATR'] / current_prices[t]
                        if atr_pct > 0:
                            target_val = (nav * 0.0025) / atr_pct
                            target_val = min(target_val, nav * 0.10)
                            
                    current_l1_l2_val = sum(pos['qty'] * current_prices[pos_t] for pos_t, pos in positions.items())
                    if current_l1_l2_val + target_val <= nav * 0.35:
                        buy_val = min(target_val, cash)
                        if buy_val > 0:
                            next_open = df_t.loc[next_date, 'Open']
                            qty = buy_val / next_open
                            cash -= buy_val
                            positions[t] = {
                                "qty": qty,
                                "entry_price": next_open,
                                "entry_date": next_date,
                                "layer": "L1",
                                "parent_ticker": None
                            }
                            
                            trade_log.append({
                                "Type": "BUY",
                                "Ticker": t,
                                "Layer": "L1",
                                "Date": next_date.strftime("%Y-%m-%d"),
                                "Price": next_open,
                                "Value": buy_val,
                                "Reason": reason_str
                            })
                            
            # L2 Entries
            for l1_t in l1_tickers:
                if l1_t not in positions or positions[l1_t]['layer'] != 'L1':
                    continue
                
                l1_pos = positions[l1_t]
                if l1_pos['entry_date'] >= next_date:
                    continue
                    
                if data[l1_t].loc[date, 'ST_trend'] != 1:
                    continue
                    
                for l2_t in l2_whitelist[l1_t]:
                    if l2_t in positions:
                        continue
                        
                    df_l2 = data[l2_t]
                    if date not in df_l2.index:
                        continue
                        
                    l2_st = df_l2.loc[date, 'ST_trend']
                    if l2_st == 1:
                        if use_market_breadth and "S5FI" in data and date in data["S5FI"].index:
                            s5fi_val = float(data["S5FI"].loc[date, "Close"])
                            if s5fi_val < s5fi_l2_threshold:
                                continue
                                
                        target_val = nav * 0.08
                        if use_atr_sizing:
                            atr_pct = data[l2_t].loc[date, 'ATR'] / current_prices[l2_t]
                            if atr_pct > 0:
                                target_val = (nav * 0.0025) / atr_pct
                                target_val = min(target_val, nav * 0.08)
                                
                        existing_qty_val = 0.0
                        if l2_t in positions:
                            existing_qty_val = positions[l2_t]['qty'] * current_prices[l2_t]
                        if existing_qty_val + target_val > nav * 0.10:
                            target_val = max(0.0, nav * 0.10 - existing_qty_val)
                            
                        current_l1_l2_val = sum(pos['qty'] * current_prices[pos_t] for pos_t, pos in positions.items())
                        if current_l1_l2_val + target_val <= nav * 0.35 and target_val > 0:
                            buy_val = min(target_val, cash)
                            if buy_val > 0:
                                next_open = df_l2.loc[next_date, 'Open']
                                qty = buy_val / next_open
                                cash -= buy_val
                                positions[l2_t] = {
                                    "qty": qty,
                                    "entry_price": next_open,
                                    "entry_date": next_date,
                                    "layer": "L2",
                                    "parent_ticker": l1_t,
                                    "peak_price": next_open
                                }
                                
                                trade_log.append({
                                    "Type": "BUY",
                                    "Ticker": l2_t,
                                    "Layer": "L2",
                                    "Date": next_date.strftime("%Y-%m-%d"),
                                    "Price": next_open,
                                    "Value": buy_val,
                                    "Reason": f"L1 {l1_t} held, L2 {l2_t} is SuperTrend Bullish (L2 Entry)"
                                })
                                
            # Short Entries
            if short_mode and short_mode not in positions:
                short_ticker = short_mode
                parent_ticker = "SPY" if short_mode == "SH" else "QQQ"
                
                if parent_ticker in data and date in data[parent_ticker].index and short_ticker in data and date in data[short_ticker].index and next_date in data[short_ticker].index:
                    parent_row = data[parent_ticker].loc[date]
                    parent_st_trend = parent_row['ST_trend']
                    parent_below_ema = parent_row['Close'] < parent_row['EMA200']
                    
                    s5fi_low = False
                    if use_market_breadth and "S5FI" in data and date in data["S5FI"].index:
                        s5fi_val = float(data["S5FI"].loc[date, "Close"])
                        if s5fi_val < s5fi_l1_threshold:
                            s5fi_low = True
                    else:
                        s5fi_low = True
                        
                    if parent_below_ema and parent_st_trend == -1 and s5fi_low:
                        target_val = nav * (0.08 if short_mode == "QID" else 0.10)
                        current_l1_l2_val = sum(pos['qty'] * current_prices[pos_t] for pos_t, pos in positions.items())
                        if current_l1_l2_val + target_val <= nav * 0.35 and target_val > 0:
                            buy_val = min(target_val, cash)
                            if buy_val > 0:
                                next_open = data[short_ticker].loc[next_date, 'Open']
                                qty = buy_val / next_open
                                cash -= buy_val
                                positions[short_ticker] = {
                                    "qty": qty,
                                    "entry_price": next_open,
                                    "entry_date": next_date,
                                    "layer": "Short",
                                    "parent_ticker": parent_ticker,
                                    "peak_price": next_open
                                }
                                trade_log.append({
                                    "Type": "BUY",
                                    "Ticker": short_ticker,
                                    "Layer": "Short",
                                    "Date": next_date.strftime("%Y-%m-%d"),
                                    "Price": next_open,
                                    "Value": buy_val,
                                    "Reason": f"Bearish Trend on {parent_ticker} (Price < EMA200 & SuperTrend -1 & S5FI < {s5fi_l1_threshold}%), Buy {short_ticker}"
                                })
                                
    return equity_curve, trade_log

def run_combined_backtest(data, start_date="2022-05-04", end_date="2026-06-08", wait_days=4, 
                          use_ma_slope=False, use_trailing_stop=True, 
                          initial_cash=20000.0, target_jepq_pct=0.48, target_qual_pct=0.32,
                          use_reinvest_div=False, use_atr_sizing=False, use_market_breadth=False,
                          s5fi_l1_threshold=40.0, s5fi_l2_threshold=60.0,
                          use_panic_exit=False, use_qld_leverage=False, short_mode=None):
    """
    Mode B: Combined System.
    Parameterized version to support v1.0, v1.9, v2.0, v2.1, v2.2.
    """
    initial_capital = 100000.0
    cash = initial_cash
    
    positions = {}
    
    jepq_start_price = data["JEPQ"].loc[start_date, "Close"]
    qual_start_price = data["QUAL"].loc[start_date, "Close"]
    
    # Calculate starting shares based on target pct
    jepq_shares = (initial_capital * target_jepq_pct) / jepq_start_price
    qual_shares = (initial_capital * target_qual_pct) / qual_start_price
    
    equity_curve = []
    trade_log = []
    jepq_sell_log = []
    
    l1_tickers = ["SPY", "QQQ", "SOXX"]
    l2_whitelist = {
        "SPY": ["QQQ"],
        "QQQ": ["SOXX", "QLD" if use_qld_leverage else "TQQQ"],
        "SOXX": []
    }
    
    cooling_days = {t: 0 for t in l1_tickers}
    all_dates = sorted(data["SPY"].loc[start_date:end_date].index)
    
    for idx, date in enumerate(all_dates):
        current_prices = {}
        for t in data:
            if date in data[t].index:
                current_prices[t] = data[t].loc[date, 'Close']
            else:
                current_prices[t] = None
        
        # Check Dividends and Reinvest
        if use_reinvest_div:
            # JEPQ
            if "JEPQ" in data and date in data["JEPQ"].index:
                jepq_div = data["JEPQ"].loc[date, "Dividends"]
                if jepq_div > 0 and jepq_shares > 0:
                    div_val = jepq_shares * jepq_div
                    jepq_price = current_prices["JEPQ"]
                    added_shares = div_val / jepq_price
                    jepq_shares += added_shares
                    trade_log.append({
                        "Type": "DIVIDEND_REINVEST",
                        "Ticker": "JEPQ",
                        "Layer": "L0+",
                        "Date": date.strftime("%Y-%m-%d"),
                        "Price": jepq_price,
                        "Value": div_val,
                        "Reason": f"Reinvested JEPQ dividend: {jepq_div:.4f}/share (+{added_shares:.4f} shares)"
                    })
            # QUAL
            if "QUAL" in data and date in data["QUAL"].index:
                qual_div = data["QUAL"].loc[date, "Dividends"]
                if qual_div > 0 and qual_shares > 0:
                    div_val = qual_shares * qual_div
                    qual_price = current_prices["QUAL"]
                    added_shares = div_val / qual_price
                    qual_shares += added_shares
                    trade_log.append({
                        "Type": "DIVIDEND_REINVEST",
                        "Ticker": "QUAL",
                        "Layer": "L0+",
                        "Date": date.strftime("%Y-%m-%d"),
                        "Price": qual_price,
                        "Value": div_val,
                        "Reason": f"Reinvested QUAL dividend: {qual_div:.4f}/share (+{added_shares:.4f} shares)"
                    })
            # L1/L2 Dividends paid to Cash
            for t, pos in list(positions.items()):
                if t in data and date in data[t].index:
                    t_div = data[t].loc[date, "Dividends"]
                    if t_div > 0 and pos['qty'] > 0:
                        div_val = pos['qty'] * t_div
                        cash += div_val
                        trade_log.append({
                            "Type": "DIVIDEND_PAYOUT",
                            "Ticker": t,
                            "Layer": pos['layer'],
                            "Date": date.strftime("%Y-%m-%d"),
                            "Price": current_prices[t],
                            "Value": div_val,
                            "Reason": f"Received {t} dividend: {t_div:.4f}/share paid to cash"
                        })

        jepq_val = jepq_shares * current_prices["JEPQ"]
        qual_val = qual_shares * current_prices["QUAL"]
        
        position_value = 0.0
        for t, pos in positions.items():
            price = current_prices[t]
            if price is not None:
                position_value += pos['qty'] * price
                if pos['layer'] == 'L2':
                    pos['peak_price'] = max(pos.get('peak_price', pos['entry_price']), price)
            else:
                position_value += pos['qty'] * pos['entry_price']
                
        nav = cash + jepq_val + qual_val + position_value
        
        equity_curve.append({
            "Date": date.strftime("%Y-%m-%d"),
            "NAV": float(nav),
            "Cash": float(cash),
            "JEPQ_Val": float(jepq_val),
            "QUAL_Val": float(qual_val),
            "L1_L2_Val": float(position_value),
            "JEPQ_Qty": float(jepq_shares),
            "QUAL_Qty": float(qual_shares),
            "Positions": {t: float(pos['qty'] * current_prices[t]) for t, pos in positions.items()}
        })
        
        for t in cooling_days:
            if cooling_days[t] > 0:
                cooling_days[t] -= 1
                
        # 1. Check Exits (Execute next day open)
        to_sell = []
        for t, pos in list(positions.items()):
            df_t = data[t]
            if date not in df_t.index:
                continue
                
            st_trend = df_t.loc[date, 'ST_trend']
            
            # Exit L2
            if pos['layer'] == 'L2':
                parent = pos['parent_ticker']
                df_parent = data[parent]
                parent_st_trend = df_parent.loc[date, 'ST_trend'] if date in df_parent.index else -1
                
                is_trailing_stop = False
                if use_trailing_stop:
                    price_today = current_prices[t]
                    peak = pos.get('peak_price', pos['entry_price'])
                    is_trailing_stop = (price_today is not None) and (price_today <= peak * 0.90)
                
                is_panic_exit = False
                if use_panic_exit and "S5FI" in data and date in data["S5FI"].index:
                    s5fi_val = float(data["S5FI"].loc[date, "Close"])
                    if s5fi_val < 20.0:
                        is_panic_exit = True
                        
                if st_trend == -1 or parent_st_trend == -1 or is_trailing_stop or is_panic_exit:
                    to_sell.append(t)
                    if is_panic_exit:
                        pos['exit_reason'] = "S5FI breadth panic exit (<20%)"
                    elif is_trailing_stop:
                        pos['exit_reason'] = "Trailing Stop-loss (10% from peak)"
                    else:
                        pos['exit_reason'] = "SuperTrend turned Bearish (Exit L2)"
            
            # Exit L1
            elif pos['layer'] == 'L1':
                if st_trend == -1:
                    to_sell.append(t)
                    pos['exit_reason'] = "SuperTrend turned Bearish (Exit L1)"
                    cooling_days[t] = wait_days
                    
        to_sell_sorted = []
        for t in to_sell:
            if positions[t]['layer'] == 'Short':
                to_sell_sorted.append(t)
        for t in to_sell:
            if positions[t]['layer'] == 'L2':
                to_sell_sorted.append(t)
        for t in to_sell:
            if positions[t]['layer'] == 'L1':
                to_sell_sorted.append(t)
                
        if idx < len(all_dates) - 1:
            next_date = all_dates[idx + 1]
            for t in to_sell_sorted:
                pos = positions.pop(t)
                next_open = data[t].loc[next_date, 'Open']
                sell_val = pos['qty'] * next_open
                cash += sell_val
                
                trade_log.append({
                    "Type": "SELL",
                    "Ticker": t,
                    "Layer": pos['layer'],
                    "Date": next_date.strftime("%Y-%m-%d"),
                    "Price": next_open,
                    "Value": sell_val,
                    "EntryPrice": pos['entry_price'],
                    "EntryDate": pos['entry_date'].strftime("%Y-%m-%d"),
                    "ReturnPct": (next_open / pos['entry_price'] - 1) * 100,
                    "Profit": sell_val - (pos['qty'] * pos['entry_price']),
                    "Reason": pos.get('exit_reason', f"SuperTrend turned Bearish (Exit {pos['layer']})")
                })
                
        # 2. Check Entries (Execute next day open)
        if idx < len(all_dates) - 1:
            next_date = all_dates[idx + 1]
            
            def fund_and_buy(ticker, layer, target_val, reason, parent_t=None):
                nonlocal cash, jepq_shares, jepq_val
                
                if cash >= target_val:
                    buy_val = target_val
                else:
                    deficit = target_val - cash
                    max_sell_limit = nav * 0.10
                    sell_amount = min(deficit, jepq_val, max_sell_limit)
                    
                    if sell_amount < deficit:
                        sell_amount = min(deficit, jepq_val)
                        
                    if sell_amount > 0:
                        jepq_next_open = data["JEPQ"].loc[next_date, 'Open']
                        sell_qty = sell_amount / jepq_next_open
                        jepq_shares -= sell_qty
                        cash += sell_amount
                        
                        jepq_sell_log.append({
                            "Date": next_date.strftime("%Y-%m-%d"),
                            "Amount": float(sell_amount),
                            "Qty": float(sell_qty),
                            "Reason": f"Fund {layer} buy for {ticker}"
                        })
                    
                    buy_val = min(target_val, cash)
                
                if buy_val > 0:
                    next_open = data[ticker].loc[next_date, 'Open']
                    qty = buy_val / next_open
                    cash -= buy_val
                    
                    pos_dict = {
                        "qty": qty,
                        "entry_price": next_open,
                        "entry_date": next_date,
                        "layer": layer,
                        "parent_ticker": parent_t
                    }
                    if layer == 'L2':
                        pos_dict["peak_price"] = next_open
                        
                    positions[ticker] = pos_dict
                    
                    trade_log.append({
                        "Type": "BUY",
                        "Ticker": ticker,
                        "Layer": layer,
                        "Date": next_date.strftime("%Y-%m-%d"),
                        "Price": next_open,
                        "Value": buy_val,
                        "Reason": reason
                    })
            
            # L1 Entries
            for t in l1_tickers:
                if t in positions:
                    continue
                if cooling_days[t] > 0:
                    continue
                    
                df_t = data[t]
                if date not in df_t.index or next_date not in df_t.index:
                    continue
                
                row = df_t.loc[date]
                prev_idx = df_t.index.get_loc(date) - 1
                if prev_idx < 0:
                    continue
                prev_trend = df_t.iloc[prev_idx]['ST_trend']
                
                # Check Entry Logic based on MA Slope Parameter
                if use_ma_slope:
                    price_above_ma = (row['Close'] > row['EMA200']) and (row['Close'] > row['DEMA200'])
                    ma_rising = row['EMA200_up'] and row['DEMA200_up']
                    st_turned_bullish = (row['ST_trend'] == 1) and (prev_trend == -1)
                    entry_signal = price_above_ma and ma_rising and st_turned_bullish
                    reason_str = "EMA & DEMA > 200, MAs rising, SuperTrend turned Bullish (L1 Entry)"
                else:
                    price_above_ma = row['Close'] > row['EMA200']
                    st_turned_bullish = (row['ST_trend'] == 1) and (prev_trend == -1)
                    entry_signal = price_above_ma and st_turned_bullish
                    reason_str = "Price > EMA200, SuperTrend turned Bullish (L1 Entry)"
                
                if entry_signal:
                    if use_market_breadth and "S5FI" in data and date in data["S5FI"].index:
                        s5fi_val = float(data["S5FI"].loc[date, "Close"])
                        if s5fi_val < s5fi_l1_threshold:
                            entry_signal = False
                            
                if entry_signal:
                    target_val = nav * 0.10
                    if use_atr_sizing:
                        atr_pct = data[t].loc[date, 'ATR'] / current_prices[t]
                        if atr_pct > 0:
                            target_val = (nav * 0.0025) / atr_pct
                            target_val = min(target_val, nav * 0.10)
                            
                    current_l1_l2_val = sum(pos['qty'] * current_prices[pos_t] for pos_t, pos in positions.items())
                    if current_l1_l2_val + target_val <= nav * 0.35:
                        fund_and_buy(t, "L1", target_val, reason_str)
                            
            # L2 Entries
            for l1_t in l1_tickers:
                if l1_t not in positions or positions[l1_t]['layer'] != 'L1':
                    continue
                
                l1_pos = positions[l1_t]
                if l1_pos['entry_date'] >= next_date:
                    continue
                    
                if data[l1_t].loc[date, 'ST_trend'] != 1:
                    continue
                    
                for l2_t in l2_whitelist[l1_t]:
                    if l2_t in positions:
                        continue
                        
                    df_l2 = data[l2_t]
                    if date not in df_l2.index or next_date not in df_l2.index:
                        continue
                        
                    l2_st = df_l2.loc[date, 'ST_trend']
                    if l2_st == 1:
                        if use_market_breadth and "S5FI" in data and date in data["S5FI"].index:
                            s5fi_val = float(data["S5FI"].loc[date, "Close"])
                            if s5fi_val < s5fi_l2_threshold:
                                continue
                                
                        target_val = nav * 0.08
                        if use_atr_sizing:
                            atr_pct = data[l2_t].loc[date, 'ATR'] / current_prices[l2_t]
                            if atr_pct > 0:
                                target_val = (nav * 0.0025) / atr_pct
                                target_val = min(target_val, nav * 0.08)
                        
                        existing_qty_val = 0.0
                        if l2_t in positions:
                            existing_qty_val = positions[l2_t]['qty'] * current_prices[l2_t]
                        if existing_qty_val + target_val > nav * 0.10:
                            target_val = max(0.0, nav * 0.10 - existing_qty_val)
                            
                        current_l1_l2_val = sum(pos['qty'] * current_prices[pos_t] for pos_t, pos in positions.items())
                        if current_l1_l2_val + target_val <= nav * 0.35 and target_val > 0:
                            fund_and_buy(l2_t, "L2", target_val, f"L1 {l1_t} held, L2 {l2_t} is SuperTrend Bullish (L2 Entry)", l1_t)
                            
            # Short Entries
            if short_mode and short_mode not in positions:
                short_ticker = short_mode
                parent_ticker = "SPY" if short_mode == "SH" else "QQQ"
                
                if parent_ticker in data and date in data[parent_ticker].index and short_ticker in data and date in data[short_ticker].index and next_date in data[short_ticker].index:
                    parent_row = data[parent_ticker].loc[date]
                    parent_st_trend = parent_row['ST_trend']
                    parent_below_ema = parent_row['Close'] < parent_row['EMA200']
                    
                    s5fi_low = False
                    if use_market_breadth and "S5FI" in data and date in data["S5FI"].index:
                        s5fi_val = float(data["S5FI"].loc[date, "Close"])
                        if s5fi_val < s5fi_l1_threshold:
                            s5fi_low = True
                    else:
                        s5fi_low = True
                        
                    if parent_below_ema and parent_st_trend == -1 and s5fi_low:
                        target_val = nav * (0.08 if short_mode == "QID" else 0.10)
                        current_l1_l2_val = sum(pos['qty'] * current_prices[pos_t] for pos_t, pos in positions.items())
                        if current_l1_l2_val + target_val <= nav * 0.35 and target_val > 0:
                            fund_and_buy(short_ticker, "Short", target_val, f"Bearish Trend on {parent_ticker} (Price < EMA200 & SuperTrend -1 & S5FI < {s5fi_l1_threshold}%), Buy {short_ticker}", parent_ticker)
            
            # 3. L0+ Refill / Cash Sweeping (Next day open)
            # v1.0 holds 35% cash buffer, rebalances cash if cash > 15% NAV
            # v1.9 / v2.0 holds 20% cash buffer, rebalances cash if cash > 10% NAV
            cash_threshold = nav * 0.15 if use_ma_slope else nav * 0.10
            min_cash_buffer = nav * 0.10 if use_ma_slope else nav * 0.05
            
            if cash > cash_threshold:
                target_jepq_val = nav * target_jepq_pct
                current_jepq_val = jepq_shares * current_prices["JEPQ"]
                
                if current_jepq_val < target_jepq_val:
                    excess_cash = cash - min_cash_buffer
                    buy_amount = min(excess_cash, target_jepq_val - current_jepq_val)
                    
                    if buy_amount > 100.0:
                        jepq_next_open = data["JEPQ"].loc[next_date, 'Open']
                        buy_qty = buy_amount / jepq_next_open
                        jepq_shares += buy_qty
                        cash -= buy_amount
                        
                        trade_log.append({
                            "Type": "REBALANCE_BUY",
                            "Ticker": "JEPQ",
                            "Layer": "L0+",
                            "Date": next_date.strftime("%Y-%m-%d"),
                            "Price": jepq_next_open,
                            "Value": buy_amount,
                            "Reason": f"Refill JEPQ buffer pool using excess cash (Cash: ${cash:.2f})"
                        })
                        
    return equity_curve, trade_log, jepq_sell_log

def compute_metrics(equity_curve, benchmark_df, name="Strategy"):
    df = pd.DataFrame(equity_curve)
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.set_index('Date')
    
    df['Daily_Return'] = df['NAV'].pct_change()
    total_return = (df['NAV'].iloc[-1] / df['NAV'].iloc[0] - 1) * 100
    
    trading_days = len(df)
    years = trading_days / 252.0
    cagr = ((df['NAV'].iloc[-1] / df['NAV'].iloc[0]) ** (1.0 / years) - 1) * 100
    
    df['Peak'] = df['NAV'].cummax()
    df['Drawdown'] = (df['NAV'] - df['Peak']) / df['Peak']
    max_dd = df['Drawdown'].min() * 100
    
    std = df['Daily_Return'].std()
    mean = df['Daily_Return'].mean()
    sharpe = (mean / std * np.sqrt(252)) if std != 0 else 0
    
    downside_returns = df['Daily_Return'][df['Daily_Return'] < 0]
    downside_std = downside_returns.std()
    sortino = (mean / downside_std * np.sqrt(252)) if downside_std != 0 else 0
    
    return {
        "Name": name,
        "TotalReturnPct": total_return,
        "CAGR": cagr,
        "MaxDrawdownPct": max_dd,
        "SharpeRatio": sharpe,
        "SortinoRatio": sortino,
        "InitialNAV": float(df['NAV'].iloc[0]),
        "FinalNAV": float(df['NAV'].iloc[-1])
    }

def main():
    print("Loading data and calculating indicators...")
    data = prepare_data("data")
    
    # Define Configurations
    # Format: (use_ma_slope, use_trailing_stop, initial_cash, target_jepq_pct, target_qual_pct, use_reinvest_div, use_atr_sizing, use_market_breadth, s5fi_l1_threshold, s5fi_l2_threshold, use_panic_exit, use_qld_leverage)
    configs = {
        "v1.0": (True, False, 35000.0, 0.39, 0.26, False, False, False, 40.0, 60.0, False, False),
        "v1.9": (False, False, 20000.0, 0.48, 0.32, False, False, False, 40.0, 60.0, False, False),
        "v2.0": (False, True, 20000.0, 0.48, 0.32, False, False, False, 40.0, 60.0, False, False),
        "v2.1": (False, False, 20000.0, 0.48, 0.32, True, False, False, 40.0, 60.0, False, False),
        "v2.2": (False, False, 20000.0, 0.48, 0.32, True, True, False, 40.0, 60.0, False, False),
        "v2.21": (False, False, 20000.0, 0.48, 0.32, True, False, True, 40.0, 60.0, False, False),
        "v2.22": (False, False, 20000.0, 0.48, 0.32, True, False, True, 45.0, 55.0, False, False),
        "v2.23": (False, False, 20000.0, 0.48, 0.32, True, False, True, 45.0, 55.0, True, False),
        "v2.24": (False, False, 20000.0, 0.48, 0.32, True, False, True, 45.0, 55.0, False, True, None),
        "v2.25_PSQ": (False, False, 20000.0, 0.48, 0.32, True, False, True, 45.0, 55.0, False, True, "PSQ"),
        "v2.25_SH": (False, False, 20000.0, 0.48, 0.32, True, False, True, 45.0, 55.0, False, True, "SH"),
        "v2.25_QID": (False, False, 20000.0, 0.48, 0.32, True, False, True, 45.0, 55.0, False, True, "QID"),
        "v2.3": (False, False, 20000.0, 0.48, 0.32, True, True, True, 40.0, 60.0, False, False, None)
    }
    
    results = {}
    
    # Align date structures
    spy_df = data["SPY"].loc["2021-06-08":"2026-06-08"]
    qqq_df = data["QQQ"].loc["2021-06-08":"2026-06-08"]
    
    # 1. Run Standalone Backtests (5 Years: 2021-06-08 to 2026-06-08)
    print("Running Standalone Backtests...")
    results["standalone"] = {}
    for ver, cfg in configs.items():
        print(f"  Running Standalone {ver}...")
        sec, stl = run_standalone_backtest(
            data, start_date="2021-06-08", end_date="2026-06-08", wait_days=4,
            use_ma_slope=cfg[0], use_trailing_stop=cfg[1], use_reinvest_div=cfg[5], use_atr_sizing=cfg[6],
            use_market_breadth=cfg[7], s5fi_l1_threshold=cfg[8], s5fi_l2_threshold=cfg[9],
            use_panic_exit=cfg[10], use_qld_leverage=cfg[11], short_mode=cfg[12] if len(cfg) > 12 else None
        )
        met = compute_metrics(sec, spy_df, f"L1/L2 Standalone {ver}")
        results["standalone"][ver] = {
            "metrics": met,
            "equity_curve": sec,
            "trade_log": stl
        }
        
    # Standalone Benchmarks
    spy_bh_st = [{"Date": d.strftime("%Y-%m-%d"), "NAV": float((spy_df.loc[d, "Close"] / spy_df.iloc[0]["Close"]) * 35000.0)} for d in spy_df.index]
    qqq_bh_st = [{"Date": d.strftime("%Y-%m-%d"), "NAV": float((qqq_df.loc[d, "Close"] / qqq_df.iloc[0]["Close"]) * 35000.0)} for d in data["QQQ"].loc["2021-06-08":"2026-06-08"].index]
    
    results["standalone"]["spy_metrics"] = compute_metrics(spy_bh_st, spy_df, "SPY Buy-and-Hold (35k)")
    results["standalone"]["qqq_metrics"] = compute_metrics(qqq_bh_st, spy_df, "QQQ Buy-and-Hold (35k)")
    results["standalone"]["spy_bh"] = spy_bh_st
    results["standalone"]["qqq_bh"] = qqq_bh_st
    
    # 2. Run Combined Backtests (Since JEPQ Inception: 2022-05-04 to 2026-06-08)
    print("Running Combined Portfolio Backtests...")
    results["combined"] = {}
    for ver, cfg in configs.items():
        print(f"  Running Combined {ver}...")
        cec, ctl, cjsl = run_combined_backtest(
            data, start_date="2022-05-04", end_date="2026-06-08", wait_days=4,
            use_ma_slope=cfg[0], use_trailing_stop=cfg[1],
            initial_cash=cfg[2], target_jepq_pct=cfg[3], target_qual_pct=cfg[4],
            use_reinvest_div=cfg[5], use_atr_sizing=cfg[6], use_market_breadth=cfg[7],
            s5fi_l1_threshold=cfg[8], s5fi_l2_threshold=cfg[9],
            use_panic_exit=cfg[10], use_qld_leverage=cfg[11], short_mode=cfg[12] if len(cfg) > 12 else None
        )
        met = compute_metrics(cec, data["SPY"].loc["2022-05-04":"2026-06-08"], f"Combined {ver}")
        results["combined"][ver] = {
            "metrics": met,
            "equity_curve": cec,
            "trade_log": ctl,
            "jepq_sells": cjsl
        }
        
    # Combined Benchmarks
    spy_bh_cb = [{"Date": d.strftime("%Y-%m-%d"), "NAV": float((data["SPY"].loc[d, "Close"] / data["SPY"].loc["2022-05-04", "Close"]) * 100000.0)} for d in data["SPY"].loc["2022-05-04":"2026-06-08"].index]
    qqq_bh_cb = [{"Date": d.strftime("%Y-%m-%d"), "NAV": float((data["QQQ"].loc[d, "Close"] / data["QQQ"].loc["2022-05-04", "Close"]) * 100000.0)} for d in data["QQQ"].loc["2022-05-04":"2026-06-08"].index]
    
    results["combined"]["spy_metrics"] = compute_metrics(spy_bh_cb, data["SPY"].loc["2022-05-04":"2026-06-08"], "SPY Buy-and-Hold (100k)")
    results["combined"]["qqq_metrics"] = compute_metrics(qqq_bh_cb, data["QQQ"].loc["2022-05-04":"2026-06-08"], "QQQ Buy-and-Hold (100k)")
    results["combined"]["spy_bh"] = spy_bh_cb
    results["combined"]["qqq_bh"] = qqq_bh_cb
    
    # 3. Sensitivity Analysis (on v2.0 parameters)
    print("Running Sensitivity Analysis...")
    sensitivity_results = []
    for w in [3, 4, 5]:
        sec, stl = run_standalone_backtest(data, start_date="2021-06-08", end_date="2026-06-08", wait_days=w, use_ma_slope=False, use_trailing_stop=True, use_reinvest_div=False, use_atr_sizing=False)
        met = compute_metrics(sec, spy_df, f"Wait {w} Days")
        sensitivity_results.append({
            "WaitDays": w,
            "TotalReturn": met["TotalReturnPct"],
            "CAGR": met["CAGR"],
            "MaxDrawdown": met["MaxDrawdownPct"],
            "Sharpe": met["SharpeRatio"]
        })
    results["sensitivity"] = sensitivity_results
    
    os.makedirs("logs", exist_ok=True)
    with open("logs/backtest_results.json", "w") as f:
        json.dump(results, f, indent=2)
        
    print("Backtests completed successfully! Results written to logs/backtest_results.json")

if __name__ == "__main__":
    main()
