import os
import sys
import re
import json
import argparse
import requests
import datetime
import pandas as pd
import numpy as np

# ----------------------------------------------------------------------
# 1. S5FI Breadth Fetcher
# ----------------------------------------------------------------------
def fetch_s5fi_breadth(manual_s5fi=None):
    if manual_s5fi is not None:
        print(f"[S5FI] Using manually provided S5FI value: {manual_s5fi:.2f}%")
        return float(manual_s5fi), "Manual Input"

    # Attempt 1: Fetch from Barchart $S5FI overview
    try:
        url = "https://www.barchart.com/stocks/quotes/$S5FI/overview"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            matches = re.findall(r'"lastPrice":\s*"?([\d\.]+)"?', r.text)
            if matches:
                s5fi_val = float(matches[0])
                print(f"[S5FI] Fetched live S5FI from Barchart: {s5fi_val:.2f}%")
                return s5fi_val, "Barchart (Live)"
    except Exception as e:
        print(f"[S5FI Warning] Barchart fetch failed: {e}")

    # Attempt 2: Load latest from data/S5FI.csv
    s5fi_csv_path = os.path.join("data", "S5FI.csv")
    if os.path.exists(s5fi_csv_path):
        try:
            df_s5fi = pd.read_csv(s5fi_csv_path)
            last_row = df_s5fi.iloc[-1]
            s5fi_val = float(last_row["Close"])
            last_date = str(last_row["Date"])
            print(f"[S5FI] Fallback to data/S5FI.csv (Date: {last_date}): {s5fi_val:.2f}%")
            return s5fi_val, f"Local Cache ({last_date})"
        except Exception as e:
            print(f"[S5FI Warning] Failed reading local S5FI.csv: {e}")

    # Default fallback
    print("[S5FI Warning] Using default conservative fallback S5FI: 50.0%")
    return 50.0, "Fallback Default"

# ----------------------------------------------------------------------
# 2. Indicator Calculation: SuperTrend (10,3), EMA200, ATR(20)
# ----------------------------------------------------------------------
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

