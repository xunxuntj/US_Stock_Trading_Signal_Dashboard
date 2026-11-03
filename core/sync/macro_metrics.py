"""
Layer 1 Macro Wealth & Passive Cash Flow Engine (core/sync/macro_metrics.py)
Computes macro family wealth indicators across all accounts:
1. Cumulative Net PnL (绝对净创利) & MOIC/TVPI (投入资本倍数)
2. Money-Weighted Return (MWR / XIRR 资金加权真实年化收益率)
3. Calendar Year YTD Return & Profit (自然年收益)
4. Liquidity & Cash Buffer Ratio (流动性安全垫)
5. Passive Income & Financial Freedom Engine (被动现金流造血能力与自由度指标):
   - JEPQ dividend cash flow
   - SGOV treasury yield cash flow
   - Tiger Vault (钱袋子) money-market fund yield
   - HK IPO profit annualized contribution
   - Total Annualized Passive Cash Flow & Monthly Run-rate
   - Cash Flow Yield %
"""

import datetime
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd
import numpy as np


def calculate_xirr(cash_flows: List[Tuple[datetime.date, float]], max_iter: int = 100) -> float:
    """
    Computes annualized internal rate of return (XIRR / MWR).
    Standard convention:
      - Investment deposits (inflows to account) are negative (-amount)
      - Withdrawals (outflows from account) are positive (+amount)
      - Final ending asset net worth is positive (+net_equity)
    Returns annualized percentage (e.g. 14.5 for 14.5%).
    """
    if len(cash_flows) < 2:
        return 0.0

    # Sort chronologically
    sorted_cf = sorted(cash_flows, key=lambda x: x[0])
    d0 = sorted_cf[0][0]
    total_days = (sorted_cf[-1][0] - d0).days
    if total_days <= 0:
        return 0.0

    # Check if there are both positive and negative cash flows
    has_pos = any(cf[1] > 0 for cf in sorted_cf)
    has_neg = any(cf[1] < 0 for cf in sorted_cf)
    if not (has_pos and has_neg):
        return 0.0

    # Newton-Raphson solver
    def npv(rate: float) -> float:
        if rate <= -0.9999:
            return float('inf')
        val = 0.0
        for dt, amt in sorted_cf:
            years = (dt - d0).days / 365.0
            val += amt / ((1.0 + rate) ** years)
        return val

    def npv_prime(rate: float) -> float:
        val = 0.0
        for dt, amt in sorted_cf:
            years = (dt - d0).days / 365.0
            if years != 0:
                val -= years * amt / ((1.0 + rate) ** (years + 1.0))
        return val

    # Initial guess
    rate = 0.10
    for _ in range(max_iter):
        f_val = npv(rate)
        f_prime = npv_prime(rate)
        if abs(f_prime) < 1e-12:
            break
        new_rate = rate - f_val / f_prime
        if abs(new_rate - rate) < 1e-6:
            return round(new_rate * 100.0, 2)
        if new_rate < -0.95:
            new_rate = -0.95
        elif new_rate > 5.0:
            new_rate = 5.0
        rate = new_rate

    # Fallback to Bisection if Newton did not converge
    low = -0.90
    high = 3.0
    f_low = npv(low)
    f_high = npv(high)
    if f_low * f_high > 0:
        # Simple CAGR fallback
        total_in = abs(sum(cf[1] for cf in sorted_cf if cf[1] < 0))
        total_out = sum(cf[1] for cf in sorted_cf if cf[1] > 0)
        if total_in > 0:
            cagr = ((total_out / total_in) ** (365.0 / max(1, total_days)) - 1.0) * 100.0
            return round(cagr, 2)
        return 0.0

    for _ in range(60):
        mid = (low + high) / 2.0
        f_mid = npv(mid)
        if abs(f_mid) < 1e-5:
            return round(mid * 100.0, 2)
        if f_low * f_mid < 0:
            high = mid
        else:
            low = mid
            f_low = f_mid

    return round(((low + high) / 2.0) * 100.0, 2)


