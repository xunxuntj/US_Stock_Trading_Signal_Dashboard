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
            from tigeropen.tiger_open_config import TigerOpenClientConfig
            from tigeropen.trade.trade_client import TradeClient

            client_config = TigerOpenClientConfig(sandbox_debug=self.is_sandbox)
            client_config.tiger_id = str(self.tiger_id).strip()
            client_config.account = str(self.account_id).strip()

            pk_val = str(self.private_key_path).strip() if self.private_key_path else ""
            if os.path.exists(pk_val):
                with open(pk_val, "r", encoding="utf-8") as f:
                    pk_val = f.read().strip()

            # Tiger SDK expects pure base64 key string with PEM headers stripped
            clean_key = (
                pk_val.replace("-----BEGIN RSA PRIVATE KEY-----", "")
                .replace("-----END RSA PRIVATE KEY-----", "")
                .replace("-----BEGIN PRIVATE KEY-----", "")
                .replace("-----END PRIVATE KEY-----", "")
                .strip()
            )
            client_config.private_key = clean_key

            self._client = TradeClient(client_config)
            print(f"✅ Tiger TradeClient initialized for account {self.account_id} (Tiger ID: {self.tiger_id})")
        except Exception as e:
            print(f"⚠️ Tiger client init failed for account {self.account_id}: {e}")
            self._client = None

    def is_live_connected(self) -> bool:
        """Return True if real TigerOpen SDK client is configured and authenticated."""
        return self._client is not None

    def get_account_balance(self) -> AccountBalance:
        if self._client:
            try:
                asset_obj = None
                try:
                    asset_obj = self._client.get_assets(account=self.account_id)
                except Exception:
                    pass
                if not asset_obj:
                    try:
                        asset_obj = self._client.get_prime_assets(account=self.account_id)
                    except Exception:
                        pass

                if asset_obj and len(asset_obj) > 0:
                    a = asset_obj[0]
                    total_eq = float(getattr(a, 'net_liquidation', 0.0) or getattr(a, 'total_equity', 0.0) or 0.0)
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
                    raw_sym = getattr(p, 'symbol', None)
                    if not raw_sym and hasattr(p, 'contract'):
                        raw_sym = getattr(p.contract, 'symbol', '')
                    symbol = str(raw_sym or '').upper().strip()
                    if not symbol:
                        continue

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
                    order_id = str(getattr(o, 'order_id', getattr(o, 'id', '')))
                    raw_sym = getattr(o, 'symbol', None)
                    if not raw_sym and hasattr(o, 'contract'):
                        raw_sym = getattr(o.contract, 'symbol', '')
                    symbol = str(raw_sym or '').upper().strip()
                    if not symbol:
                        continue

                    action = str(getattr(o, 'action', 'BUY')).upper()
                    filled_qty = float(getattr(o, 'filled_quantity', getattr(o, 'filled', 0.0)) or 0.0)
                    avg_fill_price = float(getattr(o, 'avg_fill_price', 0.0) or 0.0)
                    commission = float(getattr(o, 'commission', 0.0) or 0.0)
                    fill_time = str(getattr(o, 'trade_time', getattr(o, 'order_time', '')))

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
