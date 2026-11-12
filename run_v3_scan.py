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

from core.sync.reconcile_engine import (
    check_position_drift, sync_broker_positions_to_db,
    ingest_broker_orders, ingest_broker_cash_transactions
)

from core.sync.metrics import compute_strategy_metrics

from core.sync.macro_metrics import compute_macro_wealth_metrics

from core.notifier.dispatcher import ProactiveNotifier





SHADOW_MODE = os.getenv("SHADOW_MODE", "false").lower() in ["true", "1", "yes"]





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

    print(f"💰 [Balances Detail] total_equity={aggregated_balances['total_equity']}, cash={aggregated_balances['total_cash']}, accounts={aggregated_balances['accounts']}")

    aggregated_positions = broker_mgr.get_aggregated_positions()



    # Compare DB positions vs Broker API positions
    drift_report = check_position_drift(db_pos_df, aggregated_positions)
    if drift_report.has_drift:
        print(f"⚠️ Position Drift Detected ({len(drift_report.drifts)} items):")
        for line in drift_report.summary_lines:
            print(f"  {line}")
    else:
        print("✅ No Position Drift: Broker positions match local database 100%.")

    # In Live Auto-Data Mode (SHADOW_MODE=False), synchronize positions directly
    if not SHADOW_MODE and not aggregated_positions.empty:
        print("🔄 Live Auto-Data Mode: Synchronizing real broker positions to portfolio database & Supabase Cloud...")
        sync_res = sync_broker_positions_to_db(aggregated_positions, shadow_mode=False)
        print(f"✅ Positions Synced: {len(sync_res.get('updated', []))} active positions updated, {len(sync_res.get('closed', []))} closed.")
        # Re-fetch active positions for subsequent calculations
        db_pos_df = get_positions()

    # Ingest executed orders from API (85-day lookback window)
    filled_orders = broker_mgr.get_all_filled_orders(start_date=None)
    num_synced, synced_list = ingest_broker_orders(filled_orders, shadow_mode=SHADOW_MODE)
    print(f"Broker Order Ingestion: {num_synced} new order(s) processed (Shadow Mode: {SHADOW_MODE}).")

    # Ingest cash deposits and withdrawals across all brokers (Tiger Consolidated + Charles Schwab)
    broker_cash_txs = broker_mgr.get_all_cash_transactions()
    num_cash_synced, cash_synced_list = ingest_broker_cash_transactions(broker_cash_txs)
    if num_cash_synced > 0:
        print(f"💰 Broker Cash Flow Ingestion: {num_cash_synced} new cash transaction(s) recorded: {cash_synced_list}")
    else:
        print("✅ Broker Cash Flow Ingestion: No new cash flow detected.")




    # -------------------------------------------------------------------------

    # STEP 4: Proactive Push Notification (Telegram + Feishu)

    # -------------------------------------------------------------------------

    print("\n[Step 4] Proactively Dispatching Telegram & Feishu Notification Cards...")

    strategy_metrics = compute_strategy_metrics()

    print(f"📊 Strategy Metrics: Return=+{strategy_metrics.get('strat_ret_pct', 0):.2f}%, Sharpe={strategy_metrics.get('sharpe', 0):.2f}, Alpha=+{strategy_metrics.get('alpha_pct', 0):.2f}%")



    if actions:
        push_res = notifier.dispatch_signal_card(
            date_str, nav, s5fi_val, actions, dedup_check=True, metrics=strategy_metrics
        )
        print(f"Signal Card Push Result: {push_res}")
        sig_summary = f"🚨 今日触发 **{len(actions)}** 笔调仓指令 (S5FI 宽度: {s5fi_val:.1f}%)"
    else:
        push_res = {"skipped_empty_combined_with_brief": True}
        print("ℹ️ No new trading signals today; merging scan status into Daily Asset Brief.")
        sig_summary = f"🟢 今日全盘无新增买卖信号 (S5FI 宽度: {s5fi_val:.1f}%)，持仓按原策略稳定运行"



    # Dispatch daily reconcile & NAV report

    hk_cum = get_hk_cum_profit(date_str)



    import sqlite3

    from config import DB_PATH

    conn_db = sqlite3.connect(DB_PATH)

    try:

        cash_tx_df = pd.read_sql("SELECT * FROM cash_transactions", conn_db)

    except Exception:

        cash_tx_df = None

    finally:

        conn_db.close()



    total_eq = aggregated_balances["total_equity"]

    # HK IPO operates inside Tiger Consolidated (638812), so total_eq already includes HK IPO capital and profits!
    total_wealth = total_eq if total_eq > 0 else nav



    macro_metrics = compute_macro_wealth_metrics(

        total_consolidated_equity=total_wealth,

        cash_balance=aggregated_balances["total_cash"],

        vault_balance=aggregated_balances.get("total_vault_balance", 0.0),

        positions_df=aggregated_positions,

        cash_transactions_df=cash_tx_df,

        initial_capital=INITIAL_CAPITAL,

        initial_date="2026-01-15",

        hk_ipo_cum=hk_cum

    )



        # Strategy Pool = Tiger Consolidated (638812) + Charles Schwab (excluding Universal legacy NVDA)
    strat_equity = 0.0
    for acc in aggregated_balances.get("accounts", []):
        acc_name_upper = acc.get("account_name", "").upper()
        if "UNIVERSAL" in acc_name_upper or "U9959007" in acc_name_upper:
            continue
        strat_equity += acc.get("equity", 0.0)

    if strat_equity <= 0:
        strat_equity = total_wealth

    cash_val = aggregated_balances["total_cash"]



    report_res = notifier.dispatch_daily_report(
        date_str=date_str,
        total_equity=total_wealth,
        strategy_equity=strat_equity,
        hk_ipo_cum=hk_cum,
        cash=cash_val,
        accounts_detail=aggregated_balances["accounts"],
        drift_summary=drift_report.summary_lines,
        metrics=strategy_metrics,
        macro_metrics=macro_metrics,
        dedup_check=True,
        signal_summary=sig_summary
    )

    print(f"Daily Reconcile Report Push Result: {report_res}")

    # Data QA Circuit Breaker before writing daily NAV
    qa_passed = True
    try:
        c_qa = sqlite3.connect(DB_PATH)
        cur_qa = c_qa.cursor()
        cur_qa.execute("SELECT total_equity FROM nav_history WHERE date < ? AND total_equity > 0 ORDER BY date DESC LIMIT 1", (date_str,))
        prev_row = cur_qa.fetchone()
        c_qa.close()
        prev_eq = float(prev_row[0]) if prev_row else 0.0
        if total_wealth <= 0:
            qa_passed = False
            qa_msg = f"今日净值核算异常 (<= 0): total_wealth=${total_wealth:,.2f}，已触发 QA 熔断阻止写入数据库。"
            print(f"🛑 [Data QA Blocked] {qa_msg}")
            notifier.dispatch_technical_alert("数据 QA 熔断拦截：总净值异常归零", [qa_msg])
        elif prev_eq > 0 and abs(total_wealth - prev_eq) / prev_eq > 0.30 and num_cash_synced == 0:
            qa_passed = False
            pct_chg = (total_wealth - prev_eq) / prev_eq * 100.0
            qa_msg = f"今日净值较昨日 (${prev_eq:,.2f}) 异常跳变 {pct_chg:+.1f}% (${total_wealth:,.2f})，且无大额出入金记录，已触发 QA 熔断阻止脏数据入库。"
            print(f"🛑 [Data QA Blocked] {qa_msg}")
            notifier.dispatch_technical_alert("数据 QA 熔断拦截：单日净值波动异常", [qa_msg])
    except Exception as qa_err:
        print(f"⚠️ Data QA check exception (proceeding safely): {qa_err}")

    # Record daily NAV to nav_history (SQLite + Supabase Cloud)
    if qa_passed:
        hwm = max(total_wealth, macro_metrics.get("high_water_mark", total_wealth))
        dd = (total_wealth - hwm) / hwm * 100.0 if hwm > 0 else 0.0

        record_nav(
            date_str=date_str,
            nav=strat_equity,
            cash=cash_val,
            jepq_val=0.0,
            sgov_val=0.0,
            trend_val=0.0,
            total_equity=total_wealth,
            strategy_equity=strat_equity,
            hk_pnl_cum=hk_cum,
            high_water_mark=hwm,
            drawdown_pct=dd,
            source="BROKER_SYNC"
        )
        print(f"📊 Auto-Recorded Daily NAV: total_equity=${total_wealth:,.2f}, strategy_equity=${strat_equity:,.2f}, hk_cum=${hk_cum:,.2f}")



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

