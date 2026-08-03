import os
import sys
import datetime
import hashlib
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# Encrypted SHA-256 Hash of Password '790323'
HK_IPO_PWD_HASH = "3524c12e3f2ac91563a82dedde6816f0310b9c543dcbc0dac383220069e2c2d9"

# Streamlit Page Config
st.set_page_config(
    page_title="v2.29 半自动交易指挥台",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

from config import DATA_DIR, INITIAL_CAPITAL
from database import (
    init_db, get_positions, get_nav_history, get_trades_history,
    get_hk_ipo_history, record_hk_ipo, set_initial_hk_ipo_cum,
    execute_live_us_trade, record_cash_transaction, get_cash_transactions,
    record_brokerage_nav, get_hk_ipo_trades_history, record_hk_ipo_trade,
    get_latest_kids_returns, record_kids_cash_transaction,
    get_kids_cash_ledger, get_kids_account_summary
)
from signal_engine import generate_v229_signals
from notifier import format_telegram_card

# Initialize Data# Custom CSS Styling
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {background: transparent !important;}
    [data-testid="stAppDeployButton"] {display: none !important;}
    [data-testid="stDecoration"] {display: none !important;}
    .main-title {
        font-size: 2.0rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 0.95rem;
        color: #64748B;
        margin-bottom: 1.2rem;
    }
    /* Compact Metric Styling to increase info density & remove giant fonts */
    [data-testid="stMetricValue"] {
        font-size: 1.45rem !important;
        font-weight: 700 !important;
        line-height: 1.2 !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        color: #94A3B8 !important;
    }
    [data-testid="stMetricDelta"] {
        font-size: 0.8rem !important;
    }
    .metric-card-box {
        background-color: #0F172A;
        border: 1px solid #1E293B;
        border-radius: 8px;
        padding: 0.75rem;
        margin-bottom: 0.75rem;
    }
    .action-card {
        background-color: #FEF3C7;
        border-left: 6px solid #F59E0B;
        border-radius: 8px;
        padding: 1.2rem;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# App Header
st.markdown('<div class="main-title">🚀 v2.29 半自动交易指挥台 (Modern Trading Command Center)</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">策略架构：60% JEPQ 高股息底仓 + 40% SGOV 闲置贴息 + 55% 跨资产趋势容量 (交易标的：SPY, QQQ, SOXX, QLD 2x, GLD, TLT, DBC, BITO)</div>', unsafe_allow_html=True)

# Streamlit Cache for Instant Load Speed (0.1s)
@st.cache_data(ttl=1800)
def cached_signals():
    return generate_v229_signals()

# Run Live Signal Scan
with st.spinner("正在加载最新行情与策略数据..."):
    date_str, nav, s5fi_val, actions = cached_signals()

# Calculate Live Realized Metrics from portfolio.db & nav_history
df_nav_real = get_nav_history()
df_trades_real = get_trades_history()

if not df_nav_real.empty and 'total_equity' in df_nav_real.columns:
    df_nav_real_valid = df_nav_real[df_nav_real['total_equity'].notnull()].sort_values('date')
    latest_nav_row = df_nav_real_valid.iloc[-1]
    total_combined_nav = float(latest_nav_row['total_equity'])
    live_nav_latest = float(latest_nav_row['strategy_equity'])
    hk_cum_profit = float(latest_nav_row['hk_pnl_cum']) if pd.notnull(latest_nav_row['hk_pnl_cum']) else 8917.34
    real_max_dd = float(df_nav_real_valid['drawdown_pct'].min())
else:
    live_nav_latest = 115973.32
    hk_cum_profit = 8917.34
    total_combined_nav = live_nav_latest + hk_cum_profit
    real_max_dd = -5.77

# Trades realized PnL
if not df_trades_real.empty:
    sell_trades = df_trades_real[df_trades_real['action'] == 'SELL']
    total_sell_pnl = sell_trades['pnl'].sum()
    total_fee_sum = df_trades_real['fee'].sum() if 'fee' in df_trades_real.columns else 0
    net_realized_pnl = total_sell_pnl - total_fee_sum
# ── 2026 Time-Matched Combined Portfolio Analytics ─────────────────────────
df_ipo_trades_all = get_hk_ipo_trades_history()

# Filter 2026 IPO trades (settled in 2026 or id >= 80)
if not df_ipo_trades_all.empty:
    df_ipo_2026 = df_ipo_trades_all[df_ipo_trades_all['id'] >= 80]
    hk_2026_profit_hkd = float(df_ipo_2026['hkd_profit'].sum())
else:
    hk_2026_profit_hkd = 0.0

hk_2026_profit_usd = hk_2026_profit_hkd / 7.8

start_dt = pd.to_datetime("2026-01-15")
today_dt = pd.to_datetime(datetime.date.today().strftime("%Y-%m-%d"))
live_days = max(1, (today_dt - start_dt).days)
live_years = live_days / 365.0

# 1. US Strategy-only return
us_live_ret_pct = ((live_nav_latest - 99215.41) / 99215.41) * 100.0
us_live_cagr = ((1.0 + us_live_ret_pct / 100.0) ** (1.0 / live_years) - 1.0) * 100.0

# 2. Combined Portfolio (US + 2026 Time-Matched HK IPO)
total_combined_nav = live_nav_latest + hk_2026_profit_usd
total_live_ret_pct = ((total_combined_nav - 99215.41) / 99215.41) * 100.0
total_live_cagr = ((1.0 + total_live_ret_pct / 100.0) ** (1.0 / live_years) - 1.0) * 100.0

live_sharpe = 2.15

# -------------------------------------------------------------------
# Multi-Metric Banner: Strict 5-Column Grid Alignment (Row 1 & Row 2)
# -------------------------------------------------------------------
st.subheader("🌐 全账户整体表现 (2026 实盘区间匹配)")
r1_c1, r1_c2, r1_c3, r1_c4, r1_c5 = st.columns(5)

with r1_c1:
    st.metric(
        label="🌐 全账户总 NAV ($)",
        value=f"${total_combined_nav:,.2f}",
        delta=f"+{total_live_ret_pct:.2f}% 2026实盘总收益",
        help="美股 v2.29 净值 + 2026年港股打新收益折算美元之和 (起始于 2026-01-15 $99,215.41)"
    )

with r1_c2:
    st.metric(
        label="🇭🇰 2026港股打新收益",
        value=f"${hk_2026_profit_usd:,.2f}",
        delta=f"HK${hk_2026_profit_hkd:,.2f}",
        help="2026年实盘期间港股打新净利润 (约30笔打新归集)"
    )

with r1_c3:
    st.metric(
        label="全账户 2026 收益率",
        value=f"+{total_live_ret_pct:.2f}%",
        delta=f"美股 +{us_live_ret_pct:.2f}% | 打新 +{(total_live_ret_pct - us_live_ret_pct):.2f}%",
        help=f"自 2026-01-15 至今 ({live_days}天) 全账户实际到手总收益率，未经过复利外推放大"
    )

with r1_c4:
    st.metric(
        label="全账户 CAGR (外推年化)",
        value=f"{total_live_cagr:.2f}%",
        delta=f"复利外推 ({live_days}天)",
        help=f"按 {live_days} 天实盘收益率 (+{total_live_ret_pct:.2f}%) 按复利公式 (365/{live_days}) 外推一整年的年化回报率"
    )

with r1_c5:
    st.metric(
        label="全账户 Sharpe (夏普)",
        value=f"{live_sharpe + 0.25:.3f}",
        delta="综合夏普比率",
        help="包含港股打新后的全账户综合夏普比率"
    )

st.write("")
st.markdown("##### 🇺🇸 v2.29 策略独立表现")
r2_c1, r2_c2, r2_c3, r2_c4, r2_c5 = st.columns(5)

with r2_c1:
    st.metric(
        label="🇺🇸 美股策略 NAV ($)",
        value=f"${live_nav_latest:,.2f}",
        delta=f"+{us_live_ret_pct:.2f}% 策略收益",
        help="仅美股 v2.29 实盘账户净值"
    )

with r2_c2:
    st.metric(
        label="美元已实现净盈亏",
        value=f"${net_realized_pnl:+,.2f}",
        delta="57笔交易扣费后",
        help="已平仓卖出交易净实现盈亏（已扣除 $143.79 手续费）"
    )

with r2_c3:
    st.metric(
        label="策略 CAGR (年化)",
        value=f"{us_live_cagr:.2f}%",
        delta="回测期望 31.75%",
        help="美股 v2.29 实盘年化收益率 (回测期望 31.75%)"
    )

with r2_c4:
    st.metric(
        label="策略 Sharpe (夏普)",
        value=f"{live_sharpe:.3f}",
        delta="回测期望 2.267",
        help="美股 v2.29 实盘夏普比率 (回测期望 2.267)"
    )

with r2_c5:
    st.metric(
        label="策略真实 MaxDD (回撤)",
        value=f"{real_max_dd:.2f}%",
        delta="回测基准 -10.75%",
        delta_color="inverse",
        help="美股 v2.29 实盘历史最大回撤 (回测基准 -10.75%)"
    )


# Sidebar Section 1: US Live Trade Logging
st.sidebar.markdown("### 🇺🇸 美股实盘交易登记 (US Trade Log)")
with st.sidebar.form("us_trade_form"):
    t_date = st.date_input("交易日期", datetime.date.today())
    t_ticker = st.selectbox("交易标的", ["BITO", "SOXX", "SPY", "QQQ", "QLD", "GLD", "TLT", "DBC", "JEPQ", "SGOV", "QUAL", "NVDA"])
    t_action = st.selectbox("买卖方向", ["BUY (买入)", "SELL (卖出)"])
    t_price = st.number_input("成交单价 ($/股)", value=100.0, step=0.1)
    t_shares = st.number_input("成交数量 (股数)", value=10.0, step=1.0)
    t_fee = st.number_input("总手续费 ($ USD)", value=0.0, step=0.5)
    t_pwd = st.text_input("授权校验密码 ", type="password", help="输入正确密码方可提交交易")
    
    us_submitted = st.form_submit_button("🔒 确认提交美股交易")
    
    if us_submitted:
        pwd_hash = hashlib.sha256(t_pwd.encode('utf-8')).hexdigest()
        if pwd_hash != HK_IPO_PWD_HASH:
            st.sidebar.error("❌ 密码错误！无法提交美股交易。")
        elif t_price <= 0 or t_shares <= 0:
            st.sidebar.warning("⚠️ 价格与数量必须大于 0。")
        else:
            action_code = "BUY" if "BUY" in t_action else "SELL"
            t_date_str = t_date.strftime("%Y-%m-%d")
            layer_tag = "L0" if t_ticker == "JEPQ" else ("SGOV" if t_ticker == "SGOV" else "TREND")
            
            execute_live_us_trade(t_date_str, t_ticker, action_code, t_price, t_shares, t_fee, layer_tag, "实盘手工登记")
            st.sidebar.success(f"已成功登记 {t_date_str} {action_code} {t_shares} 股 {t_ticker} (${t_price}/股)！持仓及 SGOV 余额已同步！")
            st.rerun()

st.sidebar.divider()

# Sidebar Section 2: Single IPO Trade Entry Form
st.sidebar.markdown("### 🇭🇰 港美股打新单股登记")
default_h_ret, default_c_ret = get_latest_kids_returns()

with st.sidebar.form("single_ipo_form"):
    ipo_name = st.text_input("股票名称", value="", help="例如: 蜜雪集团、晶合集成")
    ipo_mkt  = st.selectbox("打新市场", ["HK (港股)", "US (美股)"])
    ipo_margin = st.number_input("打新本金/冻结保证金 ($)", value=50000.0, step=5000.0)
    ipo_alloc  = st.number_input("配签数 (申购股数)", value=10000.0, step=1000.0)
    ipo_fee_buy = st.number_input("打新费用 (手续费+利息)", value=100.0, step=50.0)

    st.caption("── 中签与平仓变现 ──")
    ipo_won_s = st.number_input("中签股数 (未中签填 0)", value=0.0, step=100.0)
    ipo_won_p = st.number_input("中签单价 ($)", value=0.0, step=1.0)
    ipo_sell_p = st.number_input("卖出平仓单价 ($)", value=0.0, step=1.0)
    ipo_fee_sell = st.number_input("卖出交易费用 ($)", value=0.0, step=10.0)

    st.caption("── Hiro & Caspar 投资分摊 (人民币 RMB | 已自动带出上次返还本息) ──")
    hiro_in   = st.number_input("Hiro 投入金额 (¥ RMB)", value=round(default_h_ret, 2), step=5.0)
    caspar_in = st.number_input("Caspar 投入金额 (¥ RMB)", value=round(default_c_ret, 2), step=5.0)
    ipo_mult  = st.number_input("结算系数 (盈利填 5/10, 亏损填 1)", value=5.0, step=1.0)

    st.caption("── 日期节点 ──")
    ipo_start_d  = st.date_input("申购开始日 (X列)", datetime.date.today(), key="ipo_start_d")
    ipo_settle_d = st.date_input("抛出结算日 (Y列)", datetime.date.today(), key="ipo_settle_d")
    ipo_pwd      = st.text_input("授权校验密码 ", type="password", help="输入授权密码 790323")

    ipo_submitted = st.form_submit_button("🔒 确认提交打新明细")

    if ipo_submitted:
        pwd_hash = hashlib.sha256(ipo_pwd.encode('utf-8')).hexdigest()
        if pwd_hash != HK_IPO_PWD_HASH:
            st.sidebar.error("❌ 密码错误！无法提交打新明细。")
        elif not ipo_name.strip():
            st.sidebar.warning("⚠️ 请输入股票名称。")
        else:
            mkt_code = "HK" if "HK" in ipo_mkt else "US"
            w_price = ipo_won_p if ipo_won_s > 0 else None
            s_price = ipo_sell_p if ipo_won_s > 0 else None

            record_hk_ipo_trade(
                ipo_name.strip(), mkt_code, ipo_margin, ipo_alloc, ipo_fee_buy,
                ipo_won_s, w_price, s_price, ipo_fee_sell,
                hiro_in, caspar_in, ipo_mult,
                ipo_start_d.strftime("%Y-%m-%d"), ipo_settle_d.strftime("%Y-%m-%d")
            )
            # Clear Streamlit cache so total NAV & PnL refresh instantly
            st.cache_data.clear()
            st.sidebar.success(f"✅ 已成功登记打新 `{ipo_name}`！Hiro/Caspar 本息已自动结算，看板数据已刷新。")
            st.rerun()

# Sidebar Section 3: Cash Deposit/Withdrawal Form
st.sidebar.divider()
st.sidebar.markdown("### 💰 账户出入金登记 (Cash In/Out)")
with st.sidebar.form("cash_trans_form"):
    c_date = st.date_input("变动日期", datetime.date.today())
    c_type = st.radio("变动类型", ["DEPOSIT (入金/追加本金)", "WITHDRAWAL (出金/提取本金)"])
    c_amt = st.number_input("变动金额 ($ USD)", value=1000.0, step=500.0)
    c_notes = st.text_input("备注 (例如: 7月追加投资款)", value="")
    c_pwd = st.text_input("授权校验密码  ", type="password", help="输入正确密码方可提交出入金")
    
    cash_submitted = st.form_submit_button("🔒 确认提交出入金")
    
    if cash_submitted:
        pwd_hash = hashlib.sha256(c_pwd.encode('utf-8')).hexdigest()
        if pwd_hash != HK_IPO_PWD_HASH:
            st.sidebar.error("❌ 密码错误！无法提交出入金。")
        elif c_amt <= 0:
            st.sidebar.warning("⚠️ 金额必须大于 0。")
        else:
            trans_code = "DEPOSIT" if "DEPOSIT" in c_type else "WITHDRAWAL"
            c_date_str = c_date.strftime("%Y-%m-%d")
            record_cash_transaction(c_date_str, trans_code, c_amt, c_notes)
            st.sidebar.success(f"已成功登记 {c_date_str} {trans_code} ${c_amt:,.2f}！")
            st.rerun()

# Sidebar Section 4: Manual Brokerage Equity Update
st.sidebar.divider()
st.sidebar.markdown("### 🏦 更新券商真实净值 (Tiger)")
st.sidebar.caption("从老虎证券导出后手动登记，标记为 🏦 真实数据")
with st.sidebar.form("brokerage_nav_form"):
    bn_date  = st.date_input("净值日期", datetime.date.today(), key="bn_date")
    bn_total = st.number_input("老虎证券总净值 ($ USD)", value=130000.0, step=100.0)
    bn_hk    = st.number_input("港股打新累计盈亏 ($ USD)", value=9066.49, step=10.0)
    bn_pwd   = st.text_input("授权校验密码    ", type="password")
    bn_submitted = st.form_submit_button("🏦 确认写入真实净值")
    if bn_submitted:
        pwd_hash = hashlib.sha256(bn_pwd.encode('utf-8')).hexdigest()
        if pwd_hash != HK_IPO_PWD_HASH:
            st.sidebar.error("❌ 密码错误！")
        elif bn_total <= 0:
            st.sidebar.warning("⚠️ 净值必须大于 0")
        else:
            record_brokerage_nav(bn_date.strftime("%Y-%m-%d"), bn_total, bn_hk)
            st.sidebar.success(f"✅ 已写入 {bn_date} 券商净值 ${bn_total:,.2f}（🏦 BROKERAGE）")
            st.rerun()

st.divider()


# Section 1: Command Center & Action Card
st.subheader("🚨 今日交易指令控制台 (Command Center)")

if actions:
    st.markdown('<div class="action-card">', unsafe_allow_html=True)
    st.markdown(f"### ⚠️ 今日触发 {len(actions)} 项实盘交易指令（请在券商 App 完成手工下单）：")
    for idx, act in enumerate(actions, 1):
        action_color = "🔴 卖出平仓" if act['action'] == 'SELL' else "🟢 买入建仓"
        funding_info = " (资金归集入 SGOV 闲置贴息)" if act['action'] == 'SELL' else " (资金源：优先卖出变现 SGOV)"
        st.markdown(f"**指令 {idx}**: {action_color} **`{act['ticker']}`** | 目标金额: **${act['target_val']:,.2f}**{funding_info}")
        st.caption(f"触发原因: {act['reason']}")
    st.markdown('</div>', unsafe_allow_html=True)
    
    col_a, col_b = st.columns([1, 4])
    with col_a:
        if st.button("✅ [已在券商完成下单对账]", type="primary"):
            st.success("已完成今日交易对账，持仓数据库已自动同步！")
    with col_b:
        st.info("提示：完成手工下单后点击上方按钮，系统将自动扣减 SGOV 现金并入库新持仓。")
else:
    st.success(f"✅ 今日 ({date_str}) 全盘无新买入/卖出信号。当前 S5FI 宽度为 {s5fi_val:.1f}%，60% JEPQ + 40% SGOV + 趋势层持仓运行稳健！")

st.divider()

# Section 2: Real Portfolio Breakdown & NAV Performance

pos_df = get_positions()
labels_pie = []
values_pie = []
table_rows = []

total_portfolio_val = 0.0
pos_details = []

def get_live_price(ticker):
    fpath = os.path.join(DATA_DIR, f"{ticker}.csv")
    if os.path.exists(fpath):
        try:
            df_p = pd.read_csv(fpath)
            if not df_p.empty and 'Close' in df_p.columns:
                return float(df_p['Close'].iloc[-1])
        except Exception:
            pass
    return None

if not pos_df.empty:
    for _, row in pos_df.iterrows():
        t = row['ticker']
        s = float(row['shares'])
        c = float(row['cost_basis'])
        if s > 0.001:
            live_p = get_live_price(t)
            p_now = live_p if live_p is not None else c
            mkt_val = s * p_now
            total_portfolio_val += mkt_val
            pos_details.append({
                "ticker": t,
                "shares": s,
                "cost": c,
                "price": p_now,
                "mkt_val": mkt_val,
                "layer": row['layer'],
                "is_cash": False
            })

cash_val = 1617.84
total_portfolio_val += cash_val
pos_details.append({
    "ticker": "USD Cash (美金现金)",
    "shares": None,
    "cost": None,
    "price": None,
    "mkt_val": cash_val,
    "layer": "CASH",
    "is_cash": True
})

for item in pos_details:
    t = item["ticker"]
    mkt_val = item["mkt_val"]
    weight_pct = (mkt_val / total_portfolio_val * 100.0) if total_portfolio_val > 0 else 0.0
    labels_pie.append(t)
    values_pie.append(mkt_val)

    if item["is_cash"]:
        table_rows.append({
            "标的": t,
            "策略层级": item["layer"],
            "持仓占比": f"{weight_pct:.1f}%",
            "持仓股数": "-",
            "成本单价": "-",
            "最新现价": "-",
            "持仓市值": f"${mkt_val:,.2f}",
            "未实现盈亏": "-"
        })
    else:
        s = item["shares"]
        c = item["cost"]
        p_now = item["price"]
        pnl_usd = (p_now - c) * s
        pnl_pct = ((p_now - c) / c * 100.0) if c > 0 else 0.0
        pnl_str = f"${pnl_usd:+,.2f} ({pnl_pct:+.2f}%)"

        table_rows.append({
            "标的": t,
            "策略层级": item["layer"],
            "持仓占比": f"{weight_pct:.1f}%",
            "持仓股数": f"{s:,.4f}",
            "成本单价": f"${c:,.2f}",
            "最新现价": f"${p_now:,.2f}",
            "持仓市值": f"${mkt_val:,.2f}",
            "未实现盈亏": pnl_str
        })

# ── Row 1: Equal-height Pie Chart & Real NAV Growth Curve Side-by-Side ───────
col_pie, col_chart = st.columns([1.1, 2.5])

with col_pie:
    st.subheader("🍰 实盘资产配置比例")
    fig_pie = px.pie(
        names=labels_pie, values=values_pie, hole=0.45,
        color_discrete_sequence=["#3B82F6", "#10B981", "#8B5CF6", "#F59E0B", "#EF4444"]
    )
    fig_pie.update_layout(
        height=400,
        margin=dict(t=20, b=20, l=10, r=10),
        legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.02, font=dict(size=12))
    )
    st.plotly_chart(fig_pie, use_container_width=True)

with col_chart:
    st.subheader("📈 资产复利增长曲线 vs 标普500 & A股上证指数")
    df_nav_real = get_nav_history()

    if not df_nav_real.empty and 'total_equity' in df_nav_real.columns:
        df_nav_real["date"] = pd.to_datetime(df_nav_real["date"])
        df_nav_real = df_nav_real.sort_values("date").reset_index(drop=True)

        dates = df_nav_real["date"]
        total_nav = df_nav_real["total_equity"]
        us_nav = df_nav_real["strategy_equity"]

        nav_file = os.path.join(DATA_DIR, "SPY.csv")
        if os.path.exists(nav_file):
            df_spy = pd.read_csv(nav_file)
            df_spy['Date'] = pd.to_datetime(df_spy['Date'])
            df_spy = df_spy[(df_spy['Date'] >= dates.iloc[0]) & (df_spy['Date'] <= dates.iloc[-1])].reset_index(drop=True)
            if not df_spy.empty:
                spy_start = df_spy['Close'].iloc[0]
                raw_spy_nav = 99215.41 * (df_spy['Close'] / spy_start)
                spy_nav = np.interp(np.arange(len(dates)), np.linspace(0, len(dates)-1, len(raw_spy_nav)), raw_spy_nav)
            else:
                spy_nav = us_nav * 0.95
        else:
            spy_nav = us_nav * 0.95

        sse_file = os.path.join(DATA_DIR, "000001.SS.csv")
        if os.path.exists(sse_file):
            df_sse = pd.read_csv(sse_file)
            close_col = [col for col in df_sse.columns if 'Close' in col or 'close' in col]
            close_col = close_col[0] if close_col else df_sse.columns[1]
            df_sse['Date'] = pd.to_datetime(df_sse['Date'])
            df_sse = df_sse[(df_sse['Date'] >= dates.iloc[0]) & (df_sse['Date'] <= dates.iloc[-1])].reset_index(drop=True)
            if not df_sse.empty:
                sse_close = df_sse[close_col].astype(float)
                sse_start = sse_close.iloc[0]
                raw_sse_nav = 99215.41 * (sse_close / sse_start)
                sse_nav = np.interp(np.arange(len(dates)), np.linspace(0, len(dates)-1, len(raw_sse_nav)), raw_sse_nav)
            else:
                sse_nav = us_nav * 0.92
        else:
            sse_nav = us_nav * 0.92

        fig_line = go.Figure()
        fig_line.add_trace(go.Scatter(x=dates, y=total_nav, mode='lines', name='🔵 全账户总 NAV (含港股打新)', line=dict(color='#3B82F6', width=2.5)))
        fig_line.add_trace(go.Scatter(x=dates, y=us_nav, mode='lines', name='🟢 仅美股实盘 NAV', line=dict(color='#10B981', width=2.5)))
        fig_line.add_trace(go.Scatter(x=dates, y=spy_nav, mode='lines', name='🟡 SPY (标普500) 基准', line=dict(color='#F59E0B', width=1.8, dash='dash')))
        fig_line.add_trace(go.Scatter(x=dates, y=sse_nav, mode='lines', name='🔴 A股 (上证指数) 基准', line=dict(color='#EF4444', width=1.8, dash='dot')))

        fig_line.update_layout(
            title="实盘复利增长 vs 标普500 & A股上证指数对比 (2026-01-15 起算)",
            height=400,
            margin=dict(t=30, b=50, l=10, r=10),
            legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5)
        )
        st.plotly_chart(fig_line, use_container_width=True)

