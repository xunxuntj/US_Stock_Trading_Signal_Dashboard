"""
Base Broker Connector & Data Contracts (core/broker/base.py)
Defines standard models for multi-account portfolio aggregation across
Tiger Brokers (Universal & Consolidated), Charles Schwab, and Futu HK IPO.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any
import datetime


class BrokerType(str, Enum):
    TIGER = "TIGER"
    SCHWAB = "SCHWAB"
    FUTU = "FUTU"
    MOCK = "MOCK"


@dataclass
class AccountBalance:
    account_id: str
    broker: BrokerType
    account_name: str
    total_equity: float
    cash: float
    market_value: float
    currency: str = "USD"
    accrued_dividend: float = 0.0     # 应计待到账分红
    accrued_interest: float = 0.0     # 应计利息
    vault_balance: float = 0.0        # 老虎钱袋子 / 基金总资产 (货币基金)
    locked_funds: float = 0.0         # 冻结资金
    buying_power: float = 0.0         # 可用购买力
    excess_liquidity: float = 0.0     # 剩余流动性
    updated_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


@dataclass
class PositionItem:
    account_id: str
    broker: BrokerType
    ticker: str
    shares: float
    cost_basis: float
    market_price: float
    market_value: float
    layer: Optional[str] = None
    currency: str = "USD"
    updated_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


@dataclass
class FilledOrder:
    order_id: str
    account_id: str
    broker: BrokerType
    ticker: str
    action: str  # BUY / SELL
    shares: float
    price: float
    total_value: float
    fee: float = 0.0
    filled_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    status: str = "FILLED"
    remark: Optional[str] = None



@dataclass
class CashTransactionItem:
    transaction_id: str
    account_id: str
    broker: BrokerType
    date: str          # YYYY-MM-DD
    type: str          # DEPOSIT / WITHDRAWAL
    amount: float      # Positive float
    description: str = ""
    raw_type: str = ""


class BaseBrokerConnector(ABC):
    """Abstract interface that every broker connector must implement."""

    @abstractmethod
    def get_account_balance(self) -> AccountBalance:
        """Fetch real-time account equity and cash balance."""
        pass

    @abstractmethod
    def get_positions(self) -> List[PositionItem]:
        """Fetch currently held positions."""
        pass

    @abstractmethod
    def get_filled_orders(self, start_date: Optional[str] = None) -> List[FilledOrder]:
        """Fetch executed filled orders since start_date (YYYY-MM-DD)."""
        pass

    def get_cash_transactions(self, start_date: Optional[str] = None) -> List[CashTransactionItem]:
        """Fetch cash deposits and withdrawals since start_date (YYYY-MM-DD). Default empty."""
        return []
