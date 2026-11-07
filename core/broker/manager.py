"""
Multi-Broker Portfolio Manager (core/broker/manager.py)
Unifies accounts across Tiger Brokers (Universal & Consolidated),
Charles Schwab, and Futu (HK IPO cash). Aggregates balances, combines positions
across migrating accounts, and fetches cross-broker order fills.
"""

import os
from typing import Dict, List, Optional, Any
import pandas as pd
from .base import BaseBrokerConnector, BrokerType, AccountBalance, PositionItem, FilledOrder, CashTransactionItem
from .tiger_connector import TigerBrokerConnector
from .schwab_connector import SchwabBrokerConnector
from .mock_connector import MockBrokerConnector
from core.sanity.signal_guard import get_canonical_layer


class MultiBrokerManager:
    def __init__(self, use_mock_if_no_keys: bool = True):
        self.connectors: Dict[str, BaseBrokerConnector] = {}
        self.use_mock_if_no_keys = use_mock_if_no_keys
        self._init_default_connectors()

    def _init_default_connectors(self):
        # 1. Tiger Brokers (supports single account or comma-separated multiple accounts)
        raw_tiger_accounts = os.getenv("TIGER_ACCOUNT", "").strip()
        tiger_accounts = [
            a.strip() for a in raw_tiger_accounts.split(",")
            if a.strip() and a.strip() != "TO_BE_FILLED"
        ]
        if not tiger_accounts:
            tiger_accounts = ["TIGER_UNIVERSAL", "TIGER_CONSOLIDATED"]

        tiger_connectors = []
        for idx, acc in enumerate(tiger_accounts, 1):
            if "U9959007" in acc or "UNIVERSAL" in acc.upper():
                acc_label = f"老虎证券 - 环球账户 ({acc})"
            elif "638812" in acc or "CONSOLIDATED" in acc.upper():
                acc_label = f"老虎证券 - 综合账户 ({acc})"
            else:
                acc_label = f"老虎证券 ({acc})"

            conn = TigerBrokerConnector(
                account_id=acc,
                account_name=acc_label
            )
            tiger_connectors.append(conn)
            self.register_connector(f"tiger_{idx}", conn)

        # 2. Charles Schwab Main Account
        schwab = SchwabBrokerConnector(
            account_name="Charles Schwab (嘉信理财)"
        )
        self.register_connector("schwab_main", schwab)

        # Check if any live credentials are functional
        has_any_live = (
            any(getattr(c, 'is_live_connected', lambda: False)() for c in tiger_connectors) or
            getattr(schwab, 'is_live_connected', lambda: False)()
        )

        if not has_any_live and self.use_mock_if_no_keys:
            # High-fidelity mock fallback matching portfolio.db
            mock_tiger = MockBrokerConnector(
                account_id="TIGER_LIVE_SIM",
                account_name="Tiger Brokers (实盘同步仿真通道)",
                broker=BrokerType.TIGER,
                initial_equity=132121.52,
                initial_cash=1617.84
            )
            self.register_connector("tiger_mock", mock_tiger)

    def register_connector(self, name: str, connector: BaseBrokerConnector):
        self.connectors[name] = connector

    def get_aggregated_balances(self) -> Dict[str, Any]:
        """Aggregate total equity and cash across all registered accounts."""
        total_equity = 0.0
        total_cash = 0.0
        total_mkt_val = 0.0
        total_vault_val = 0.0
        total_acc_div = 0.0
        total_acc_int = 0.0
        total_locked = 0.0
        total_buying_power = 0.0
        accounts_detail = []

        for name, conn in self.connectors.items():
            b = conn.get_account_balance()
            total_equity += b.total_equity
            total_cash += b.cash
            total_mkt_val += b.market_value
            total_vault_val += getattr(b, 'vault_balance', 0.0)
            total_acc_div += getattr(b, 'accrued_dividend', 0.0)
            total_acc_int += getattr(b, 'accrued_interest', 0.0)
            total_locked += getattr(b, 'locked_funds', 0.0)
            total_buying_power += getattr(b, 'buying_power', 0.0)

            accounts_detail.append({
                "connector": name,
                "account_name": b.account_name,
                "broker": b.broker.value,
                "equity": round(b.total_equity, 2),
                "cash": round(b.cash, 2),
                "market_value": round(b.market_value, 2),
                "vault_balance": round(getattr(b, 'vault_balance', 0.0), 2),
                "accrued_dividend": round(getattr(b, 'accrued_dividend', 0.0), 2),
                "accrued_interest": round(getattr(b, 'accrued_interest', 0.0), 2),
                "locked_funds": round(getattr(b, 'locked_funds', 0.0), 2),
                "buying_power": round(getattr(b, 'buying_power', 0.0), 2),
                "excess_liquidity": round(getattr(b, 'excess_liquidity', 0.0), 2)
            })

        return {
            "total_equity": round(total_equity, 2),
            "total_cash": round(total_cash, 2),
            "total_market_value": round(total_mkt_val, 2),
            "total_vault_balance": round(total_vault_val, 2),
            "total_accrued_dividend": round(total_acc_div, 2),
            "total_accrued_interest": round(total_acc_int, 2),
            "total_locked_funds": round(total_locked, 2),
            "total_buying_power": round(total_buying_power, 2),
            "accounts": accounts_detail
        }

    def get_aggregated_positions(self) -> pd.DataFrame:
        """
        Aggregate positions from all accounts.
        If a ticker is held in multiple accounts, merges total shares
        and computes weighted average cost basis.
        """
        records: Dict[str, Dict[str, Any]] = {}

        for name, conn in self.connectors.items():
            pos_list = conn.get_positions()
            for p in pos_list:
                ticker = p.ticker.upper().strip()
                if ticker not in records:
                    records[ticker] = {
                        "ticker": ticker,
                        "shares": 0.0,
                        "total_cost": 0.0,
                        "market_value": 0.0,
                        "market_price": p.market_price,
                        "layer": get_canonical_layer(ticker, p.layer),
                        "accounts": []
                    }
                r = records[ticker]
                r["shares"] += p.shares
                r["total_cost"] += (p.shares * p.cost_basis)
                r["market_value"] += p.market_value
                r["accounts"].append(f"{conn.get_account_balance().account_name} ({p.shares})")

        rows = []
        for ticker, data in records.items():
            shares = data["shares"]
            cost_basis = round(data["total_cost"] / shares, 4) if shares > 0 else 0.0
            rows.append({
                "ticker": ticker,
                "shares": round(shares, 4),
                "cost_basis": cost_basis,
                "market_price": data["market_price"],
                "market_value": round(data["market_value"], 2),
                "layer": data["layer"],
                "accounts": ", ".join(data["accounts"])
            })

        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values(by="market_value", ascending=False).reset_index(drop=True)
        return df

    def get_all_filled_orders(self, start_date: Optional[str] = None) -> List[FilledOrder]:
        """Collect all filled orders across all broker accounts."""
        all_orders: List[FilledOrder] = []
        for conn in self.connectors.values():
            orders = conn.get_filled_orders(start_date=start_date)
            all_orders.extend(orders)

        # Sort chronologically
        all_orders.sort(key=lambda o: o.filled_at, reverse=True)
        return all_orders

    def get_all_cash_transactions(self, start_date: Optional[str] = None) -> List[CashTransactionItem]:
        """Fetch and combine cash deposits/withdrawals across all registered brokers."""
        all_txs: List[CashTransactionItem] = []
        for name, conn in self.connectors.items():
            try:
                txs = conn.get_cash_transactions(start_date=start_date)
                all_txs.extend(txs)
            except Exception as e:
                print(f"Warning: Failed to fetch cash transactions from connector {name}: {e}")
        return all_txs
