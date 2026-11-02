"""
Charles Schwab Trader API Connector (core/broker/schwab_connector.py)
Provides REST API connectivity for Charles Schwab brokerage accounts.
Supports gradual portfolio migration from Tiger to Schwab with automated
position aggregation and order fill ingestion.
"""

import os
import datetime
from typing import List, Optional, Dict, Any
import httpx
from .base import BaseBrokerConnector, BrokerType, AccountBalance, PositionItem, FilledOrder
from core.sanity.signal_guard import get_canonical_layer


class SchwabBrokerConnector(BaseBrokerConnector):
    SCHWAB_BASE_URL = "https://api.schwabapi.com/trader/v1"

    def __init__(
        self,
        app_key: Optional[str] = None,
        app_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
        account_number: Optional[str] = None,
        account_name: str = "Charles Schwab Main"
    ):
        self.app_key = app_key or os.getenv("SCHWAB_APP_KEY")
        self.app_secret = app_secret or os.getenv("SCHWAB_APP_SECRET")
        self.refresh_token = refresh_token or os.getenv("SCHWAB_REFRESH_TOKEN")
        self.account_id = account_number or os.getenv("SCHWAB_ACCOUNT_NUMBER", "SCHWAB_DEFAULT")
        self.account_name = account_name
        self.broker = BrokerType.SCHWAB
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime.datetime] = None

    def is_live_connected(self) -> bool:
        """Check if Schwab API credentials are configured."""
        return bool(
            self.app_key and self.refresh_token and
            self.app_key != "TO_BE_FILLED" and
            self.account_id not in ["SCHWAB_DEFAULT", "TO_BE_FILLED"]
        )

    def _ensure_access_token(self) -> Optional[str]:
        """Refreshes Schwab OAuth access token if expired."""
        if not self.is_live_connected():
            return None

        now = datetime.datetime.now()
        if self._access_token and self._token_expires_at and now < self._token_expires_at:
            return self._access_token

        try:
            token_url = "https://api.schwabapi.com/v1/oauth/token"
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            payload = {
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            }
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(token_url, data=payload, auth=(self.app_key, self.app_secret or ""))
                if resp.status_code == 200:
                    data = resp.json()
                    self._access_token = data.get("access_token")
                    expires_in = int(data.get("expires_in", 1800))
                    self._token_expires_at = now + datetime.timedelta(seconds=expires_in - 60)
                    return self._access_token
        except Exception as e:
            print(f"Warning: Schwab token refresh error: {e}")

        return None

    def get_account_balance(self) -> AccountBalance:
        token = self._ensure_access_token()
        if token:
            try:
                headers = {"Authorization": f"Bearer {token}"}
                url = f"{self.SCHWAB_BASE_URL}/accounts/{self.account_id}?fields=positions"
                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(url, headers=headers)
                    if resp.status_code == 200:
                        acc_data = resp.json().get("securitiesAccount", {})
                        balances = acc_data.get("currentBalances", {})
                        tot_eq = float(balances.get("liquidationValue", 0.0) or 0.0)
                        cash_val = float(balances.get("cashBalance", 0.0) or 0.0)
                        mkt_val = tot_eq - cash_val
                        return AccountBalance(
                            account_id=self.account_id,
                            broker=self.broker,
                            account_name=self.account_name,
                            total_equity=tot_eq,
                            cash=cash_val,
                            market_value=mkt_val
                        )
            except Exception as e:
                print(f"Warning: Schwab get_account_balance error: {e}")

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
        token = self._ensure_access_token()
        if token:
            try:
                headers = {"Authorization": f"Bearer {token}"}
                url = f"{self.SCHWAB_BASE_URL}/accounts/{self.account_id}?fields=positions"
                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(url, headers=headers)
                    if resp.status_code == 200:
                        acc_data = resp.json().get("securitiesAccount", {})
                        positions = acc_data.get("positions", [])
                        for p in positions:
                            inst = p.get("instrument", {})
                            sym = str(inst.get("symbol", "")).upper()
                            qty = float(p.get("longQuantity", 0.0) or 0.0)
                            if qty <= 0.0001:
                                continue
                            cost = float(p.get("averagePrice", 0.0) or 0.0)
                            mkt_val = float(p.get("marketValue", 0.0) or 0.0)
                            mkt_price = mkt_val / qty if qty > 0 else cost

                            results.append(PositionItem(
                                account_id=self.account_id,
                                broker=self.broker,
                                ticker=sym,
                                shares=qty,
                                cost_basis=cost,
                                market_price=mkt_price,
                                market_value=mkt_val,
                                layer=get_canonical_layer(sym)
                            ))
            except Exception as e:
                print(f"Warning: Schwab get_positions error: {e}")

        return results

    def get_filled_orders(self, start_date: Optional[str] = None) -> List[FilledOrder]:
        orders: List[FilledOrder] = []
        token = self._ensure_access_token()
        if token:
            try:
                headers = {"Authorization": f"Bearer {token}"}
                url = f"{self.SCHWAB_BASE_URL}/accounts/{self.account_id}/orders"
                params = {"status": "FILLED"}
                if start_date:
                    params["fromEnteredTime"] = f"{start_date}T00:00:00.000Z"

                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(url, headers=headers, params=params)
                    if resp.status_code == 200:
                        for o in resp.json():
                            order_id = str(o.get("orderId", ""))
                            activities = o.get("orderActivityCollection", [])
                            for act in activities:
                                if act.get("activityType") == "EXECUTION":
                                    leg = o.get("orderLegCollection", [{}])[0]
                                    inst = leg.get("instrument", {})
                                    sym = str(inst.get("symbol", "")).upper()
                                    instruction = str(leg.get("instruction", "BUY")).upper()
                                    filled_qty = float(act.get("executionLegs", [{}])[0].get("quantity", 0.0))
                                    fill_price = float(act.get("executionLegs", [{}])[0].get("price", 0.0))

                                    orders.append(FilledOrder(
                                        order_id=order_id,
                                        account_id=self.account_id,
                                        broker=self.broker,
                                        ticker=sym,
                                        action="BUY" if "BUY" in instruction else "SELL",
                                        shares=filled_qty,
                                        price=fill_price,
                                        total_value=filled_qty * fill_price,
                                        fee=0.0,
                                        filled_at=act.get("executionTime", "")
                                    ))
            except Exception as e:
                print(f"Warning: Schwab get_filled_orders error: {e}")

        return orders
