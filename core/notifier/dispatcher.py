"""
Unified Proactive Notification Dispatcher (core/notifier/dispatcher.py)
Orchestrates multi-channel push across Telegram Bot and Feishu Robot.
Provides standard templates for:
1. Daily Trading Decision Cards (交易决策卡)
2. Two-Layer Multi-Broker Account NAV & Drift Reports (账户对账研报: Layer 1 宏观总账本 + Layer 2 量化策略)
3. Technical Anomaly & Data Alerts (技术告警卡)
"""

from typing import Dict, List, Optional, Any
import datetime
import re
from .telegram_dispatcher import TelegramDispatcher
from .feishu_dispatcher import FeishuDispatcher
from core.sanity.signal_guard import is_signal_already_sent, mark_signal_sent


class ProactiveNotifier:
    def __init__(
        self,
        telegram: Optional[TelegramDispatcher] = None,
        feishu: Optional[FeishuDispatcher] = None
    ):
        self.telegram = telegram or TelegramDispatcher()
        self.feishu = feishu or FeishuDispatcher()

    # -------------------------------------------------------------------------
    # 1. 每日交易决策卡 (Daily Trading Decision Card)
    # -------------------------------------------------------------------------
    def format_signal_card_markdown(
        self,
        date_str: str,
        nav: float,
        s5fi_val: float,
        actions: List[Dict[str, Any]],
        metrics: Optional[Dict[str, Any]] = None
    ) -> str:
        metrics_badge = ""
        if metrics:
            strat_ret = metrics.get('strat_ret_pct', 0.0)
            strat_cagr = metrics.get('strat_cagr', 0.0)
            curr_dd = metrics.get('curr_dd_pct', 0.0)
            max_dd = metrics.get('max_dd_pct', 0.0)
            sharpe = metrics.get('sharpe', 0.0)
            metrics_badge = (
                f"📈 策略实盘收益: **+{strat_ret:.2f}%** (CAGR: **+{strat_cagr:.2f}%**) | "
                f"回撤: **{curr_dd:.2f}%** (Max: **{max_dd:.2f}%**) | "
                f"夏普: **{sharpe:.2f}**\n"
            )

        if not actions:
            card = f"🟢 **【v2.29 盘后信号扫描与日终对账 - {date_str}】**\n\n"
            card += f"📊 账户估算总净值: **${nav:,.2f}**\n"
            card += f"📈 S5FI 宏观宽度: **{s5fi_val:.1f}%**\n"
            if metrics_badge:
                card += f"{metrics_badge}\n"
            else:
                card += "\n"
            card += "✅ **今日无新增买入/卖出信号，全盘持仓按原策略稳定运行！**\n"
            card += "• 现金流底仓 (JEPQ 60% DRIP) 持续享红利复利\n"
            card += "• 闲置贴息池 (SGOV) 持续享 ~5.2% 无风险贴息\n"
            return card

        card = f"🚨 **【v2.29 实盘交易指令决策卡 - {date_str}】**\n\n"
        card += f"📊 账户基准 NAV: **${nav:,.2f}** | 宽度 S5FI: **{s5fi_val:.1f}%**\n"
        if metrics_badge:
            card += f"{metrics_badge}"
        card += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

        for idx, act in enumerate(actions, 1):
            is_sell = (act.get('action') == 'SELL')
            action_type = "🔴 卖出平仓" if is_sell else "🟢 买入建仓"
            funding_str = " (资金归集入 SGOV 闲置贴息池)" if is_sell else " (资金源：优先卖出变现 SGOV)"

            ticker = act.get('ticker')
            target_val = float(act.get('target_val', 0.0))
            shares = act.get('shares')
            shares_str = f" (`{shares:.2f}` 股)" if shares else ""

            card += f"**指令 {idx}**: {action_type} **`{ticker}`**{shares_str}\n"
            card += f"• 目标金额: **${target_val:,.2f}**{funding_str}\n"
            card += f"• 触发原因: {act.get('reason', '')}\n\n"

        card += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        card += "🔘 请在券商 App (老虎/嘉信) 完成下单后，系统将自动从 API 拉取成交对账。"
        return card

    def dispatch_signal_card(
        self,
        date_str: str,
        nav: float,
        s5fi_val: float,
        actions: List[Dict[str, Any]],
        dedup_check: bool = True,
        metrics: Optional[Dict[str, Any]] = None
    ) -> Dict[str, bool]:
        """Dispatch signal card to Telegram and Feishu with deduplication check."""
        filtered_actions = []
        if dedup_check:
            for act in actions:
                t = act.get('ticker', '')
                a = act.get('action', '')
                if not is_signal_already_sent(date_str, t, a):
                    filtered_actions.append(act)
        else:
            filtered_actions = actions

        if actions and not filtered_actions and dedup_check:
            print(f"[Notifier] All {len(actions)} signals already dispatched today, skipping duplicate push.")
            return {"telegram": False, "feishu": False, "skipped_duplicate": True}

        text = self.format_signal_card_markdown(date_str, nav, s5fi_val, filtered_actions, metrics=metrics)
        color = "red" if filtered_actions and any(a.get('action') == 'SELL' for a in filtered_actions) else ("green" if filtered_actions else "blue")
        title = f"📢 交易决策卡: {len(filtered_actions)} 笔信号" if filtered_actions else "📊 每日扫描: 持仓正常运行"

        tg_ok = self.telegram.send_message(text)
        fs_ok = self.feishu.send_markdown(title=title, md_content=text, color=color)

        # Fallback protection: only mark sent if delivery succeeded (or neither channel configured in test/mock)
        is_mock = (not self.telegram.is_configured()) and (not self.feishu.is_configured())
        if dedup_check and (tg_ok or fs_ok or is_mock):
            for act in filtered_actions:
                mark_signal_sent(date_str, act.get('ticker', ''), act.get('action', ''), act.get('target_val', 0.0))

        return {"telegram": tg_ok, "feishu": fs_ok}

    # -------------------------------------------------------------------------
    # 2. 每日两层架构对账研报 (Daily Two-Layer Macro & Strategy Report)
    # -------------------------------------------------------------------------
    def dispatch_daily_report(
        self,
        date_str: str,
        total_equity: float,
        strategy_equity: float,
        hk_ipo_cum: float,
        cash: float,
        accounts_detail: List[Dict[str, Any]],
        drift_summary: List[str],
        metrics: Optional[Dict[str, Any]] = None,
        macro_metrics: Optional[Dict[str, Any]] = None,
        dedup_check: bool = False,
        signal_summary: Optional[str] = None
    ) -> Dict[str, bool]:
        if dedup_check and not drift_summary:
            if is_signal_already_sent(date_str, "SYSTEM_BRIEF", "DAILY_REPORT"):
                print(f"[Notifier] Daily Asset Brief already dispatched for {date_str} and zero position drift, staying silent.")
                return {"telegram": False, "feishu": False, "skipped_duplicate": True}

        report_total = macro_metrics.get("total_consolidated_equity", total_equity) if macro_metrics else total_equity

        text = f"🏦 **【多券商统一对账与家庭资产总研报 - {date_str}】**\n\n"
        if signal_summary:
            text += f"📡 **今日信号巡检**: {signal_summary}\n\n"

        # ---------------------------------------------------------------------
        # LAYER 1: 家庭全账户宏观大账本 (Family Wealth Macro Ledger)
        # ---------------------------------------------------------------------
        text += "🏛️ **【Layer 1: 家庭全账户宏观大账本】**\n"
        text += f"💰 **全账户资产总和**: **${report_total:,.2f}**\n"

        # Account details breakdown
        text += "📂 **各券商账户明细分布**:\n"
        for acc in accounts_detail:
            acc_name = acc.get('account_name', '券商账户')
            acc_name = re.sub(r'\s*\(?(?:638812|U9959007|56169533|[0-9]{5,}|U[0-9]{6,})\)?', '', acc_name).strip()
            acc_name = re.sub(r'\s*\(\s*\)', '', acc_name).strip()
            eq = acc.get('equity', 0.0)
            c_val = acc.get('cash', 0.0)
            m_val = acc.get('market_value', 0.0)
            v_val = acc.get('vault_balance', 0.0)
            d_val = acc.get('accrued_dividend', 0.0)
            l_val = acc.get('locked_funds', 0.0)

            extra_parts = []
            if m_val > 0:
                extra_parts.append(f"证券持仓: ${m_val:,.2f}")
            if d_val > 0:
                extra_parts.append(f"应计待派分红: +${d_val:,.2f}")
            if v_val > 0:
                extra_parts.append(f"老虎钱袋子: ${v_val:,.2f}")
            if c_val > 0:
                extra_parts.append(f"现金: ${c_val:,.2f}")
            if l_val > 0:
                extra_parts.append(f"冻结: ${l_val:,.2f}")

            detail_str = f" *({' | '.join(extra_parts)})*" if extra_parts else f" *(现金: ${c_val:,.2f})*"
            text += f"• **{acc_name}**: 资产 **${eq:,.2f}**{detail_str}\n"

        # Layer 1 Macro Performance & Capital Efficiency
        if macro_metrics:
            net_pnl = macro_metrics.get('cumulative_net_pnl', 0.0)
            moic = macro_metrics.get('moic_tvpi', 1.0)
            mwr = macro_metrics.get('mwr_xirr_pct', 0.0)
            ytd_pnl = macro_metrics.get('ytd_pnl', 0.0)
            ytd_ret = macro_metrics.get('ytd_ret_pct', 0.0)

            pnl_sign = "+" if net_pnl >= 0 else ""
            ytd_sign = "+" if ytd_pnl >= 0 else ""

            text += "\n💎 **历史赚钱能力与资本效率**:\n"
            text += f"• 累计绝对净创利 (Net PnL): **{pnl_sign}${net_pnl:,.2f}**\n"
            text += f"• 投入资本回报倍数 (MOIC / TVPI): **{moic:.2f}x** (历史每投入 $1 增值至 ${moic:.2f})\n"
            text += f"• 资金加权真实年化 (MWR / XIRR): **+{mwr:.2f}%**\n"
            text += f"• 2026 自然年内创利 (YTD): **{ytd_sign}${ytd_pnl:,.2f}** ({ytd_sign}{ytd_ret:.2f}%)\n"

            # Layer 1 Dimension 3: Passive Income & Financial Freedom (造血能力与被动现金流指标)
            ann_cf = macro_metrics.get('total_annual_passive_cashflow', 0.0)
            mo_cf = macro_metrics.get('monthly_passive_cashflow', 0.0)
            cf_yield = macro_metrics.get('cashflow_yield_pct', 0.0)
            j_div = macro_metrics.get('jepq_annual_div', 0.0)
            s_yield = macro_metrics.get('sgov_annual_yield', 0.0)
            v_yield = macro_metrics.get('vault_annual_yield', 0.0)

            text += "\n🏖️ **资产造血能力与财务自由度**:\n"
            text += f"• 预估年化被动现金流: **${ann_cf:,.2f} USD/年** (平均每月 **${mo_cf:,.2f} USD**)\n"
            text += f"  *(构成: JEPQ分红 ${j_div:,.2f} + SGOV美债贴息 ${s_yield:,.2f} + 钱袋子 ${v_yield:,.2f})*\n"
            text += f"• 综合资产现金流收益率: **{cf_yield:.2f}%**\n"
            text += f"• 自由度里程碑: 资产组合每月无需平仓任何持股，自动产生 **${mo_cf:,.2f}** 纯现金流！\n"

            # Layer 1 Financial Health & Liquidity
            buf_val = macro_metrics.get('liquidity_buffer_val', 0.0)
            buf_pct = macro_metrics.get('liquidity_buffer_pct', 0.0)
            lev_status = macro_metrics.get('leverage_status', '未使用杠杆 (负债 $0.00 / 极度安全)')

            text += "\n🛡️ **财务健康与安全垫**:\n"
            text += f"• 流动性安全垫 (现金+钱袋子+SGOV): **${buf_val:,.2f}** (全资产占比 **{buf_pct:.1f}%** - 充裕防守)\n"
            text += f"• 杠杆与风控状态: {lev_status}\n"

        # ---------------------------------------------------------------------
        # LAYER 2: v2.29 实盘量化主策略表现 (限定综合账户 638812)
        # ---------------------------------------------------------------------
        text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        text += "📈 **【Layer 2: v2.29 实盘量化主策略表现 (老虎综合 + 嘉信理财)】**\n"
        if hk_ipo_cum > 0 and strategy_equity > 0:
            pure_strat_eq = max(0.0, strategy_equity - hk_ipo_cum)
            text += f"• 实盘量化主策略总值: **${strategy_equity:,.2f}** (美股策略权益: **${pure_strat_eq:,.2f}** | 港股打新累计贡献: **+${hk_ipo_cum:,.2f}**)\n"
        elif strategy_equity > 0:
            text += f"• 量化策略总值 (老虎综合 + 嘉信理财): **${strategy_equity:,.2f}**\n"
        elif hk_ipo_cum > 0:
            text += f"• 港股打新累计贡献 (HK IPO PnL): **+${hk_ipo_cum:,.2f}**\n"

        if metrics:
            text += f"• 策略实盘净值收益率 (TWR): **+{metrics['strat_ret_pct']:.2f}%** (年化 CAGR: **+{metrics['strat_cagr']:.2f}%**)\n"
            text += f"• 历史最大回撤 (MaxDD): **{metrics['max_dd_pct']:.2f}%** (当前动态回撤: **{metrics['curr_dd_pct']:.2f}%**)\n"
            text += f"• 策略夏普比率 (Sharpe): **{metrics['sharpe']:.2f}** (基准无风险利率: 4.5%)\n"
            text += f"• 标普500对比超额 (Alpha): 领先 SPY **+{metrics['alpha_pct']:.2f}%** (SPY同期: +{metrics['spy_ret_pct']:.2f}%)\n"
            text += f"• 策略实盘周期: **{metrics['live_days']} 天** (基准起始: {metrics['start_date']} `${metrics['start_nav']:,.2f}`)\n"

        # ---------------------------------------------------------------------
        # DRIFT ALERT: 持仓偏差检查
        # ---------------------------------------------------------------------
        text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        if drift_summary:
            text += "⚠️ **持仓偏差提醒 (Drift Alert)**:\n"
            for d in drift_summary:
                text += f"{d}\n"
            text += "*(注：若为券商 DRIP 股息再投资或碎股，系统将在下次扫描自动平滑归集)*\n"
        else:
            text += "✅ **账实完全相符**: 券商 API 持仓与系统数据库 100% 对齐无偏差。\n"

        title = f"🏦 每日资产对账报告: ${report_total:,.2f}"
        tg_ok = self.telegram.send_message(text)
        fs_ok = self.feishu.send_markdown(title=title, md_content=text, color="blue")
        if dedup_check and (tg_ok or fs_ok) and not drift_summary:
            mark_signal_sent(date_str, "SYSTEM_BRIEF", "DAILY_REPORT", report_total)
        return {"telegram": tg_ok, "feishu": fs_ok}

    # -------------------------------------------------------------------------
    # 3. 技术告警与防错预警 (Technical Sanity Alert)
    # -------------------------------------------------------------------------
    def dispatch_technical_alert(self, title: str, issues: List[str]) -> Dict[str, bool]:
        text = f"⚠️ **【量化系统技术异常预警】**\n\n"
        text += f"**告警主题**: {title}\n"
        text += f"**发生时间**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        for idx, issue in enumerate(issues, 1):
            text += f"{idx}. {issue}\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        text += "💡 系统技术风控已自动拦截潜在错误，请检查网络或数据源！"

        tg_ok = self.telegram.send_message(text)
        fs_ok = self.feishu.send_markdown(title=f"⚠️ 技术风控告警: {title}", md_content=text, color="red")
        return {"telegram": tg_ok, "feishu": fs_ok}
