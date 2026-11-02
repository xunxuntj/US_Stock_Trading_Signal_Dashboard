"""
v3.0 Main Quantitative Scan & Active Dispatcher Pipeline (run_v3_scan.py)
Orchestrates:
1. Technical Data Sanity & Freshness Guard
2. v2.29 Strategy Signal Generation with Exhaustive Exit Scans (Zero Blind Spot)
3. Multi-Broker (Tiger + Schwab + Futu) Position Reconcile & Drift Detection
4. Proactive Telegram & Feishu Notification Cards
5. Zero-Impact Shadow Mode Isolation
"""

import os
import sys
import datetime
import pandas as pd
from typing import Dict, List, Any

# Ensure project root in python path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import (
    INITIAL_CAPITAL, JEPQ_TARGET_PCT, SGOV_TARGET_PCT, DATA_DIR,
    EQUITY_L1_TICKERS, EQUITY_L2_WHITELIST, NON_EQUITY_TICKERS,
    S5FI_L1_THRESHOLD, S5FI_L2_THRESHOLD, MAX_TREND_CAPACITY_PCT,
    SINGLE_POSITION_CAP_PCT, L2_POSITION_CAP_PCT
)
from database import (
    init_db, get_positions, get_hk_ipo_history, record_nav
)
import backtest_engine as be

# v3.0 Core Modules
from core.sanity.data_guard import check_universe_data_health, is_us_trading_day, is_us_market_open_now
from core.sanity.signal_guard import exhaustive_scan_trend_exits, get_canonical_layer
from core.broker.manager import MultiBrokerManager
from core.sync.reconcile_engine import check_position_drift, ingest_broker_orders
from core.notifier.dispatcher import ProactiveNotifier


SHADOW_MODE = os.getenv("SHADOW_MODE", "true").lower() in ["true", "1", "yes"]


def get_hk_cum_profit(date_str: str) -> float:
    """Fetch latest HK IPO cumulative profit."""
    try:
        df_hk = get_hk_ipo_history()
        if not df_hk.empty:
            ym = date_str[:7]
            valid = df_hk[df_hk['date'].str[:7] <= ym].sort_values('date', ascending=True)
            if not valid.empty and pd.notnull(valid.iloc[-1]['cum_profit']):
                return float(valid.iloc[-1]['cum_profit'])
    except Exception:
        pass
    return 8866.16  # Fallback baseline


