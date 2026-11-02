"""
Tiger Brokers OpenAPI Connector (core/broker/tiger_connector.py)
Connects to TigerOpen API for Tiger Universal Account and Consolidated Account.
Supports reading real-time balances, multi-asset positions, and filled orders.
Gracefully handles missing credentials or offline execution with clear diagnostics.
"""

import os
import datetime
from typing import List, Optional, Dict, Any
from .base import BaseBrokerConnector, BrokerType, AccountBalance, PositionItem, FilledOrder
from core.sanity.signal_guard import get_canonical_layer


class TigerBrokerConnector(BaseBrokerConnector):
    def __init__(
        self,
        account_id: Optional[str] = None,
        account_name: str = "Tiger Universal",
        tiger_id: Optional[str] = None,
        private_key_path: Optional[str] = None,
        is_sandbox: bool = False
    ):
        self.account_id = account_id or os.getenv("TIGER_ACCOUNT", "TIGER_DEFAULT_ACC")
        self.account_name = account_name
        self.tiger_id = tiger_id or os.getenv("TIGER_ID")
        self.private_key_path = private_key_path or os.getenv("TIGER_PRIVATE_KEY_PATH")
        self.is_sandbox = is_sandbox
        self.broker = BrokerType.TIGER
        self._client = None
        self._init_client()

    def _init_client(self):
        """Attempts to initialize tigeropen SDK client if available."""
        if not self.tiger_id or not self.private_key_path or self.tiger_id == "TO_BE_FILLED":
            return

        try:
            from tigeropen.common.util.signature_utils import read_private_key
            from tigeropen.tiger_open_config import TigerOpenConfig
            from tigeropen.trade.trade_client import TradeClient

            client_config = TigerOpenConfig(sandbox_debug=self.is_sandbox)
            client_config.tiger_id = self.tiger_id
            client_config.account = self.account_id
            
            pk_val = self.private_key_path.strip() if self.private_key_path else ""
            if "-----BEGIN" in pk_val:
                client_config.private_key = pk_val
            elif os.path.exists(pk_val):
                client_config.private_key = read_private_key(pk_val)

            self._client = TradeClient(client_config)
        except Exception as e:
            # SDK not installed or keys invalid
            self._client = None

    def is_live_connected(self) -> bool:
        """Return True if real TigerOpen SDK client is configured and authenticated."""
        return self._client is not None

    def get_account_balance(self) -> AccountBalance:
        if self._client:
            try:
                asset_obj = self._client.get_assets(account=self.account_id)
                if asset_obj and len(asset_obj) > 0:
                    a = asset_obj[0]
                    total_eq = float(getattr(a, 'net_liquidation', 0.0) or 0.0)
                    cash_val = float(getattr(a, 'cash_balance', 0.0) or getattr(a, 'cash', 0.0) or 0.0)
                    mkt_val = total_eq - cash_val
                    return AccountBalance(
                        account_id=self.account_id,
                        broker=self.broker,
                        account_name=self.account_name,
                        total_equity=total_eq,
                        cash=cash_val,
                        market_value=mkt_val
                    )
            except Exception as e:
                print(f"Warning: Tiger API get_assets failed ({e}), using fallback")

        # Fallback when credentials aren't live yet
        return AccountBalance(
            account_id=self.account_id,
            broker=self.broker,
            account_name=self.account_name,
            total_equity=0.0,
            cash=0.0,
            market_value=0.0
        )

    def get_positions(self) -> List[PositionItem]:
        results: List[PositionItem] = []
        if self._client:
            try:
                pos_list = self._client.get_positions(account=self.account_id)
                for p in pos_list:
                    symbol = str(getattr(p, 'symbol', '')).upper()
                    quantity = float(getattr(p, 'quantity', 0.0) or 0.0)
                    if quantity <= 0.0001:
                        continue
                    cost_basis = float(getattr(p, 'average_cost', 0.0) or 0.0)
                    market_price = float(getattr(p, 'market_price', cost_basis) or cost_basis)
                    market_val = float(getattr(p, 'market_value', quantity * market_price) or quantity * market_price)

                    results.append(PositionItem(
                        account_id=self.account_id,
                        broker=self.broker,
                        ticker=symbol,
                        shares=quantity,
                        cost_basis=cost_basis,
                        market_price=market_price,
                        market_value=market_val,
                        layer=get_canonical_layer(symbol)
                    ))
                return results
            except Exception as e:
                print(f"Warning: Tiger API get_positions failed ({e})")

        return results

    def get_filled_orders(self, start_date: Optional[str] = None) -> List[FilledOrder]:
        orders: List[FilledOrder] = []
        if self._client:
            try:
                # Query historical filled orders
                tiger_orders = self._client.get_filled_orders(account=self.account_id)
                for o in tiger_orders:
                    order_id = str(getattr(o, 'order_id', ''))
                    symbol = str(getattr(o, 'symbol', '')).upper()
                    action = str(getattr(o, 'action', 'BUY')).upper()
                    filled_qty = float(getattr(o, 'filled_quantity', 0.0) or 0.0)
                    avg_fill_price = float(getattr(o, 'avg_fill_price', 0.0) or 0.0)
                    commission = float(getattr(o, 'commission', 0.0) or 0.0)
                    fill_time = str(getattr(o, 'trade_time', getattr(o, 'updated_time', '')))

                    orders.append(FilledOrder(
                        order_id=order_id,
                        account_id=self.account_id,
                        broker=self.broker,
                        ticker=symbol,
                        action=action,
                        shares=filled_qty,
                        price=avg_fill_price,
                        total_value=filled_qty * avg_fill_price,
                        fee=commission,
                        filled_at=fill_time,
                        status="FILLED"
                    ))
            except Exception as e:
                print(f"Warning: Tiger API get_filled_orders failed ({e})")

        return orders
