"""
Unified Proactive Notification Dispatcher (core/notifier/dispatcher.py)
Orchestrates multi-channel push across Telegram Bot and Feishu Robot.
Provides standard templates for:
1. Daily Trading Decision Cards (交易决策卡)
2. Multi-Broker Account NAV & Drift Reports (账户对账研报)
3. Technical Anomaly & Data Alerts (技术告警卡)
"""

from typing import Dict, List, Optional, Any
import datetime
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
            metrics_badge = (
                f"📈 策略实盘收益: **+{metrics['strat_ret_pct']:.2f}%** (CAGR: **+{metrics['strat_cagr']:.2f}%**) | "
                f"回撤: **{metrics['curr_dd_pct']:.2f}%** (Max: **{metrics['max_dd_pct']:.2f}%**) | "
                f"夏普: **{metrics['sharpe']:.2f}**\n"
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
                    mark_signal_sent(date_str, t, a, act.get('target_val', 0.0))
        else:
            filtered_actions = actions

        # If actions were present but all already sent today, skip duplicate notification
        if actions and not filtered_actions and dedup_check:
            print(f"[Notifier] All {len(actions)} signals already dispatched today, skipping duplicate push.")
            return {"telegram": False, "feishu": False, "skipped_duplicate": True}

        text = self.format_signal_card_markdown(date_str, nav, s5fi_val, filtered_actions, metrics=metrics)
        color = "red" if filtered_actions and any(a.get('action') == 'SELL' for a in filtered_actions) else ("green" if filtered_actions else "blue")
        title = f"📢 交易决策卡: {len(filtered_actions)} 笔信号" if filtered_actions else "📊 每日扫描: 持仓正常运行"

        tg_ok = self.telegram.send_message(text)
        fs_ok = self.feishu.send_markdown(title=title, md_content=text, color=color)

        return {"telegram": tg_ok, "feishu": fs_ok}

    # -------------------------------------------------------------------------
    # 2. 每日综合对账研报 (Daily Multi-Broker Reconcile Report)
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
        metrics: Optional[Dict[str, Any]] = None
    ) -> Dict[str, bool]:
        text = f"🏦 **【多券商统一对账与资产报告 - {date_str}】**\n\n"
        text += f"💰 **全账户资产总和**: **${total_equity:,.2f}**\n"
        text += f"• 美股策略权益 (Strategy Equity): **${strategy_equity:,.2f}**\n"
        text += f"• 港股打新累计贡献 (HK IPO PnL): **${hk_ipo_cum:,.2f}**\n"
        text += f"• 可用现金总计 (Cash Balance): **${cash:,.2f}**\n\n"

        text += "📂 **各券商账户分布**:\n"
        for acc in accounts_detail:
            text += f"• {acc['account_name']}: 资产 **${acc['equity']:,.2f}** (现金: ${acc['cash']:,.2f})\n"

        if metrics:
            text += "\n📈 **v2.29 策略核心收益指标**:\n"
            text += f"• 策略实盘收益率: **+{metrics['strat_ret_pct']:.2f}%** (年化 CAGR: **+{metrics['strat_cagr']:.2f}%**)\n"
            text += f"• 全账户总收益率: **+{metrics['total_ret_pct']:.2f}%** (年化 CAGR: **+{metrics['total_cagr']:.2f}%**)\n"
            text += f"• 历史最大回撤 (MaxDD): **{metrics['max_dd_pct']:.2f}%** (当前动态回撤: **{metrics['curr_dd_pct']:.2f}%**)\n"
            text += f"• 策略夏普比率 (Sharpe): **{metrics['sharpe']:.2f}** (无风险利率: 4.5%)\n"
            text += f"• 标普500对比超额 (Alpha): 领先 SPY **+{metrics['alpha_pct']:.2f}%** (SPY同期: +{metrics['spy_ret_pct']:.2f}%)\n"
            text += f"• 实盘持续跟踪: **{metrics['live_days']} 天** (基准起始: {metrics['start_date']} `${metrics['start_nav']:,.2f}`)\n"

        if drift_summary:
            text += "\n⚠️ **持仓偏差提醒 (Drift Alert)**:\n"
            for d in drift_summary:
                text += f"{d}\n"
            text += "*(注：若为券商 DRIP 股息再投资或碎股，系统将在下次扫描自动平滑归集)*\n"
        else:
            text += "\n✅ **账实完全相符**: 券商 API 持仓与系统数据库 100% 对齐无偏差。\n"

        title = f"🏦 每日资产对账报告: ${total_equity:,.2f}"
        tg_ok = self.telegram.send_message(text)
        fs_ok = self.feishu.send_markdown(title=title, md_content=text, color="blue")
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