def run_pipeline() -> Dict[str, Any]:
    print("=" * 70)
    print("🚀 RUNNING QUANTITATIVE TRADING PIPELINE v3.0")
    print(f"🕒 Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🛡️ Mode: {'[SHADOW MODE (影子运行 - 只比对不破坏实盘)]' if SHADOW_MODE else '[LIVE AUTO-EXECUTION]'}")
    print("=" * 70)

    notifier = ProactiveNotifier()
    today = datetime.date.today()
    date_str = today.strftime("%Y-%m-%d")

    # -------------------------------------------------------------------------
    # STEP 1: Technical Data Sanity & Freshness Guard
    # -------------------------------------------------------------------------
    print("\n[Step 1] Loading Market Data and Executing Technical Sanity Guard...")
    data = be.prepare_data(DATA_DIR)
    
    required_universe = list(set(EQUITY_L1_TICKERS + ["QLD"] + NON_EQUITY_TICKERS + ["JEPQ", "SGOV", "SPY", "QQQ"]))
    data_report = check_universe_data_health(data, required_universe)

    if not data_report.is_valid:
        print(f"❌ Critical Data Sanity Issues Found: {data_report.errors}")
        notifier.dispatch_technical_alert("市场行情数据异常拦截", data_report.errors)
        return {"status": "ERROR", "reason": "Data sanity check failed", "errors": data_report.errors}

    if data_report.warnings:
        print(f"⚠️ Data Sanity Warnings: {data_report.warnings}")

    spy_df = data["SPY"]
    market_open_now = is_us_market_open_now()
    latest_date = spy_df.index[-1]
    today_et_str = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=4)).strftime('%Y-%m-%d')

    # Session Guard: strictly adhere to v2.29 rule that signals require completed daily candle.
    # If triggered during active trading hours, exclude the fluctuating unfinished intraday candle.
    if market_open_now and str(latest_date)[:10] == today_et_str and len(spy_df) >= 2:
        print(f"⚠️ [Session Guard] US market is currently OPEN (Intraday: {today_et_str}).")
        print(f"   Excluding unclosed candle to prevent premature signals and noise.")
        print(f"   Signals strictly evaluated on last completed close: {spy_df.index[-2]}")
        latest_date = spy_df.index[-2]
        prev_date = spy_df.index[-3] if len(spy_df) >= 3 else latest_date
    else:
        prev_date = spy_df.index[-2] if len(spy_df) >= 2 else latest_date

    # S5FI Market Breadth
    if "S5FI" in data and not data["S5FI"].empty:
        if latest_date in data["S5FI"].index:
            s5fi_val = float(data["S5FI"].loc[latest_date, "Close"])
        else:
            s5fi_val = float(data["S5FI"]["Close"].iloc[-1])
    else:
        s5fi_val = 50.0

    current_prices = {t: data[t].loc[latest_date, 'Close'] for t in data if latest_date in data[t].index}

    # -------------------------------------------------------------------------
    # STEP 2: Strategy Signal Generation (Zero Blind Spot Exit & Precise Entry)
    # -------------------------------------------------------------------------
    print("\n[Step 2] Scanning Active Positions & Generating Strategy Signals...")
    db_pos_df = get_positions()

    # 2.1 Exhaustive Exit Scans (Zero Blind Spot: eliminates SOXX 'TREND' bug)
    exit_actions, exit_warnings = exhaustive_scan_trend_exits(db_pos_df, data, latest_date, date_str)
    if exit_warnings:
        print(f"⚠️ Exit Scan Warnings: {exit_warnings}")

    actions: List[Dict[str, Any]] = list(exit_actions)

    # Calculate Current NAV & Active Trend Allocation
    current_pos_map = {row['ticker']: row for _, row in db_pos_df.iterrows()} if not db_pos_df.empty else {}
    trend_val = sum(
        pos['shares'] * current_prices[pos['ticker']]
        for t, pos in current_pos_map.items()
        if pos['layer'] not in ['L0', 'SGOV', 'LEGACY'] and pos['ticker'] in current_prices
    )
    jepq_val = current_pos_map['JEPQ']['shares'] * current_prices['JEPQ'] if 'JEPQ' in current_pos_map and 'JEPQ' in current_prices else 0.0
    sgov_val = current_pos_map['SGOV']['shares'] * current_prices['SGOV'] if 'SGOV' in current_pos_map and 'SGOV' in current_prices else 0.0
    nav = trend_val + jepq_val + sgov_val
    if nav <= 0:
        nav = INITIAL_CAPITAL

    # 2.2 Entry Checks strictly adhering to existing v2.29 Strategy Card
    # L1 Equities
    for t in EQUITY_L1_TICKERS:
        if t in current_pos_map or any(a['ticker'] == t for a in actions):
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
                        "shares": round(target_val / float(row['Close']), 2),
                        "price": float(row['Close']),
                        "reason": f"L1 Entry ({t}): Close > EMA200, ST flipped Bullish (+1), S5FI ({s5fi_val:.1f}%) >= 45%",
                        "layer": "L1"
                    })
                    trend_val += target_val

    # L2 Equities (QLD)
    for l1_parent, children in EQUITY_L2_WHITELIST.items():
        if l1_parent not in current_pos_map:
            continue
        if data[l1_parent].loc[latest_date, 'ST_trend'] != 1:
            continue
        for child_t in children:
            if child_t in current_pos_map or any(a['ticker'] == child_t for a in actions):
                continue
            df_c = data[child_t]
            if latest_date not in df_c.index or prev_date not in df_c.index:
                continue
            r_c = df_c.loc[latest_date]
            if r_c['Close'] > r_c['EMA200'] and r_c['ST_trend'] == 1 and df_c.loc[prev_date, 'ST_trend'] == -1:
                if s5fi_val >= S5FI_L2_THRESHOLD:
                    target_val = nav * L2_POSITION_CAP_PCT
                    if trend_val + target_val <= nav * MAX_TREND_CAPACITY_PCT:
                        actions.append({
                            "date": date_str, "ticker": child_t, "action": "BUY",
                            "target_val": target_val,
                            "shares": round(target_val / float(r_c['Close']), 2),
                            "price": float(r_c['Close']),
                            "reason": f"L2 Entry ({child_t}): Close > EMA200, ST flipped Bullish (+1), S5FI ({s5fi_val:.1f}%) >= 55%",
                            "layer": "L2"
                        })
                        trend_val += target_val

    # Non-Equity Trend Layer (GLD, TLT, DBC, BITO) - Exempt from S5FI
    for t in NON_EQUITY_TICKERS:
        if t in current_pos_map or any(a['ticker'] == t for a in actions):
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
                    "shares": round(target_val / float(row['Close']), 2),
                    "price": float(row['Close']),
                    "reason": f"Non-Equity Entry ({t}): Close > EMA200, ST flipped Bullish (+1) (S5FI exempt)",
                    "layer": "Non-Equity"
                })
                trend_val += target_val

    print(f"Generated {len(actions)} signal(s).")

    # -------------------------------------------------------------------------
    # STEP 3: Multi-Broker Reconciliation & Drift Detection
    # -------------------------------------------------------------------------
    print("\n[Step 3] Multi-Broker API Ingestion & Reconcile (Tiger + Schwab)...")
    broker_mgr = MultiBrokerManager(use_mock_if_no_keys=True)
    aggregated_balances = broker_mgr.get_aggregated_balances()
    aggregated_positions = broker_mgr.get_aggregated_positions()

    # Compare DB positions vs Broker API positions
    drift_report = check_position_drift(db_pos_df, aggregated_positions)
    if drift_report.has_drift:
        print(f"⚠️ Position Drift Detected ({len(drift_report.drifts)} items):")
        for line in drift_report.summary_lines:
            print(f"  {line}")
    else:
        print("✅ No Position Drift: Broker positions match local database 100%.")

    # Ingest executed orders from API
    filled_orders = broker_mgr.get_all_filled_orders(start_date=date_str)
    num_synced, synced_list = ingest_broker_orders(filled_orders, shadow_mode=SHADOW_MODE)
    print(f"Broker Order Ingestion: {num_synced} new order(s) processed (Shadow Mode: {SHADOW_MODE}).")

    # -------------------------------------------------------------------------
    # STEP 4: Proactive Push Notification (Telegram + Feishu)
    # -------------------------------------------------------------------------
    print("\n[Step 4] Proactively Dispatching Telegram & Feishu Notification Cards...")
    push_res = notifier.dispatch_signal_card(date_str, nav, s5fi_val, actions, dedup_check=True)
    print(f"Signal Card Push Result: {push_res}")

    # Dispatch daily reconcile & NAV report
    hk_cum = get_hk_cum_profit(date_str)
    total_equity = aggregated_balances["total_equity"] + hk_cum
    strat_equity = aggregated_balances["total_equity"]
    cash_val = aggregated_balances["total_cash"]

    report_res = notifier.dispatch_daily_report(
        date_str=date_str,
        total_equity=total_equity,
        strategy_equity=strat_equity,
        hk_ipo_cum=hk_cum,
        cash=cash_val,
        accounts_detail=aggregated_balances["accounts"],
        drift_summary=drift_report.summary_lines
    )
    print(f"Daily Reconcile Report Push Result: {report_res}")

    print("\n" + "=" * 70)
    print("✅ QUANTITATIVE TRADING PIPELINE v3.0 EXECUTION COMPLETED")
    print("=" * 70)

    return {
        "status": "SUCCESS",
        "date": date_str,
        "nav": nav,
        "s5fi": s5fi_val,
        "actions_count": len(actions),
        "actions": actions,
        "has_drift": drift_report.has_drift,
        "push_result": push_res
    }


if __name__ == "__main__":
    init_db()
    run_pipeline()