def fetch_market_indicators(tickers):
    import yfinance as yf
    print(f"[Market Data] Fetching batch price data for {tickers}...")
    
    # Download all in one batch for maximum speed
    df_raw = yf.download(tickers, period="1y", progress=False)
    
    data = {}
    for ticker in tickers:
        try:
            if isinstance(df_raw.columns, pd.MultiIndex):
                # Columns structure: ('Close', 'SPY') or ('SPY', 'Close')
                if ticker in df_raw.columns.levels[1]:
                    df = df_raw.xs(ticker, axis=1, level=1).copy()
                elif ticker in df_raw.columns.levels[0]:
                    df = df_raw.xs(ticker, axis=1, level=0).copy()
                else:
                    # Fallback single download
                    df = yf.download(ticker, period="1y", progress=False)
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = [c[0] for c in df.columns]
            else:
                df = df_raw.copy()

            df = df.dropna(subset=['Close'])

            # ATR(20)
            high, low, close = df['High'], df['Low'], df['Close']
            tr1 = high - low
            tr2 = (high - close.shift(1)).abs()
            tr3 = (low - close.shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df['ATR20'] = tr.ewm(span=20, adjust=False).mean()
            
            # EMA200
            df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
            
            # SuperTrend (10, 3)
            trend, ub, lb = calculate_supertrend(df, period=10, multiplier=3)
            df['ST_trend'] = trend
            df['ST_line'] = np.where(trend == 1, lb, ub)
            
            data[ticker] = df
        except Exception as e:
            print(f"[Market Data Error] Failed processing {ticker}: {e}")
            
    return data

# ----------------------------------------------------------------------
# 3. Decision Engine & Position Sizer
# ----------------------------------------------------------------------
def evaluate_strategy(version="v2.3", nav=100000, manual_s5fi=None):
    if version == "v2.3":
        title = "《L0+ / L1 / L2 多层趋势系统 · 每日执行卡 (v2.3 Ultimate)》"
        s5fi_l1_gate = 40.0
        s5fi_l2_gate = 60.0
        l2_leverage_ticker = "TQQQ"  # 3x
        position_mode = "ATR Dynamic Risk Sizing"
    elif version == "v2.24":
        title = "《L0+ / L1 / L2 多层趋势系统 · 每日执行卡 (v2.24 Low Volatility)》"
        s5fi_l1_gate = 45.0
        s5fi_l2_gate = 55.0
        l2_leverage_ticker = "QLD"   # 2x
        position_mode = "Fixed Position Sizing (10% / 8%)"
    else:
        title = f"《L0+ / L1 / L2 多层趋势系统 · 每日执行卡 ({version})》"
        s5fi_l1_gate = 40.0
        s5fi_l2_gate = 60.0
        l2_leverage_ticker = "TQQQ"
        position_mode = "ATR Dynamic Risk Sizing"

    s5fi_val, s5fi_source = fetch_s5fi_breadth(manual_s5fi)
    
    l1_buy_allowed = s5fi_val >= s5fi_l1_gate
    l2_buy_allowed = s5fi_val >= s5fi_l2_gate
    
    if s5fi_val < s5fi_l1_gate:
        s5fi_status_str = f"🔴 极度低迷 (<{s5fi_l1_gate:.0f}%) - 全面关停 L1 & L2 所有新买入！"
        s5fi_gate_level = "RED_LOCKDOWN"
    elif s5fi_val < s5fi_l2_gate:
        s5fi_status_str = f"🟡 警戒区域 ({s5fi_l1_gate:.0f}%-{s5fi_l2_gate:.0f}%) - L1 可买入，强制关停 L2 加速层买入！"
        s5fi_gate_level = "YELLOW_L2_FREEZE"
    else:
        s5fi_status_str = f"🟢 正常开阔 (≥{s5fi_l2_gate:.0f}%) - L1 & L2 买入通道全部打开！"
        s5fi_gate_level = "GREEN_ALL_CLEAR"

    tickers = ["SPY", "QQQ", "SOXX", "TQQQ", "QLD", "QUAL", "JEPQ"]
    market_data = fetch_market_indicators(tickers)
    
    if not market_data:
        raise RuntimeError("Failed to fetch market data.")

    latest_date = list(market_data.values())[0].index[-1].strftime("%Y-%m-%d")

    signals = []
    
    def calc_sizing(ticker, close, atr, layer):
        risk_budget = nav * 0.0025  # 0.25% NAV
        atr_pct = atr / close if close > 0 else 0.05
        
        if version == "v2.3":
            cap_limit_pct = 0.10 if layer == "L1" else 0.08
            target_dollars = min(risk_budget / atr_pct, nav * cap_limit_pct)
        else: # v2.24
            cap_limit_pct = 0.10 if layer == "L1" else 0.08
            target_dollars = nav * cap_limit_pct
            
        target_shares = int(np.floor(target_dollars / close))
        return target_dollars, target_shares, atr_pct

    # Evaluate L1 assets: SPY, QQQ, SOXX
    l1_assets = ["SPY", "QQQ", "SOXX"]
    l1_status_map = {}

    for t in l1_assets:
        df = market_data[t]
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        close = float(curr['Close'])
        ema200 = float(curr['EMA200'])
        st_curr = int(curr['ST_trend'])
        st_prev = int(prev['ST_trend'])
        st_line = float(curr['ST_line'])
        atr = float(curr['ATR20'])
        
        above_ema = close > ema200
        flipped_bull = (st_prev == -1 and st_curr == 1)
        flipped_bear = (st_prev == 1 and st_curr == -1)
        is_bull = (st_curr == 1)
        
        l1_status_map[t] = is_bull and above_ema
        
        target_dollars, target_shares, atr_pct = calc_sizing(t, close, atr, "L1")
        
        if flipped_bull and above_ema:
            if l1_buy_allowed:
                action = "BUY 🟢"
                reason = "SuperTrend 当日翻多 且 收盘 > EMA200 (S5FI通过)"
            else:
                action = "WAIT ⏸️"
                reason = f"触发技术买入，但被 S5FI 宏观关停 (<{s5fi_l1_gate:.0f}%)"
        elif is_bull and above_ema:
            action = "HOLD 🟢"
            reason = "维持多头趋势 (收盘 > EMA200 & SuperTrend多头)"
        elif flipped_bear:
            action = "SELL 🔴"
            reason = "SuperTrend 翻空，无条件平仓出场"
        else:
            action = "WAIT ⏸️"
            reason = "空头趋势或收盘价低于 EMA200"
            
        signals.append({
            "Layer": "L1 母仓",
            "Ticker": t,
            "Close": close,
            "EMA200": ema200,
            "EMA200_Status": "Above 🟢" if above_ema else "Below 🔴",
            "SuperTrend": "BULL 🟢" if is_bull else "BEAR 🔴",
            "ST_Line": st_line,
            "ATR20": atr,
            "ATR_Pct": atr_pct * 100,
            "Action": action,
            "Reason": reason,
            "TargetDollars": target_dollars,
            "TargetShares": target_shares
        })

    # Evaluate L2 assets
    l2_configs = [
        {"Ticker": "QQQ", "Parent": "SPY"},
        {"Ticker": "SOXX", "Parent": "QQQ"},
        {"Ticker": l2_leverage_ticker, "Parent": "QQQ"}
    ]
    
    for config in l2_configs:
        t = config["Ticker"]
        parent_t = config["Parent"]
        parent_alive = l1_status_map.get(parent_t, False)
        
        df = market_data[t]
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        close = float(curr['Close'])
        ema200 = float(curr['EMA200'])
        st_curr = int(curr['ST_trend'])
        st_prev = int(prev['ST_trend'])
        st_line = float(curr['ST_line'])
        atr = float(curr['ATR20'])
        
        flipped_bear = (st_prev == 1 and st_curr == -1)
        is_bull = (st_curr == 1)
        
        target_dollars, target_shares, atr_pct = calc_sizing(t, close, atr, "L2")
        
        if not parent_alive:
            if is_bull:
                action = "WAIT ⏸️"
                reason = f"母仓 {parent_t} 未建仓或已坍塌，L2 加速层禁止买入"
            else:
                action = "OFF ⚪"
                reason = f"母仓 {parent_t} 处于空头状态"
        else:
            if is_bull:
                if l2_buy_allowed:
                    action = "BUY / HOLD 🟢"
                    reason = f"母仓 {parent_t} 多头 且 自身 SuperTrend 多头 (S5FI通过)"
                else:
                    action = "HOLD / FREEZE 🟡"
                    reason = f"已持仓可继续持有，新买入被 S5FI 关停 (<{s5fi_l2_gate:.0f}%)"
            elif flipped_bear:
                action = "SELL 🔴"
                reason = "自身 SuperTrend 翻空，连带平仓离场"
            else:
                action = "WAIT ⏸️"
                reason = "SuperTrend 处于空头"

        signals.append({
            "Layer": f"L2 加速 ({parent_t})",
            "Ticker": t,
            "Close": close,
            "EMA200": ema200,
            "EMA200_Status": "Above 🟢" if close > ema200 else "Below 🔴",
            "SuperTrend": "BULL 🟢" if is_bull else "BEAR 🔴",
            "ST_Line": st_line,
            "ATR20": atr,
            "ATR_Pct": atr_pct * 100,
            "Action": action,
            "Reason": reason,
            "TargetDollars": target_dollars,
            "TargetShares": target_shares
        })

    l0_info = [
        {"Ticker": "JEPQ", "Role": "稳态 / 调拨缓冲池", "TargetPct": "48%", "Mode": "DRIP (分红自动买回 JEPQ)", "Close": float(market_data["JEPQ"].iloc[-1]["Close"])},
        {"Ticker": "QUAL", "Role": "长期成长效率", "TargetPct": "32%", "Mode": "DRIP (分红自动买回 QUAL)", "Close": float(market_data["QUAL"].iloc[-1]["Close"])},
    ]

    return {
        "Version": version,
        "Title": title,
        "Date": latest_date,
        "NAV": nav,
        "S5FI_Val": s5fi_val,
        "S5FI_Source": s5fi_source,
        "S5FI_Status": s5fi_status_str,
        "S5FI_GateLevel": s5fi_gate_level,
        "Signals": signals,
        "L0_Info": l0_info,
        "PositionMode": position_mode
    }

# ----------------------------------------------------------------------
# 4. Generate Reports (Markdown Artifact & Terminal Display)
# ----------------------------------------------------------------------
def render_markdown_card(res):
    md = f"""# {res['Title']}

> **生成时间**：{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} (行情基准日: `{res['Date']}`)  
> **账户基准资金 (NAV)**：`${res['NAV']:,.2f}` | **控仓模式**：`{res['PositionMode']}`

---

## 🛡️ 第一步：S5FI 宏观市场宽度总闸门

| 指标 | 当前数值 | 数据来源 | 判定状态 |
| :--- | :---: | :---: | :--- |
| **S5FI (S&P 500 > 50MA %)** | **`{res['S5FI_Val']:.2f}%`** | {res['S5FI_Source']} | **{res['S5FI_Status']}** |

> 💡 **闸门规则**：
> * **S5FI < 40%**：全盘关停 L1 & L2 所有新买入建仓。
> * **S5FI < 60%**：关停 L2 所有加速层新买入建仓（L1 不受限）。
> * *注：S5FI 仅约束“入场建仓”，不作为已持仓位离场依据。*

---

## 🎯 第二步：L1 / L2 趋势层每日进出场信号表

| 层级 | 标的 | 收盘价 ($) | EMA200 状态 | SuperTrend 信号 | 止损/翻转位 ($) | ATR(20)% | **每日建议动作** | 建议建仓金额 | **目标股数** | 触发逻辑说明 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
"""

    for s in res['Signals']:
        md += f"| **{s['Layer']}** | **`{s['Ticker']}`** | ${s['Close']:.2f} | {s['EMA200_Status']} | {s['SuperTrend']} | ${s['ST_Line']:.2f} | {s['ATR_Pct']:.2f}% | **{s['Action']}** | ${s['TargetDollars']:,.0f} | **`{s['TargetShares']} 股`** | {s['Reason']} |\n"

    md += f"""
---

## 🧱 第三步：L0+ 缓冲底仓配置 (DRIP 自动复利)

| 标的 | 角色与功能 | 目标资金占比 | 基础估算金额 | 最新价格 | 分红处理模式 |
| :--- | :--- | :---: | :---: | :---: | :--- |
"""
    for l0 in res['L0_Info']:
        target_amt = res['NAV'] * (0.48 if l0['Ticker'] == 'JEPQ' else 0.32)
        md += f"| **`{l0['Ticker']}`** | {l0['Role']} | **{l0['TargetPct']}** | ${target_amt:,.0f} | ${l0['Close']:.2f} | **{l0['Mode']}** |\n"

    md += f"""
---

## ⚡ 资金调拨与明日开盘执行指令

1. **若今日触发 `BUY` 信号**：
   * 下一交易日美股开盘时，以**市价单 (Market Order)** 直接买入对应目标股数。
   * 若现金不足，自动从 **JEPQ** 中赎回差额资金（单次上限 $10,000 / 10% NAV）。
2. **若今日触发 `SELL` 信号**：
   * 下一交易日美股开盘时，以**市价单 (Market Order)** 一次性全额卖出平仓。
   * 卖出顺序：**先卖 L2 加速层，再卖 L1 母仓**。
   * 卖出回笼资金若使现金超过 **20% NAV**，超出部分一次性申购 **JEPQ** 进行底仓再平衡。
3. **若无买卖指令 (`HOLD` / `WAIT`)**：
   * 保持现有仓位，无脑执行，无需人工介入。
"""
    return md

def main():
    parser = argparse.ArgumentParser(description="Auto Daily Trading Card Generator")
    parser.add_argument("--version", type=str, default="v2.3", choices=["v2.3", "v2.24"], help="Strategy version")
    parser.add_argument("--nav", type=float, default=100000.0, help="Account NAV in USD")
    parser.add_argument("--s5fi", type=float, default=None, help="Manual S5FI percentage override")
    args = parser.parse_args()

    print(f"=== Multi-Layer Trend Strategy Daily Execution Card Generator ===")
    print(f"Strategy Version: {args.version} | Account NAV: ${args.nav:,.2f}")
    
    res = evaluate_strategy(version=args.version, nav=args.nav, manual_s5fi=args.s5fi)
    md_content = render_markdown_card(res)
    
    # Save to workspace root
    out_file = "daily_execution_card.md"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"\n[Success] Generated execution card at workspace file: {out_file}")

    # Also save to artifacts folder
    artifact_dir = r"C:\Users\Jason Zhang\.gemini\antigravity\brain\bee7e578-cf43-40a0-bc98-062d8e1fc21c"
    if os.path.exists(artifact_dir):
        art_file = os.path.join(artifact_dir, "daily_execution_card.md")
        with open(art_file, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"[Success] Copied execution card to artifact path: {art_file}")

    print("\n" + "="*75)
    print(f"               DAILY RECOMMENDATION SUMMARY ({res['Date']})")
    print("="*75)
    print(f"S5FI Breadth: {res['S5FI_Val']:.2f}% ({res['S5FI_Source']}) -> Status: {res['S5FI_Status']}")
    print("-" * 75)
    print(f"{'Layer':<14} {'Ticker':<8} {'Close':<8} {'SuperTrend':<10} {'Action':<15} {'Target Shares':<12}")
    print("-" * 75)
    for s in res['Signals']:
        print(f"{s['Layer']:<14} {s['Ticker']:<8} ${s['Close']:<7.2f} {s['SuperTrend']:<10} {s['Action']:<15} {s['TargetShares']} shares (${s['TargetDollars']:,.0f})")
    print("="*75)

if __name__ == "__main__":
    main()
