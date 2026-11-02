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