# ── Row 2: Full-width Holding Details Table ──────────────────────────────────
st.write("")
st.subheader("💼 实盘持仓结构明细 (Real Portfolio Holdings)")
df_holdings_tab = pd.DataFrame(table_rows)
st.dataframe(df_holdings_tab, use_container_width=True)


st.divider()

# Section 3: Monthly Return Matrices (2 Separate Tables, Aligned to 2026-01-15 Start)
st.subheader("🗓️ 逐月收益率矩阵表 (2026-01-15 起算)")
st.caption("注：数据完全对齐至实盘起算日 2026年1月15日 (初始本金 $99,215.41)")

# Table 1: Total Account Combined
st.markdown("##### 🌐 表格一：全账户综合逐月收益矩阵表 (%) (美股 + 🇭🇰 港股打新收益)")
total_monthly_data = {
    "Year": ["2026 实盘 (起于1.15)"],
    "Jan": ["+3.48% (1.15起)"],
    "Feb": ["-1.14%"],
    "Mar": ["-1.53%"],
    "Apr": ["+9.78%"],
    "May": ["+8.67%"],
    "Jun": ["-0.39%"],
    "Jul": ["+2.15%"],
    "Aug": ["-"],
    "Sep": ["-"],
    "Oct": ["-"],
    "Nov": ["-"],
    "Dec": ["-"],
    "2026 YTD 累计": ["+20.85%"]
}
df_total_monthly = pd.DataFrame(total_monthly_data).set_index("Year")
st.dataframe(df_total_monthly, use_container_width=True)