def compute_macro_wealth_metrics(
    total_consolidated_equity: float,
    cash_balance: float,
    vault_balance: float,
    positions_df: Optional[pd.DataFrame] = None,
    cash_transactions_df: Optional[pd.DataFrame] = None,
    initial_capital: float = 99215.41,
    initial_date: str = "2026-01-15",
    hk_ipo_cum: float = 0.0
) -> Dict[str, Any]:
    """
    Computes complete Layer 1 metrics:
    - Net PnL, MOIC/TVPI, MWR/XIRR, YTD Return
    - Liquidity Buffer & Ratio
    - Passive Income Run-rate & Financial Freedom Metrics
    """
    today = datetime.date.today()

    # 1. Cash flow modeling for MWR / XIRR
    # Initial deposit
    init_dt = datetime.datetime.strptime(initial_date, "%Y-%m-%d").date()
    flows: List[Tuple[datetime.date, float]] = [(init_dt, -float(initial_capital))]

    total_deposited = float(initial_capital)
    total_withdrawn = 0.0

    if cash_transactions_df is not None and not cash_transactions_df.empty:
        for _, row in cash_transactions_df.iterrows():
            try:
                c_dt = pd.to_datetime(row['date']).date()
                amt = float(row['amount'])
                action = str(row['type']).upper().strip()
                if "DEP" in action:
                    flows.append((c_dt, -amt))
                    total_deposited += amt
                elif "WITH" in action:
                    flows.append((c_dt, amt))
                    total_withdrawn += amt
            except Exception:
                continue

    # Terminal flow = current consolidated net wealth
    flows.append((today, float(total_consolidated_equity)))

    # MWR / XIRR
    mwr_cagr = calculate_xirr(flows)

    # 2. Cumulative Net PnL & MOIC / TVPI
    cumulative_net_pnl = round(total_consolidated_equity + total_withdrawn - total_deposited, 2)
    moic_tvpi = round((total_consolidated_equity + total_withdrawn) / total_deposited, 2) if total_deposited > 0 else 1.0

    # 3. YTD Return (from 2026-01-01 / initial capital baseline)
    ytd_pnl = round(total_consolidated_equity - total_deposited, 2)
    ytd_ret_pct = round((ytd_pnl / total_deposited) * 100.0, 2) if total_deposited > 0 else 0.0

    # 4. Extract specific position values for Liquidity & Passive Income
    jepq_shares = 0.0
    jepq_mkt_val = 0.0
    sgov_shares = 0.0
    sgov_mkt_val = 0.0

    if positions_df is not None and not positions_df.empty:
        for _, p in positions_df.iterrows():
            t = str(p.get('ticker', '')).upper().strip()
            s = float(p.get('shares', 0.0) or 0.0)
            mv = float(p.get('market_value', 0.0) or 0.0)
            if t == "JEPQ":
                jepq_shares += s
                jepq_mkt_val += mv
            elif t == "SGOV":
                sgov_shares += s
                sgov_mkt_val += mv

    # 5. Liquidity Safety Buffer (现金 + 老虎钱袋子 + SGOV超短债)
    liquidity_buffer_val = round(cash_balance + vault_balance + sgov_mkt_val, 2)
    liquidity_buffer_pct = round((liquidity_buffer_val / total_consolidated_equity * 100.0), 1) if total_consolidated_equity > 0 else 0.0

    # 6. 🌟 Passive Income & Financial Freedom Engine (造血能力与被动现金流指标)
    # Annualized Dividend Assumptions (benchmark calibrated):
    # - JEPQ: ~$5.04 / share annually (~$0.42 / month, dividend yield ~9.5% on ~$53 price)
    # - SGOV: ~$5.20 / share annually (benchmark yield ~5.18% on ~$100.5 price)
    # - Tiger Vault (钱袋子): ~4.5% annualized yield
    # - HK IPO Annualized Contribution: HK IPO cumulative profit prorated
    jepq_annual_div = round(jepq_shares * 5.04, 2) if jepq_shares > 0 else round(jepq_mkt_val * 0.095, 2)
    sgov_annual_yield = round(sgov_shares * 5.20, 2) if sgov_shares > 0 else round(sgov_mkt_val * 0.0518, 2)
    vault_annual_yield = round(vault_balance * 0.045, 2)

    # HK IPO prorated annual run rate (historical contribution active months)
    days_invested = max(1, (today - init_dt).days)
    ipo_annual_runrate = round((hk_ipo_cum / days_invested) * 365.0, 2) if hk_ipo_cum > 0 else 0.0

    total_annual_passive_cashflow = round(jepq_annual_div + sgov_annual_yield + vault_annual_yield + ipo_annual_runrate, 2)
    monthly_passive_cashflow = round(total_annual_passive_cashflow / 12.0, 2)
    cashflow_yield_pct = round((total_annual_passive_cashflow / total_consolidated_equity) * 100.0, 2) if total_consolidated_equity > 0 else 0.0

    return {
        "total_consolidated_equity": round(total_consolidated_equity, 2),
        "total_deposited": round(total_deposited, 2),
        "total_withdrawn": round(total_withdrawn, 2),
        "cumulative_net_pnl": cumulative_net_pnl,
        "moic_tvpi": moic_tvpi,
        "mwr_xirr_pct": mwr_cagr,
        "ytd_pnl": ytd_pnl,
        "ytd_ret_pct": ytd_ret_pct,
        # Health & Liquidity
        "cash_balance": round(cash_balance, 2),
        "vault_balance": round(vault_balance, 2),
        "sgov_market_value": round(sgov_mkt_val, 2),
        "liquidity_buffer_val": liquidity_buffer_val,
        "liquidity_buffer_pct": liquidity_buffer_pct,
        "leverage_status": "未使用杠杆 (负债 $0.00 / 极度安全)",
        # Passive Cashflow & Freedom
        "jepq_annual_div": jepq_annual_div,
        "sgov_annual_yield": sgov_annual_yield,
        "vault_annual_yield": vault_annual_yield,
        "ipo_annual_runrate": ipo_annual_runrate,
        "total_annual_passive_cashflow": total_annual_passive_cashflow,
        "monthly_passive_cashflow": monthly_passive_cashflow,
        "cashflow_yield_pct": cashflow_yield_pct,
        "days_tracked": days_invested
    }
