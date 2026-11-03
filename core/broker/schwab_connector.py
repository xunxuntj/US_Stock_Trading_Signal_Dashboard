"""
Charles Schwab Trader API Connector (core/broker/schwab_connector.py)
Provides REST API connectivity for Charles Schwab brokerage accounts.
Supports reading real-time balances, multi-asset positions, and filled orders.
Automatically discovers account hash values via /accounts/accountNumbers.
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
        account_name: str = "Charles Schwab (嘉信理财)"
    ):
        self.app_key = app_key or os.getenv("SCHWAB_APP_KEY")
        self.app_secret = app_secret or os.getenv("SCHWAB_APP_SECRET")
        self.refresh_token = refresh_token or os.getenv("SCHWAB_REFRESH_TOKEN")
        self.account_id = account_number or os.getenv("SCHWAB_ACCOUNT_NUMBER", "")
        self.account_name = account_name
        self.broker = BrokerType.SCHWAB
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime.datetime] = None
        self._account_hash: Optional[str] = None

    def is_live_connected(self) -> bool:
        """Check if Schwab API credentials are configured."""
        return bool(
            self.app_key and self.refresh_token and
            self.app_key != "TO_BE_FILLED" and
            self.refresh_token != "TO_BE_FILLED" and
            not self.refresh_token.startswith("C0.")
        )

    def _get_proxy(self) -> Optional[str]:
        if not os.getenv("GITHUB_ACTIONS"):
            p_val = os.getenv("TELEGRAM_PROXY_URL")
            if p_val and "socks" not in p_val:
                return p_val
            elif p_val:
                return p_val
        return None

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
            with httpx.Client(timeout=15.0, proxy=self._get_proxy()) as client:
                resp = client.post(token_url, data=payload, auth=(self.app_key, self.app_secret or ""))
                if resp.status_code == 200:
                    data = resp.json()
                    self._access_token = data.get("access_token")
                    expires_in = int(data.get("expires_in", 1800))
                    self._token_expires_at = now + datetime.timedelta(seconds=expires_in - 60)
                    return self._access_token
                else:
                    print(f"Warning: Schwab token refresh returned status {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"Warning: Schwab token refresh error: {e}")

        return None

    def _get_account_hash(self, token: str) -> Optional[str]:
        """Fetch encrypted account hash value required by Schwab trader endpoints."""
        if self._account_hash:
            return self._account_hash

        try:
            headers = {"Authorization": f"Bearer {token}"}
            url = f"{self.SCHWAB_BASE_URL}/accounts/accountNumbers"
            with httpx.Client(timeout=15.0, proxy=self._get_proxy()) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    accounts = resp.json()
                    if accounts:
                        target = accounts[0]
                        if self.account_id:
                            for a in accounts:
                                if str(a.get("accountNumber")) == str(self.account_id):
                                    target = a
                                    break
                        self._account_hash = target.get("hashValue")
                        if not self.account_id:
                            self.account_id = target.get("accountNumber", "SCHWAB_MAIN")
                        return self._account_hash
        except Exception as e:
            print(f"Warning: Schwab _get_account_hash error: {e}")

        return self.account_id or "SCHWAB_MAIN"

    def get_account_balance(self) -> AccountBalance:
        token = self._ensure_access_token()
        if token:
            try:
                acc_hash = self._get_account_hash(token)
                headers = {"Authorization": f"Bearer {token}"}
                url = f"{self.SCHWAB_BASE_URL}/accounts/{acc_hash}?fields=positions"
                with httpx.Client(timeout=15.0, proxy=self._get_proxy()) as client:
                    resp = client.get(url, headers=headers)
                    if resp.status_code == 200:
                        acc_data = resp.json().get("securitiesAccount", {})
                        balances = acc_data.get("currentBalances", {})
                        tot_eq = float(balances.get("liquidationValue", 0.0) or 0.0)
                        cash_val = float(balances.get("cashBalance", 0.0) or 0.0)
                        mkt_val = tot_eq - cash_val
                        bp = float(balances.get("buyingPower", 0.0) or 0.0)
                        return AccountBalance(
                            account_id=self.account_id or "SCHWAB_MAIN",
                            broker=self.broker,
                            account_name=self.account_name,
                            total_equity=round(tot_eq, 2),
                            cash=round(cash_val, 2),
                            market_value=round(mkt_val, 2),
                            buying_power=round(bp, 2)
                        )
            except Exception as e:
                print(f"Warning: Schwab get_account_balance error: {e}")

        return AccountBalance(
            account_id=self.account_id or "SCHWAB_MAIN",
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
                acc_hash = self._get_account_hash(token)
                headers = {"Authorization": f"Bearer {token}"}
                url = f"{self.SCHWAB_BASE_URL}/accounts/{acc_hash}?fields=positions"
                with httpx.Client(timeout=15.0, proxy=self._get_proxy()) as client:
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
                                account_id=self.account_id or "SCHWAB_MAIN",
                                broker=self.broker,
                                ticker=sym,
                                shares=round(qty, 4),
                                cost_basis=cost,
                                market_price=mkt_price,
                                market_value=round(mkt_val, 2),
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
                acc_hash = self._get_account_hash(token)
                if not start_date:
                    start_date = (datetime.datetime.now() - datetime.timedelta(days=85)).strftime('%Y-%m-%d')
                from_entered_time = f"{start_date}T00:00:00.000Z"

                headers = {"Authorization": f"Bearer {token}"}
                url = f"{self.SCHWAB_BASE_URL}/accounts/{acc_hash}/orders?fromEnteredTime={from_entered_time}&status=FILLED"
                with httpx.Client(timeout=15.0, proxy=self._get_proxy()) as client:
                    resp = client.get(url, headers=headers)
                    if resp.status_code == 200:
                        order_list = resp.json()
                        for o in order_list:
                            order_id = str(o.get("orderId", ""))
                            activities = o.get("orderActivityCollection", [])
                            order_legs = o.get("orderLegCollection", [])
                            ticker = ""
                            action = "BUY"
                            if order_legs:
                                leg = order_legs[0]
                                ticker = leg.get("instrument", {}).get("symbol", "").upper()
                                action = leg.get("instruction", "BUY").upper()

                            for act in activities:
                                if act.get("activityType") == "EXECUTION":
                                    exec_legs = act.get("executionLegs", [])
                                    for el in exec_legs:
                                        filled_qty = float(el.get("quantity", 0.0))
                                        fill_price = float(el.get("price", 0.0))
                                        fill_time = el.get("time", "")

                                        orders.append(FilledOrder(
                                            order_id=f"{order_id}_{el.get('legId', '1')}",
                                            account_id=self.account_id or "SCHWAB_MAIN",
                                            broker=self.broker,
                                            ticker=ticker,
                                            action=action,
                                            shares=filled_qty,
                                            price=fill_price,
                                            total_value=filled_qty * fill_price,
                                            fee=0.0,
                                            filled_at=fill_time[:19].replace("T", " "),
                                            status="FILLED"
                                        ))
            except Exception as e:
                print(f"Warning: Schwab get_filled_orders error: {e}")

        return orders