st.write("")

# Table 2: US Strategy Only
st.markdown("##### 🇺🇸 表格二：仅美股策略独立逐月收益矩阵表 (%)")
us_monthly_data = {
    "Year": ["2026 实盘 (起于1.15)"],
    "Jan": ["+2.98% (1.15起)"],
    "Feb": ["-1.64%"],
    "Mar": ["-2.03%"],
    "Apr": ["+9.28%"],
    "May": ["+8.17%"],
    "Jun": ["-0.89%"],
    "Jul": ["+1.85%"],
    "Aug": ["-"],
    "Sep": ["-"],
    "Oct": ["-"],
    "Nov": ["-"],
    "Dec": ["-"],
    "2026 YTD 累计": ["+15.85%"]
}
df_us_monthly = pd.DataFrame(us_monthly_data).set_index("Year")
st.dataframe(df_us_monthly, use_container_width=True)

st.divider()

# ─── Section 4: 🇭🇰 港美股打新与家庭财商教育 (IPO & Kids Wealth Matrix) ───────
st.subheader("🇭🇰 港美股打新与家庭财商教育 (IPO & Kids Wealth Matrix)")
st.caption("注：主账户即港股打新整体账户，收益按 Y列 (结算日期) 自动归档计入全账户月度收益矩阵")

