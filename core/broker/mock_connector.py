"""
Mock Broker Connector (core/broker/mock_connector.py)
Used for automated testing, local development, and shadow mode execution
without requiring live broker credentials or active network sessions.
"""

from typing import List, Optional
import datetime
from .base import BaseBrokerConnector, BrokerType, AccountBalance, PositionItem, FilledOrder


class MockBrokerConnector(BaseBrokerConnector):
    def __init__(
        self,
        account_id: str = "MOCK_ACC_01",
        account_name: str = "Tiger Universal (Mock)",
        broker: BrokerType = BrokerType.TIGER,
        initial_equity: float = 132000.0,
        initial_cash: float = 500.0
    ):
        self.account_id = account_id
        self.account_name = account_name
        self.broker = broker
        self.total_equity = initial_equity
        self.cash = initial_cash
        self.mock_positions: List[PositionItem] = [
            PositionItem(account_id=self.account_id, broker=self.broker, ticker="JEPQ", shares=1238.32, cost_basis=59.48, market_price=60.10, market_value=74423.0, layer="L0"),
            PositionItem(account_id=self.account_id, broker=self.broker, ticker="SGOV", shares=135.16, cost_basis=100.58, market_price=100.65, market_value=13603.8, layer="SGOV"),
            PositionItem(account_id=self.account_id, broker=self.broker, ticker="SPY", shares=29.0, cost_basis=774.08, market_price=775.50, market_value=22489.5, layer="L1"),
            PositionItem(account_id=self.account_id, broker=self.broker, ticker="QQQ", shares=16.0, cost_basis=726.21, market_price=730.10, market_value=11681.6, layer="L1"),
            PositionItem(account_id=self.account_id, broker=self.broker, ticker="SOXX", shares=18.0, cost_basis=554.78, market_price=558.20, market_value=10047.6, layer="L1"),
            PositionItem(account_id=self.account_id, broker=self.broker, ticker="QLD", shares=111.0, cost_basis=90.44, market_price=92.15, market_value=10228.6, layer="L2"),
            PositionItem(account_id=self.account_id, broker=self.broker, ticker="DBC", shares=406.0, cost_basis=30.11, market_price=30.50, market_value=12383.0, layer="Non-Equity"),
        ]
        self.mock_orders: List[FilledOrder] = []

    def get_account_balance(self) -> AccountBalance:
        mkt_val = sum(p.market_value for p in self.mock_positions)
        return AccountBalance(
            account_id=self.account_id,
            broker=self.broker,
            account_name=self.account_name,
            total_equity=mkt_val + self.cash,
            cash=self.cash,
            market_value=mkt_val
        )

    def get_positions(self) -> List[PositionItem]:
        return list(self.mock_positions)

    def get_filled_orders(self, start_date: Optional[str] = None) -> List[FilledOrder]:
        return list(self.mock_orders)

    def add_mock_order(self, order: FilledOrder):
        self.mock_orders.append(order)
