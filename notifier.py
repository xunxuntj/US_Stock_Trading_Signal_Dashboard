import os
import datetime

def format_telegram_card(date_str, nav, s5fi_val, actions):
    """ Formats v2.29 Action Card for Telegram / Push Notification """
    if not actions:
        card = f"🟢 **【v2.29 日终对账与信号扫描 - {date_str}】**\n\n"
        card += f"📊 账户当前估算 NAV: **${nav:,.2f}**\n"
        card += f"📈 S5FI 宏观宽度: **{s5fi_val:.1f}%**\n"
        card += "✅ **今日无新买入/卖出信号，全盘持仓按原策略稳定运行！**"
        return card
        
    card = f"🚨 **【v2.29 实盘交易指令卡 - {date_str}】**\n\n"
    card += f"📊 账户当前 NAV: **${nav:,.2f}** | S5FI 宽度: **{s5fi_val:.1f}%**\n"
    card += "-----------------------------------------\n"
    
    for idx, act in enumerate(actions, 1):
        action_type = "🔴 卖出平仓" if act['action'] == 'SELL' else "🟢 买入建仓"
        funding_str = " (资金归集入 SGOV 闲置贴息)" if act['action'] == 'SELL' else " (资金源：优先卖出变现 SGOV)"
        
        card += f"**指令 {idx}**: {action_type} **`{act['ticker']}`**\n"
        card += f"• 目标金额: **${act['target_val']:,.2f}**{funding_str}\n"
        card += f"• 触发原因: {act['reason']}\n\n"
        
    card += "-----------------------------------------\n"
    card += "🔘 请在券商 App 完成手工下单后，登录 Web 仪表盘点击 [一键对账同步]。"
    return card

def send_notification(card_text):
    """ Printing notification card to console / log file """
    print("\n=======================================================")
    print(" NOTIFICATION CARD (TELEGRAM / EMAIL / WEB)")
    print("=======================================================")
    print(card_text)
    print("=======================================================\n")