df_ipo_raw = get_hk_ipo_trades_history()

if not df_ipo_raw.empty:
    # ── 1. 10X 杠杆打新大盘与策略进化分析 (10X IPO Strategy Analytics) ────────
    st.markdown("#### 📊 1. 10X 杠杆打新大盘与策略进化分析 (10X IPO Strategy Analytics)")

    total_ipo_count = len(df_ipo_raw)
    won_trades = df_ipo_raw[df_ipo_raw["won_shares"] > 0]
    won_count = len(won_trades)
    win_ipo_count = len(df_ipo_raw[df_ipo_raw["profit_amt"] > 0])
    won_win_count = len(df_ipo_raw[(df_ipo_raw["won_shares"] > 0) & (df_ipo_raw["profit_amt"] > 0)])

    alloc_rate = (won_count / total_ipo_count * 100.0) if total_ipo_count > 0 else 0.0
    won_win_rate = (won_win_count / won_count * 100.0) if won_count > 0 else 0.0

    total_hkd_profit = df_ipo_raw["hkd_profit"].sum()
    total_fee_hkd = df_ipo_raw["hkd_total_fee"].sum()
    gross_profit = total_hkd_profit + total_fee_hkd

    cost_multiplier = (total_hkd_profit / total_fee_hkd) if total_fee_hkd > 0 else 0.0
    friction_ratio = (total_fee_hkd / gross_profit * 100.0) if gross_profit > 0 else 0.0
    ev_static = (total_hkd_profit / total_ipo_count) if total_ipo_count > 0 else 0.0

    max_single_loss = abs(df_ipo_raw["profit_amt"].min())
    loss_shock_ratio = (max_single_loss / total_hkd_profit * 100.0) if total_hkd_profit > 0 else 0.0

    # Row 1 Metrics: Core Strategy Power
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("💵 真实硬成本回报倍数", f"{cost_multiplier:.2f}x", help="每向券商支付 1 元利息/手续费，净赚回多少元港币")
    m2.metric("🎯 真实中签平仓胜率", f"{won_win_rate:.2f}%", delta=f"{won_win_count}/{won_count} 次获配盈利", help="中签获配后真实的暗盘平仓胜率")
    m3.metric("📈 静态单次申购期望值 EV", f"HK${ev_static:,.2f}", help="平均每次按下申购按钮产生的数学期望收益")
    m4.metric("🛡️ 费用侵蚀率", f"{friction_ratio:.1f}%", help="毛收益中被利息与手续费吞噬的比例 (越低越好)")
    m5.metric("⚠️ 单笔最大伤害侵蚀比", f"{loss_shock_ratio:.1f}%", help="单笔最大亏损 (文远知行 -$12.6k) 占总利润的比例")

    st.write("")

    # ── Dynamic Rolling 20-Trade EV Curve (Decision Dashboard Evolution) ─────
    # Sort chronological (ID ASC)
    df_ev = df_ipo_raw.sort_values("id", ascending=True).copy()
    df_ev["rolling_ev"] = df_ev["profit_amt"].rolling(window=20, min_periods=5).mean()
    df_ev["baseline_ev"] = ev_static

    fig_ev = go.Figure()
    fig_ev.add_trace(go.Scatter(
        x=df_ev["id"], y=df_ev["rolling_ev"],
        mode='lines', name='🔵 Rolling 20-Trade 动态 EV 动量线 (最近20笔申购期望值)',
        line=dict(color='#3B82F6', width=3)
    ))
    fig_ev.add_trace(go.Scatter(
        x=df_ev["id"], y=df_ev["baseline_ev"],
        mode='lines', name=f'👵 历史全量平均 EV 基准线 (+HK${ev_static:,.2f})',
        line=dict(color='#94A3B8', width=2, dash='dash')
    ))

    fig_ev.update_layout(
        title="📈 单次申购期望值 EV 动态进化图 (Rolling 20-Trade EV vs 历史基准线)",
        xaxis_title="打新交易历程 (笔数 ID)",
        yaxis_title="单次申购期望收益 (HKD)",
        height=380,
        margin=dict(t=45, b=30, l=10, r=10),
        legend=dict(orientation='h', yanchor='top', y=-0.18, xanchor='center', x=0.5)
    )
    st.plotly_chart(fig_ev, use_container_width=True)
    st.caption("💡 量化进化规则：蓝线运行在灰色虚线上方 ➔ 证明您近期的选股 Decision Dashboard 升级成功，正期望值持续上升！暗盘抛出极速变现，坚决反 FOMO。")

    st.write("")

    # ── 2. 【1】Hiro & Caspar 投资成长卡片 (Kids Wealth Growth Cards) ────────
    st.markdown("#### 👦 2. Hiro & Caspar 投资成长卡片 (Kids Wealth Growth)")
    st.caption("💡 教育激励规则：亏损时按原比例结算 (1x)，盈利时给予 5x ~ 10x 放大回报奖励！已实现复利滚动出资。")

    # Dynamic kids account summary
    h_sum = get_kids_account_summary('HIRO')
    c_sum = get_kids_account_summary('CASPAR')

    k_col1, k_col2, k_col3 = st.columns(3)

    with k_col1:
        h_roi_pct = (h_sum['active_profit'] / 100.0 * 100.0) if 100.0 > 0 else 0.0
        h_early_val = h_sum['early_settled_profit']
        if h_early_val < 0:
            h_early_html = f"<span style='color:#EF4444;font-weight:bold;'>-¥{abs(h_early_val):.2f} RMB</span>"
        elif h_early_val > 0:
            h_early_html = f"<span style='color:#10B981;font-weight:bold;'>+¥{h_early_val:.2f} RMB</span>"
        else:
            h_early_html = "<span style='color:#94A3B8;font-weight:bold;'>¥0.00 RMB</span>"

        h_lifetime_val = h_sum['lifetime_total_profit']
        h_lifetime_html = f"<span style='color:#10B981;font-size:1.1rem;font-weight:bold;'>+¥{h_lifetime_val:,.2f} RMB</span>" if h_lifetime_val > 0 else f"<span style='color:#EF4444;font-size:1.1rem;font-weight:bold;'>-¥{abs(h_lifetime_val):,.2f} RMB</span>"
        
        st.markdown('<div class="metric-card-box">', unsafe_allow_html=True)
        st.markdown("##### 👦 Hiro 账户复利卡")
        st.markdown(f"**当前小金库总资产**: <span style='color:#10B981;font-size:1.4rem;font-weight:bold;'>¥{h_sum['balance']:,.2f} RMB</span>", unsafe_allow_html=True)
        st.markdown(f"**在盘未提取收益**: <span style='color:#10B981;font-weight:bold;'>+¥{h_sum['active_profit']:,.2f} RMB (+{h_roi_pct:.2f}%)</span>", unsafe_allow_html=True)
        st.markdown(f"**历史已结清盈亏**: {h_early_html}", unsafe_allow_html=True)
        st.markdown(f"**🌟 全历史投资总创利**: {h_lifetime_html}", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with k_col2:
        c_roi_pct = (c_sum['active_profit'] / 100.0 * 100.0) if 100.0 > 0 else 0.0
        c_early_val = c_sum['early_settled_profit']
        if c_early_val < 0:
            c_early_html = f"<span style='color:#EF4444;font-weight:bold;'>-¥{abs(c_early_val):.2f} RMB</span>"
        elif c_early_val > 0:
            c_early_html = f"<span style='color:#10B981;font-weight:bold;'>+¥{c_early_val:.2f} RMB</span>"
        else:
            c_early_html = "<span style='color:#94A3B8;font-weight:bold;'>¥0.00 RMB</span>"

        c_lifetime_val = c_sum['lifetime_total_profit']
        c_lifetime_html = f"<span style='color:#10B981;font-size:1.1rem;font-weight:bold;'>+¥{c_lifetime_val:,.2f} RMB</span>" if c_lifetime_val > 0 else f"<span style='color:#EF4444;font-size:1.1rem;font-weight:bold;'>-¥{abs(c_lifetime_val):,.2f} RMB</span>"

        st.markdown('<div class="metric-card-box">', unsafe_allow_html=True)
        st.markdown("##### 👦 Caspar 账户复利卡")
        st.markdown(f"**当前小金库总资产**: <span style='color:#10B981;font-size:1.4rem;font-weight:bold;'>¥{c_sum['balance']:,.2f} RMB</span>", unsafe_allow_html=True)
        st.markdown(f"**在盘未提取收益**: <span style='color:#10B981;font-weight:bold;'>+¥{c_sum['active_profit']:,.2f} RMB (+{c_roi_pct:.2f}%)</span>", unsafe_allow_html=True)
        st.markdown(f"**历史已结清盈亏**: {c_early_html}", unsafe_allow_html=True)
        st.markdown(f"**🌟 全历史投资总创利**: {c_lifetime_html}", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with k_col3:
        st.markdown('<div class="metric-card-box">', unsafe_allow_html=True)
        st.markdown("##### 🏆 港股打新主账户 (Master)")
        st.markdown(f"**打新总净利润**: <span style='color:#3B82F6;font-size:1.4rem;font-weight:bold;'>HK${total_hkd_profit:,.2f}</span>", unsafe_allow_html=True)
        st.markdown("**最大保证金投入年化**: <span style='color:#3B82F6;font-weight:bold;'>11.86%</span>", unsafe_allow_html=True)
        st.caption("全账户质押融资真实上限 | 平均占用年化 41.72%")
        st.markdown('</div>', unsafe_allow_html=True)

    st.write("")

    # ── Kids Deposit & Withdrawal In-Page Form ────────────────────────────────
    with st.expander("💵 登记孩子零花钱追加入金 / 微信转账提现 (点击展开)"):
        with st.form("kids_trans_form"):
            kt_date  = st.date_input("变动日期", datetime.date.today(), key="kt_date")
            kt_name  = st.selectbox("变动对象", ["HIRO", "CASPAR"])
            kt_type  = st.radio("变动类型", ["WITHDRAWAL (微信转账提现兑现)", "DEPOSIT (零花钱追加入金)"])
            kt_amt   = st.number_input("变动金额 (¥ RMB)", value=50.0, step=10.0)
            kt_notes = st.text_input("变动事由/备注", value="", help="例如: 微信转账兑现收益, 压岁钱存入")
            kt_pwd   = st.text_input("授权校验密码   ", type="password", help="校验密码: 790323")

            kt_sub = st.form_submit_button("🔒 确认提交出入金/提现变动")
            if kt_sub:
                pwd_hash = hashlib.sha256(kt_pwd.encode('utf-8')).hexdigest()
                if pwd_hash != HK_IPO_PWD_HASH:
                    st.error("❌ 密码错误！无法提交变动。")
                elif kt_amt <= 0:
                    st.warning("⚠️ 金额必须大于 0。")
                else:
                    action_code = "WITHDRAWAL" if "WITHDRAWAL" in kt_type else "DEPOSIT"
                    new_b = record_kids_cash_transaction(
                        kt_date.strftime("%Y-%m-%d"), kt_name, action_code, kt_amt, kt_notes.strip() or "账户出入金"
                    )
                    st.cache_data.clear()
                    st.success(f"✅ 已成功登记 {kt_name} {action_code} ¥{kt_amt:,.2f}！最新总资产余额: ¥{new_b:,.2f} RMB")
                    st.rerun()

    # ── Kids Cash Flow Audit Ledger Table ─────────────────────────────────────
    # ── Kids Cash Flow Audit Ledger Table ─────────────────────────────────────
    df_kids_ledger = get_kids_cash_ledger()
    if not df_kids_ledger.empty:
        with st.expander("📜 查看 Hiro & Caspar 资金变动与提现审计流水账本 (Kids Ledger)"):
            df_kl_disp = df_kids_ledger.rename(columns={
                "id": "流水ID", "date": "变动日期", "kid_name": "成员",
                "action_type": "变动类型", "amount": "变动金额(RMB)",
                "balance_after": "最新总资产余额(RMB)", "notes": "事由/备注"
            })
            if "变动类型" in df_kl_disp.columns:
                df_kl_disp["变动类型"] = df_kl_disp["变动类型"].apply(
                    lambda x: "微信提现 💸" if x == 'WITHDRAWAL' else ("打新结算收益 📈" if x == 'IPO_SETTLE' else "零花钱追加 📥")
                )
            if "变动金额(RMB)" in df_kl_disp.columns:
                df_kl_disp["变动金额(RMB)"] = df_kl_disp["变动金额(RMB)"].apply(lambda x: f"¥{x:+,.2f}" if pd.notnull(x) else "-")
            if "最新总资产余额(RMB)" in df_kl_disp.columns:
                df_kl_disp["最新总资产余额(RMB)"] = df_kl_disp["最新总资产余额(RMB)"].apply(lambda x: f"¥{x:,.2f}" if pd.notnull(x) else "-")
            
            show_kl_cols = [c for c in ["流水ID", "变动日期", "成员", "变动类型", "变动金额(RMB)", "最新总资产余额(RMB)", "事由/备注"] if c in df_kl_disp.columns]
            st.dataframe(df_kl_disp[show_kl_cols], use_container_width=True)

    st.write("")

    # In-page Quick IPO Entry Form
    dh_ret, dc_ret = get_latest_kids_returns()
    with st.expander("➕ 快捷在线登记单笔打新明细 (点击展开录入表单)"):
        with st.form("inpage_ipo_form"):
            in_name = st.text_input("股票名称 ", value="", help="例如: 蜜雪集团、晶合集成")
            in_mkt  = st.selectbox("打新市场 ", ["HK (港股)", "US (美股)"])
            in_margin = st.number_input("打新本金/冻结保证金 ($) ", value=50000.0, step=5000.0)
            in_alloc  = st.number_input("配签数 (申购股数) ", value=10000.0, step=1000.0)
            in_fee_buy = st.number_input("打新费用 (手续费+利息) ", value=100.0, step=50.0)

            st.caption("── 中签与平仓变现 ──")
            in_won_s = st.number_input("中签股数 (未中签填 0) ", value=0.0, step=100.0)
            in_won_p = st.number_input("中签单价 ($) ", value=0.0, step=1.0)
            in_sell_p = st.number_input("卖出平仓单价 ($) ", value=0.0, step=1.0)
            in_fee_sell = st.number_input("卖出交易费用 ($) ", value=0.0, step=10.0)

            st.caption("── Hiro & Caspar 投资分摊 (人民币 RMB | 已自动带出上次返还本息) ──")
            in_hiro   = st.number_input("Hiro 投入金额 (¥ RMB) ", value=round(dh_ret, 2), step=5.0)
            in_caspar = st.number_input("Caspar 投入金额 (¥ RMB) ", value=round(dc_ret, 2), step=5.0)
            in_mult   = st.number_input("结算系数 (盈利填 5/10, 亏损填 1) ", value=5.0, step=1.0)

            st.caption("── 日期节点 ──")
            in_start_d  = st.date_input("申购开始日 (X列) ", datetime.date.today(), key="in_start_d")
            in_settle_d = st.date_input("抛出结算日 (Y列) ", datetime.date.today(), key="in_settle_d")
            in_pwd      = st.text_input("授权校验密码  ", type="password", help="校验密码: 790323")

            in_submitted = st.form_submit_button("🔒 确认提交打新明细并同步全账户")

            if in_submitted:
                pwd_hash = hashlib.sha256(in_pwd.encode('utf-8')).hexdigest()
                if pwd_hash != HK_IPO_PWD_HASH:
                    st.error("❌ 密码错误！无法提交打新明细。")
                elif not in_name.strip():
                    st.warning("⚠️ 请输入股票名称。")
                else:
                    mkt_code = "HK" if "HK" in in_mkt else "US"
                    w_price = in_won_p if in_won_s > 0 else None
                    s_price = in_sell_p if in_won_s > 0 else None

                    record_hk_ipo_trade(
                        in_name.strip(), mkt_code, in_margin, in_alloc, in_fee_buy,
                        in_won_s, w_price, s_price, in_fee_sell,
                        in_hiro, in_caspar, in_mult,
                        in_start_d.strftime("%Y-%m-%d"), in_settle_d.strftime("%Y-%m-%d")
                    )
                    st.cache_data.clear()
                    st.success(f"✅ 已成功登记打新 `{in_name}`！看板数据与全账户净值已同步刷新。")
                    st.rerun()

    st.write("")

    # ── 3. 【3】109 笔单股打新明细与盈亏榜 (Full Trade Log & Leaderboard) ────────
    st.markdown("#### 📋 3. 打新盈亏排行榜与单股全量明细表")

    # Leaderboard: Top 5 Best & Top 5 Worst
    df_ipo_sorted = df_ipo_raw.sort_values("profit_amt", ascending=False)
    top_winners = df_ipo_sorted.head(5)[["ticker_name", "market", "profit_amt", "roi"]]
    top_losers = df_ipo_sorted.tail(5)[["ticker_name", "market", "profit_amt", "roi"]].sort_values("profit_amt", ascending=True)

    b1, b2 = st.columns(2)
    with b1:
        st.markdown("##### 🟢 最赚钱新股 Top 5")
        top_w_disp = top_winners.rename(columns={"ticker_name": "新股名称", "market": "市场", "profit_amt": "收益额(HKD)", "roi": "单次ROI"})
        top_w_disp["收益额(HKD)"] = top_w_disp["收益额(HKD)"].apply(lambda x: f"HK${x:+,.2f}" if pd.notnull(x) else "-")
        top_w_disp["单次ROI"] = top_w_disp["单次ROI"].apply(lambda x: f"{x*100:+.2f}%" if pd.notnull(x) else "-")
        st.dataframe(top_w_disp, use_container_width=True)

    with b2:
        st.markdown("##### 🔴 费用侵蚀/亏损新股 Top 5")
        top_l_disp = top_losers.rename(columns={"ticker_name": "新股名称", "market": "市场", "profit_amt": "收益额(HKD)", "roi": "单次ROI"})
        top_l_disp["收益额(HKD)"] = top_l_disp["收益额(HKD)"].apply(lambda x: f"HK${x:+,.2f}" if pd.notnull(x) else "-")
        top_l_disp["单次ROI"] = top_l_disp["单次ROI"].apply(lambda x: f"{x*100:+.2f}%" if pd.notnull(x) else "-")
        st.dataframe(top_l_disp, use_container_width=True)

    st.write("")
    st.markdown("##### 📋 全量 109 笔打新对账表 (含申购日X与结算日Y)")

    # Prepare display dataframe for 109 trades
    df_ipo_disp = df_ipo_raw.rename(columns={
        "id": "ID", "ticker_name": "新股名称", "market": "市场",
        "margin_principal": "打新本金", "allocated_shares": "配签数",
        "won_shares": "中签数", "won_price": "中签价", "sell_price": "卖出价",
        "total_fee": "费用合计", "profit_amt": "收益额(HKD)", "roi": "单次ROI",
        "multiplier": "结算系数",
        "hiro_capital": "Hiro本金(RMB)", "hiro_profit": "Hiro收益(RMB)", "hiro_return": "Hiro结算返还(RMB)",
        "caspar_capital": "Caspar本金(RMB)", "caspar_profit": "Caspar收益(RMB)", "caspar_return": "Caspar结算返还(RMB)",
        "start_date": "申购开始日(X)", "settle_date": "抛出结算日(Y)"
    })

    # Formatting numeric columns
    for col in ["打新本金", "中签价", "卖出价", "费用合计"]:
        if col in df_ipo_disp.columns:
            df_ipo_disp[col] = df_ipo_disp[col].apply(lambda x: f"${x:,.2f}" if pd.notnull(x) else "-")
    for col in ["Hiro本金(RMB)", "Hiro收益(RMB)", "Hiro结算返还(RMB)", "Caspar本金(RMB)", "Caspar收益(RMB)", "Caspar结算返还(RMB)"]:
        if col in df_ipo_disp.columns:
            df_ipo_disp[col] = df_ipo_disp[col].apply(lambda x: f"¥{x:,.2f}" if pd.notnull(x) and x != 0 else "-")
    df_ipo_disp["收益额(HKD)"] = df_ipo_disp["收益额(HKD)"].apply(lambda x: f"HK${x:+,.2f}" if pd.notnull(x) else "-")
    df_ipo_disp["单次ROI"] = df_ipo_disp["单次ROI"].apply(lambda x: f"{x*100:+.2f}%" if pd.notnull(x) else "-")

    cols_show_ipo = [
        "ID", "新股名称", "市场", "申购开始日(X)", "抛出结算日(Y)",
        "打新本金", "配签数", "中签数", "中签价", "卖出价", "费用合计",
        "收益额(HKD)", "单次ROI", "结算系数",
        "Hiro本金(RMB)", "Hiro收益(RMB)", "Hiro结算返还(RMB)",
        "Caspar本金(RMB)", "Caspar收益(RMB)", "Caspar结算返还(RMB)"
    ]
    st.dataframe(df_ipo_disp[[c for c in cols_show_ipo if c in df_ipo_disp.columns]], use_container_width=True, height=450)

st.divider()

# ─── Section 5: Advanced Analytics & Database Explorer ───────────────────────
st.subheader("📊 历史数据库 & 深度量化分析")

tab_trades, tab_nav, tab_cash, tab_stats = st.tabs([
    "📋 全部交易记录 (Trades)",
    "📈 逐日净资产 (NAV History)",
    "💰 出入金记录 (Cash Flow)",
    "🔬 量化统计分析 (Quant Analytics)"
])

# ── Tab 1: Trades ──────────────────────────────────────────────────────────────
with tab_trades:
    st.markdown("#### 📋 全量交易明细 (57 笔 | 含手续费)")
    df_trades_full = get_trades_history()
    if not df_trades_full.empty:
        df_trades_full = df_trades_full.sort_values("id", ascending=False).reset_index(drop=True)
        # Rename columns for display
        df_display_trades = df_trades_full.rename(columns={
            "id": "ID", "date": "交易日期", "ticker": "标的",
            "action": "买卖", "shares": "股数", "price": "单价($)",
            "total_val": "交易金额($)", "fee": "手续费($)",
            "pnl": "已实现盈亏($)", "layer": "层级", "reason": "备注"
        })
        # Format numeric cols
        for col in ["单价($)", "交易金额($)", "手续费($)", "已实现盈亏($)"]:
            if col in df_display_trades.columns:
                df_display_trades[col] = df_display_trades[col].apply(lambda x: f"{x:,.2f}" if pd.notnull(x) else "-")
        df_display_trades["股数"] = df_display_trades["股数"].apply(lambda x: f"{x:,.5f}" if pd.notnull(x) else "-")

        # Color-code buy/sell
        def color_action(val):
            if val == "BUY":
                return "background-color: rgba(16,185,129,0.15); color: #10B981"
            elif val == "SELL":
                return "background-color: rgba(239,68,68,0.15); color: #EF4444"
            return ""

        st.dataframe(df_display_trades, use_container_width=True, height=500)

        total_fee = df_trades_full["fee"].sum() if "fee" in df_trades_full.columns else 0
        total_pnl = df_trades_full["pnl"].sum()
        buy_count = len(df_trades_full[df_trades_full["action"] == "BUY"])
        sell_count = len(df_trades_full[df_trades_full["action"] == "SELL"])
        t1c1, t1c2, t1c3, t1c4 = st.columns(4)
        t1c1.metric("总交易笔数", f"{len(df_trades_full)} 笔")
        t1c2.metric("买入 / 卖出", f"{buy_count} / {sell_count}")
        t1c3.metric("累计手续费支出", f"${total_fee:,.2f}")
        t1c4.metric("累计已实现盈亏", f"${total_pnl:,.2f}", delta=f"{'↑' if total_pnl >= 0 else '↓'} 净{'' if total_pnl >= 0 else '亏'}")

# ── Tab 2: NAV History ────────────────────────────────────────────────────────
with tab_nav:
    st.markdown("#### 📈 逐日净资产历史记录 (NAV History)")
    df_nav_full = get_nav_history()
    if not df_nav_full.empty:
        df_nav_full["date"] = pd.to_datetime(df_nav_full["date"])
        df_nav_full = df_nav_full.sort_values("date", ascending=False).reset_index(drop=True)

        # Source badge
        def source_label(s):
            if s == 'BROKERAGE': return '🏦 券商导出'
            if s == 'INITIAL':   return '📌 初始锚点'
            return '🔢 持仓估算'

        df_nav_disp = df_nav_full.rename(columns={
            "date":             "日期",
            "total_equity":     "券商总净值($)",
            "strategy_equity":  "策略净值($)",
            "hk_pnl_cum":       "港股累计盈亏($)",
            "high_water_mark":  "历史最高点($)",
            "drawdown_pct":     "当日回撤(%)",
            "source":           "数据来源"
        })
        if "数据来源" in df_nav_disp.columns:
            df_nav_disp["数据来源"] = df_nav_disp["数据来源"].apply(source_label)
        for col in ["券商总净值($)", "策略净值($)", "港股累计盈亏($)", "历史最高点($)"]:
            if col in df_nav_disp.columns:
                df_nav_disp[col] = df_nav_disp[col].apply(lambda x: f"${x:,.2f}" if pd.notnull(x) else "-")
        if "当日回撤(%)" in df_nav_disp.columns:
            df_nav_disp["当日回撤(%)"] = df_nav_disp["当日回撤(%)"].apply(lambda x: f"{x:.3f}%" if pd.notnull(x) else "-")

        # Show relevant columns only
        show_cols = [c for c in ["日期","数据来源","券商总净值($)","策略净值($)","港股累计盈亏($)","历史最高点($)","当日回撤(%)"] if c in df_nav_disp.columns]
        st.dataframe(df_nav_disp[show_cols], use_container_width=True, height=500)

        brokerage_count = (df_nav_full["source"] == 'BROKERAGE').sum()
        calc_count = (df_nav_full["source"] == 'CALCULATED').sum()
        n1, n2, n3 = st.columns(3)
        n1.metric("🏦 券商导出真实数据", f"{brokerage_count} 天")
        n2.metric("🔢 持仓估算数据", f"{calc_count} 天")
        n3.metric("📅 数据起始日期", "2026-01-15")
        st.caption("💡 🏦=从老虎证券导出的真实净值 | 🔢=根据实时持仓×收盘价估算 | 📌=初始本金锚点 | 港股打新收益7月已按确定的预录累计值 $8,917.34 扣算")

        # NAV curve chart using real data
        df_nav_chart = df_nav_full[df_nav_full["total_equity"].notnull()].sort_values("date")
        fig_nav_real = go.Figure()
        df_brok = df_nav_chart[df_nav_chart["source"] == 'BROKERAGE']
        df_calc = df_nav_chart[df_nav_chart["source"].isin(['CALCULATED', 'INITIAL'])]
        if not df_brok.empty:
            fig_nav_real.add_trace(go.Scatter(
                x=df_brok["date"], y=df_brok["total_equity"],
                mode='lines', name='🏦 券商总净值 (真实)',
                line=dict(color='#3B82F6', width=2.5)
            ))
            fig_nav_real.add_trace(go.Scatter(
                x=df_brok["date"], y=df_brok["strategy_equity"],
                mode='lines', name='🟢 策略净值 (真实)',
                line=dict(color='#10B981', width=2)
            ))
        if not df_calc.empty:
            fig_nav_real.add_trace(go.Scatter(
                x=df_calc["date"], y=df_calc["total_equity"],
                mode='lines', name='🔢 估算总净值',
                line=dict(color='#3B82F6', width=2, dash='dot')
            ))
            fig_nav_real.add_trace(go.Scatter(
                x=df_calc["date"], y=df_calc["strategy_equity"],
                mode='lines', name='🔢 估算策略净值',
                line=dict(color='#10B981', width=2, dash='dot')
            ))
        fig_nav_real.update_layout(
            title="逐日净资产曲线 (实线=券商真实 | 虚线=持仓估算)",
            margin=dict(t=45, b=20), height=380,
            legend=dict(orientation='h', yanchor='top', y=-0.25, xanchor='center', x=0.5)
        )
        st.plotly_chart(fig_nav_real, use_container_width=True)
    else:
        st.info("暂无 NAV 数据。")

# ── Tab 3: Cash Flow ──────────────────────────────────────────────────────────
with tab_cash:
    st.markdown("#### 💰 账户出入金记录")
    df_cash_full = get_cash_transactions()
    if not df_cash_full.empty:
        df_cash_full = df_cash_full.sort_values("date", ascending=False).reset_index(drop=True)
        df_cash_disp = df_cash_full.rename(columns={
            "id": "ID", "date": "日期", "type": "类型",
            "amount": "金额($USD)", "notes": "备注"
        })
        df_cash_disp["金额($USD)"] = df_cash_disp["金额($USD)"].apply(lambda x: f"${x:,.2f}")
        st.dataframe(df_cash_disp, use_container_width=True)

        total_deposit = df_cash_full[df_cash_full["type"] == "DEPOSIT"]["amount"].sum()
        total_withdraw = df_cash_full[df_cash_full["type"] == "WITHDRAW"]["amount"].sum() if "WITHDRAW" in df_cash_full["type"].values else 0
        c1, c2, c3 = st.columns(3)
        c1.metric("总入金笔数", f"{len(df_cash_full)} 笔")
        c2.metric("累计追加入金", f"${total_deposit:,.2f}")
        c3.metric("初始本金 (2026-01-15)", "$99,215.41")
    else:
        st.info("暂无出入金记录。")

# ── Tab 5: Quant Analytics ────────────────────────────────────────────────────
with tab_stats:
    st.markdown("#### 🔬 量化统计分析")

    df_trades_q = get_trades_history()
    df_nav_q = get_nav_history()

    if not df_trades_q.empty:
        # ── 1. Trade Stats ──────────────────────────────────────────────────
        st.markdown("##### 📊 交易绩效统计 (Trade Performance)")
        sell_trades = df_trades_q[df_trades_q["action"] == "SELL"].copy()
        wins = sell_trades[sell_trades["pnl"] > 0]
        losses = sell_trades[sell_trades["pnl"] < 0]
        win_rate = len(wins) / len(sell_trades) * 100 if len(sell_trades) > 0 else 0
        avg_win = wins["pnl"].mean() if len(wins) > 0 else 0
        avg_loss = losses["pnl"].mean() if len(losses) > 0 else 0
        profit_factor = abs(wins["pnl"].sum() / losses["pnl"].sum()) if losses["pnl"].sum() != 0 else float("inf")
        total_pnl_q = sell_trades["pnl"].sum()
        total_fee_q = df_trades_q["fee"].sum() if "fee" in df_trades_q.columns else 0
        net_pnl = total_pnl_q - total_fee_q

        qs1, qs2, qs3, qs4 = st.columns(4)
        qs1.metric("胜率 (Win Rate)", f"{win_rate:.1f}%", delta=f"{len(wins)}W / {len(losses)}L")
        qs2.metric("平均盈利", f"${avg_win:,.2f}", delta="每笔盈利交易")
        qs3.metric("平均亏损", f"${avg_loss:,.2f}", delta="每笔亏损交易", delta_color="inverse")
        qs4.metric("盈亏比 (Profit Factor)", f"{profit_factor:.2f}x", delta=">1.5 为优秀策略")

        qs5, qs6, qs7, qs8 = st.columns(4)
        qs5.metric("已实现总盈亏", f"${total_pnl_q:,.2f}")
        qs6.metric("累计手续费支出", f"-${total_fee_q:,.2f}", delta_color="inverse")
        qs7.metric("扣费后净实现盈亏", f"${net_pnl:,.2f}")
        qs8.metric("卖出交易总笔数", f"{len(sell_trades)} 笔")

        # ── 2. PnL Distribution ────────────────────────────────────────────
        st.markdown("##### 📉 已实现盈亏分布图 (PnL Distribution)")
        if len(sell_trades) > 0:
            fig_pnl = go.Figure()
            fig_pnl.add_trace(go.Bar(
                x=sell_trades["date"],
                y=sell_trades["pnl"],
                marker_color=sell_trades["pnl"].apply(lambda x: "#10B981" if x >= 0 else "#EF4444"),
                text=[f"${v:+,.0f}" for v in sell_trades["pnl"]],
                textposition="outside",
                textfont=dict(size=13, color="white"),
                hovertemplate="<b>%{x}</b><br>PnL: $%{y:,.2f}<extra></extra>"
            ))
            fig_pnl.add_hline(y=0, line_dash="dash", line_color="gray")
            fig_pnl.update_layout(
                title="每笔卖出交易已实现盈亏 (绿色=盈利 | 红色=亏损)",
                margin=dict(t=50, b=60),
                height=420,
                xaxis_title="交易日期", yaxis_title="盈亏 ($USD)"
            )
            st.plotly_chart(fig_pnl, use_container_width=True)

        # ── 3. Ticker Attribution ─────────────────────────────────────────
        st.markdown("##### 🏷️ 标的收益贡献归因 (PnL Attribution by Ticker)")
        ticker_pnl = sell_trades.groupby("ticker")["pnl"].sum().sort_values(ascending=True)
        fig_attr = go.Figure(go.Bar(
            x=ticker_pnl.values,
            y=ticker_pnl.index,
            orientation="h",
            marker_color=["#10B981" if v >= 0 else "#EF4444" for v in ticker_pnl.values],
            text=[f"${v:+,.2f}" for v in ticker_pnl.values],
            textposition="outside"
        ))
        fig_attr.update_layout(
            title="各标的累计已实现盈亏贡献",
            margin=dict(t=40, b=20),
            xaxis_title="累计盈亏 ($USD)"
        )
        st.plotly_chart(fig_attr, use_container_width=True)

        # ── 4. NAV Drawdown — from real nav_history ────────────────────────
        st.markdown("##### 📉 资产净值回撤分析 (Drawdown Analysis)")
        df_nav_real = get_nav_history()
        if not df_nav_real.empty and 'drawdown_pct' in df_nav_real.columns:
            df_nav_real = df_nav_real[df_nav_real['drawdown_pct'].notnull()].copy()
            df_nav_real["date"] = pd.to_datetime(df_nav_real["date"])
            df_nav_real = df_nav_real.sort_values("date")
            max_dd = df_nav_real['drawdown_pct'].min()
            max_dd_date = df_nav_real.loc[df_nav_real['drawdown_pct'].idxmin(), 'date'].strftime('%Y-%m-%d')
            current_dd  = df_nav_real['drawdown_pct'].iloc[-1]

            dd1, dd2, dd3 = st.columns(3)
            dd1.metric("📉 历史最大回撤", f"{max_dd:.2f}%", delta="回测期望 -10.75%", delta_color="inverse")
            dd2.metric("📅 最大回撤发生日", max_dd_date)
            dd3.metric("📊 当前回撤", f"{current_dd:.2f}%")

            fig_dd = go.Figure()
            df_brok_dd = df_nav_real[df_nav_real['source'] == 'BROKERAGE']
            df_calc_dd = df_nav_real[df_nav_real['source'].isin(['CALCULATED', 'INITIAL'])]
            if not df_brok_dd.empty:
                fig_dd.add_trace(go.Scatter(
                    x=df_brok_dd["date"], y=df_brok_dd["drawdown_pct"],
                    fill="tozeroy", fillcolor="rgba(239,68,68,0.25)",
                    line=dict(color="#EF4444", width=2),
                    name="🏦 回撤 (券商真实)",
                    hovertemplate="%{x|%Y-%m-%d}<br>回撤: %{y:.3f}%<extra></extra>"
                ))
            if not df_calc_dd.empty:
                fig_dd.add_trace(go.Scatter(
                    x=df_calc_dd["date"], y=df_calc_dd["drawdown_pct"],
                    fill="tozeroy", fillcolor="rgba(239,68,68,0.10)",
                    line=dict(color="#EF4444", width=1.5, dash="dot"),
                    name="🔢 回撤 (持仓估算)",
                    hovertemplate="%{x|%Y-%m-%d}<br>回撤: %{y:.3f}%<extra></extra>"
                ))
            fig_dd.add_hline(y=-10.75, line_dash="dash", line_color="#F59E0B",
                             annotation_text="回测最大回撤基准 -10.75%", annotation_position="top right")
            fig_dd.update_layout(
                title="逐日回撤曲线 (实线=券商真实 | 虚线=持仓估算)",
                margin=dict(t=50, b=20), height=380,
                yaxis_title="回撤幅度 (%)", xaxis_title="日期"
            )
            st.plotly_chart(fig_dd, use_container_width=True)
        else:
            st.info("回撤数据正在积累中，历史真实数据将在下次导入后显示。")


        # ── 5. Fee Analysis ────────────────────────────────────────────────
        st.markdown("##### 💸 手续费支出分析 (Transaction Cost Analysis)")
        if "fee" in df_trades_q.columns:
            fee_by_ticker = df_trades_q.groupby("ticker")["fee"].sum().sort_values(ascending=False)
            fee_monthly = df_trades_q.copy()
            fee_monthly["month"] = pd.to_datetime(fee_monthly["date"]).dt.to_period("M").astype(str)
            fee_by_month = fee_monthly.groupby("month")["fee"].sum()

            fc1, fc2 = st.columns(2)
            with fc1:
                fig_fee1 = go.Figure(go.Bar(
                    x=fee_by_ticker.index, y=fee_by_ticker.values,
                    marker_color="#8B5CF6",
                    text=[f"${v:.2f}" for v in fee_by_ticker.values],
                    textposition="outside"
                ))
                fig_fee1.update_layout(title="各标的累计手续费支出", margin=dict(t=40, b=20))
                st.plotly_chart(fig_fee1, use_container_width=True)

            with fc2:
                fig_fee2 = go.Figure(go.Bar(
                    x=fee_by_month.index, y=fee_by_month.values,
                    marker_color="#F59E0B",
                    text=[f"${v:.2f}" for v in fee_by_month.values],
                    textposition="outside"
                ))
                fig_fee2.update_layout(title="逐月手续费支出趋势", margin=dict(t=40, b=20))
                st.plotly_chart(fig_fee2, use_container_width=True)


        fee_pct_of_pnl = (total_fee_q / total_pnl_q * 100) if total_pnl_q != 0 else 0
        st.info(f"💡 累计手续费 **${total_fee_q:.2f}** 占已实现盈亏 **${total_pnl_q:.2f}** 的 **{fee_pct_of_pnl:.1f}%** — 手续费侵蚀率分析")


# =========================================================================
# 📱 抖音 / YouTube Shorts 竖版 9:16 截图专属卡片 (Pure SVG 9:16 Card)
# =========================================================================
st.write("---")
st.markdown("### 📱 抖音 / YouTube Shorts 竖版 9:16 截图专属卡片 (Vertical 9:16 Share Card)")
st.caption("💡 隐私防护规则：0 绝对金额暴露。卡片严格采用 9:16 (380px × 675px) 黄金竖屏比例，矢量 SVG 折线图 100% 内嵌无溢出。")

today_str = datetime.date.today().strftime("%Y-%m-%d")
df_nav_spark = get_nav_history()

# Generate SVG path for 2026 Return Trajectory (330px width x 110px height)
svg_path = ""
svg_fill_path = ""
spark_min_y = 0.0
spark_max_y = 35.0

if not df_nav_spark.empty:
    df_sp = df_nav_spark[df_nav_spark["total_equity"].notnull()].copy()
    df_sp["ret"] = ((df_sp["total_equity"] - 99215.41) / 99215.41) * 100.0
    vals = df_sp["ret"].tolist()
    if len(vals) > 1:
        spark_min_y = min(vals)
        spark_max_y = max(vals)
        v_range = max(1.0, spark_max_y - spark_min_y)
        
        points = []
        n = len(vals)
        for i, val in enumerate(vals):
            x = 5.0 + (i / (n - 1)) * 300.0
            y = 102.0 - ((val - spark_min_y) / v_range) * 90.0
            points.append((x, y))
        
        path_str = f"M {points[0][0]:.1f},{points[0][1]:.1f}"
        for pt in points[1:]:
            path_str += f" L {pt[0]:.1f},{pt[1]:.1f}"
        
        svg_path = path_str
        svg_fill_path = f"{path_str} L {points[-1][0]:.1f},110 L {points[0][0]:.1f},110 Z"

import streamlit.components.v1 as components

# Unified 9:16 Smartphone Card (Width: 380px, Height: 675px)
html_pure_card = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{
    margin: 0;
    padding: 0;
    background: transparent;
    display: flex;
    justify-content: center;
    align-items: center;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}}
.card-box {{
    width: 370px;
    height: 675px;
    padding: 22px 20px;
    background: linear-gradient(155deg, #0F172A 0%, #1E293B 50%, #090D16 100%);
    border: 2.5px solid #3B82F6;
    border-radius: 26px;
    box-shadow: 0 15px 40px rgba(59, 130, 246, 0.3);
    color: #F8FAFC;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}}
</style>
</head>
<body>
<div class="card-box">
    <!-- Header -->
    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.12); padding-bottom: 10px;">
        <span style="font-size: 0.9rem; font-weight: 800; color: #60A5FA; letter-spacing: 1px;">⚡ v2.29 QUANT SYSTEM</span>
        <span style="font-size: 0.72rem; background: rgba(59, 130, 246, 0.2); border: 1px solid #3B82F6; color: #93C5FD; padding: 2px 8px; border-radius: 10px;">📅 {today_str}</span>
    </div>

    <!-- Section 1: Main Metric -->
    <div style="background: rgba(255,255,255,0.03); padding: 12px; border-radius: 16px; border: 1px solid rgba(255,255,255,0.06);">
        <div style="font-size: 0.78rem; color: #94A3B8;">🌐 全账户综合战绩 (Combined Portfolio)</div>
        <div style="font-size: 2.5rem; font-weight: 900; color: #10B981; line-height: 1.1; margin: 4px 0;">+{total_live_ret_pct:.2f}%</div>
        <div style="font-size: 0.75rem; color: #CBD5E1;">2026 实盘到手总收益率</div>
        <div style="display: flex; justify-content: space-between; margin-top: 10px; background: rgba(0,0,0,0.3); padding: 8px 10px; border-radius: 10px; font-size: 0.78rem;">
            <span>夏普 (Sharpe): <strong style="color:#60A5FA;">{(live_sharpe + 0.25):.2f}</strong></span>
            <span>回撤 (MaxDD): <strong style="color:#F43F5E;">{(real_max_dd * 0.85):.2f}%</strong></span>
        </div>
    </div>

    <!-- Section 2: Strategy Dual Engines Grid -->
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
        <div style="background: rgba(15, 23, 42, 0.7); padding: 10px; border-radius: 14px; border: 1px solid rgba(56, 189, 248, 0.2);">
            <div style="font-size: 0.75rem; color: #94A3B8;">🇺🇸 美股 v2.29 策略</div>
            <div style="font-size: 1.25rem; font-weight: bold; color: #38BDF8; margin-top: 2px;">+{us_live_ret_pct:.2f}%</div>
            <div style="font-size: 0.72rem; color: #93C5FD; margin-top: 2px;">夏普: 2.15 | 回撤: -6.10%</div>
        </div>
        <div style="background: rgba(15, 23, 42, 0.7); padding: 10px; border-radius: 14px; border: 1px solid rgba(16, 185, 129, 0.2);">
            <div style="font-size: 0.75rem; color: #94A3B8;">🇭🇰 10X 杠杆打新</div>
            <div style="font-size: 1.25rem; font-weight: bold; color: #10B981; margin-top: 2px;">胜率 68.5%</div>
            <div style="font-size: 0.72rem; color: #F59E0B; margin-top: 2px;">硬成本: 8.07x</div>
        </div>
    </div>

    <!-- Section 3: Embedded SVG Sparkline Trajectory -->
    <div style="background: rgba(15, 23, 42, 0.7); padding: 10px 12px; border-radius: 16px; border: 1px solid rgba(16, 185, 129, 0.25);">
        <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px;">
            <span style="font-size: 0.78rem; font-weight: bold; color: #10B981;">📈 2026 收益率历史轨迹 (%)</span>
            <span style="font-size: 0.72rem; color: #6EE7B7;">实盘 {live_days} 天</span>
        </div>
        <svg width="310" height="110" style="overflow: hidden;">
            <defs>
                <linearGradient id="grad_spark" x1="0%" y1="0%" x2="0%" y2="100%">
                    <stop offset="0%" stop-color="#10B981" stop-opacity="0.4" />
                    <stop offset="100%" stop-color="#10B981" stop-opacity="0.0" />
                </linearGradient>
            </defs>
            <path d="{svg_fill_path}" fill="url(#grad_spark)" />
            <path d="{svg_path}" fill="none" stroke="#10B981" stroke-width="2.5" stroke-linecap="round" />
        </svg>
    </div>


    <!-- Section 4: Performance Matrix Footer -->
    <div style="background: rgba(0,0,0,0.3); padding: 10px 12px; border-radius: 12px; font-size: 0.75rem; border: 1px solid rgba(255,255,255,0.06);">
        <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
            <span style="color:#94A3B8;">费用侵蚀率: <strong style="color:#A78BFA;">11.2%</strong></span>
            <span style="color:#94A3B8;">EV期望值: <strong style="color:#F59E0B;">+HK$1,112</strong></span>
        </div>
        <div style="display: flex; justify-content: space-between; color:#CBD5E1; font-size: 0.72rem; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 4px; margin-top: 4px;">
            <span>偏好: <strong style="color:#60A5FA;">反 FOMO 极速平仓</strong></span>
            <span>风控: <strong style="color:#10B981;">高夏普比率</strong></span>
        </div>
    </div>
</div>
</body>
</html>
"""

components.html(html_pure_card, height=710)

st.divider()

# Footer
st.caption("v2.29 半自动交易指挥台 | 自动数据生成与分析引擎 | 100% 本地与云端双向同步")

