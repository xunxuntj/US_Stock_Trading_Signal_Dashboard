"""
Tiger Brokers OpenAPI Connector (core/broker/tiger_connector.py)
Connects to TigerOpen API for Tiger Universal Account and Consolidated Account.
Supports reading real-time balances, multi-asset positions, and filled orders.
Gracefully handles missing credentials or offline execution with clear diagnostics.
"""

import os
import datetime
from typing import List, Optional, Dict, Any
from .base import BaseBrokerConnector, BrokerType, AccountBalance, PositionItem, FilledOrder, CashTransactionItem
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
        total_eq = 0.0
        cash_val = 0.0
        mkt_val = 0.0
        acc_div = 0.0
        acc_int = 0.0
        vault_val = 0.0
        locked_f = 0.0
        b_power = 0.0
        e_liq = 0.0

        if self._client:
            is_prime_parsed = False
            # 1. Query Prime Account assets (consolidates Segment S - Securities + Segment F - Funds/钱袋子)
            try:
                prime_obj = self._client.get_prime_assets(account=self.account_id, consolidated=True)
                if prime_obj:
                    segs = getattr(prime_obj, 'segments', {})
                    if segs:
                        for seg_name, seg in segs.items():
                            s_eq = float(getattr(seg, 'net_liquidation', 0.0) or 0.0)
                            # Strictly use pure cash_balance (never fallback to cash_available_for_trade which includes margin loan)
                            cb_raw = getattr(seg, 'cash_balance', None)
                            s_cash = float(cb_raw) if cb_raw is not None and str(cb_raw) != 'inf' else 0.0
                            s_mkt = float(getattr(seg, 'gross_position_value', 0.0) or 0.0)
                            s_lock = float(getattr(seg, 'locked_funds', 0.0) or 0.0)
                            s_bp = float(getattr(seg, 'buying_power', 0.0) or 0.0)
                            s_ex = float(getattr(seg, 'excess_liquidation', 0.0) or 0.0)

                            if seg_name == 'F' or 'FUND' in str(getattr(seg, 'category', '')).upper():
                                vault_val += s_eq
                            elif seg_name == 'S' or 'SEC' in str(getattr(seg, 'category', '')).upper():
                                mkt_val += s_mkt

                            if s_eq != float('inf') and s_eq > 0:
                                total_eq += s_eq
                            if s_cash != float('inf') and s_cash > 0:
                                cash_val += s_cash
                            if s_lock != float('inf') and s_lock > 0:
                                locked_f += s_lock
                            if s_bp != float('inf') and s_bp > b_power:
                                b_power = s_bp
                            if s_ex != float('inf') and s_ex > e_liq:
                                e_liq = s_ex

                        is_prime_parsed = (total_eq > 0.0)
            except Exception:
                # Normal for Global accounts (e.g. U9959007)
                pass

            # 2. Query Asset Details (for accrued dividends and Global Account fallback)
            try:
                asset_list = self._client.get_assets(account=self.account_id, segment=True, market_value=True)
                if asset_list and len(asset_list) > 0:
                    a = asset_list[0]
                    summary = getattr(a, 'summary', None)
                    if summary:
                        div = float(getattr(summary, 'accrued_dividend', 0.0) or 0.0)
                        if div != float('inf') and div > 0:
                            acc_div = div
                        c_acc = float(getattr(summary, 'accrued_cash', 0.0) or getattr(summary, 'accrued_interest', 0.0) or 0.0)
                        if c_acc != float('inf') and c_acc > 0:
                            acc_int = c_acc

                        if not is_prime_parsed:
                            net_liq = float(getattr(summary, 'net_liquidation', 0.0) or 0.0)
                            if net_liq != float('inf') and net_liq > 0:
                                total_eq = net_liq
                            c_raw = getattr(summary, 'cash', None)
                            c_val = float(c_raw) if c_raw is not None and str(c_raw) != 'inf' else 0.0
                            cash_val = c_val
                            gp_val = float(getattr(summary, 'gross_position_value', 0.0) or 0.0)
                            if gp_val != float('inf') and gp_val > 0:
                                mkt_val = gp_val

                        bp = float(getattr(summary, 'buying_power', 0.0) or 0.0)
                        if bp != float('inf') and bp > b_power:
                            b_power = bp
                        ex = float(getattr(summary, 'excess_liquidity', 0.0) or 0.0)
                        if ex != float('inf') and ex > e_liq:
                            e_liq = ex
            except Exception:
                # 3. Fallback to basic get_assets
                try:
                    asset_obj = self._client.get_assets(account=self.account_id)
                    if asset_obj and len(asset_obj) > 0:
                        a = asset_obj[0]
                        summary = getattr(a, 'summary', None)
                        if summary and not is_prime_parsed:
                            net_liq = float(getattr(summary, 'net_liquidation', 0.0) or 0.0)
                            if net_liq != float('inf') and net_liq > 0:
                                total_eq = net_liq
                            c_raw = getattr(summary, 'cash', None)
                            c_val = float(c_raw) if c_raw is not None and str(c_raw) != 'inf' else 0.0
                            cash_val = c_val
                            gp_val = float(getattr(summary, 'gross_position_value', 0.0) or 0.0)
                            if gp_val != float('inf') and gp_val > 0:
                                mkt_val = gp_val
                except Exception:
                    pass

            # 4. Fallback / Cross-Validation: sum position market values
            positions = self.get_positions()
            pos_mkt_val = sum(p.market_value for p in positions)
            if pos_mkt_val > 0:
                if mkt_val <= 0:
                    mkt_val = pos_mkt_val
                if total_eq <= 0:
                    total_eq = mkt_val + cash_val + vault_val + acc_div

        return AccountBalance(
            account_id=self.account_id,
            broker=self.broker,
            account_name=self.account_name,
            total_equity=round(total_eq, 2),
            cash=round(cash_val, 2),
            market_value=round(mkt_val, 2),
            accrued_dividend=round(acc_div, 2),
            accrued_interest=round(acc_int, 2),
            vault_balance=round(vault_val, 2),
            locked_funds=round(locked_f, 2),
            buying_power=round(b_power, 2),
            excess_liquidity=round(e_liq, 2)
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

                    # Tiger SDK provides pre-normalized fractional shares in position_qty / pos_qty
                    quantity = float(getattr(p, 'position_qty', getattr(p, 'pos_qty', getattr(p, 'quantity', 0.0))) or 0.0)

                    if quantity <= 0.0001:
                        continue
                    cost_basis = float(getattr(p, 'average_cost', 0.0) or 0.0)
                    market_price = float(getattr(p, 'market_price', cost_basis) or cost_basis)
                    market_val = float(getattr(p, 'market_value', quantity * market_price) or quantity * market_price)

                    results.append(PositionItem(
                        account_id=self.account_id,
                        broker=self.broker,
                        ticker=symbol,
                        shares=round(quantity, 4),
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
                if not start_date:
                    start_date = (datetime.datetime.now() - datetime.timedelta(days=85)).strftime('%Y-%m-%d')
                end_date = datetime.datetime.now().strftime('%Y-%m-%d')
                tiger_orders = self._client.get_filled_orders(account=self.account_id, start_date=start_date, end_date=end_date, start_time=start_date, end_time=end_date)
                for o in tiger_orders:
                    order_id = str(getattr(o, 'order_id', getattr(o, 'id', '')))
                    raw_sym = getattr(o, 'symbol', None)
                    if not raw_sym and hasattr(o, 'contract'):
                        raw_sym = getattr(o.contract, 'symbol', '')
                    symbol = str(raw_sym or '').upper().strip()
                    if not symbol:
                        continue

                    action = str(getattr(o, 'action', 'BUY')).upper()
                    raw_filled = float(getattr(o, 'filled_quantity', getattr(o, 'filled', 0.0)) or 0.0)
                    f_scale = float(getattr(o, 'filled_scale', getattr(o, 'quantity_scale', 1.0)) or 1.0)
                    filled_qty = raw_filled / f_scale if f_scale > 1.0 else raw_filled
                    avg_fill_price = float(getattr(o, 'avg_fill_price', 0.0) or 0.0)
                    commission = float(getattr(o, 'commission', 0.0) or 0.0)
                    raw_time = getattr(o, 'trade_time', getattr(o, 'order_time', ''))
                    fill_time = ""
                    if raw_time:
                        try:
                            val = float(raw_time)
                            if val > 1e11: # milliseconds
                                val = val / 1000.0
                            fill_time = datetime.datetime.fromtimestamp(val).strftime('%Y-%m-%d %H:%M:%S')
                        except Exception:
                            fill_time = str(raw_time)

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

    def get_cash_transactions(self, start_date: Optional[str] = None) -> List[CashTransactionItem]:
        """Fetch cash deposits/withdrawals from TigerOpen API if available."""
        results: List[CashTransactionItem] = []
        if not self._client:
            return results

        try:
            # Query funding history
            fund_history = self._client.get_funding_history()
            if fund_history:
                for item in fund_history:
                    # Parse item properties
                    d_str = str(getattr(item, 'date', getattr(item, 'updated_at', '')))[:10]
                    t_type = str(getattr(item, 'type', getattr(item, 'funding_type', 'DEPOSIT'))).upper()
                    amt = float(getattr(item, 'amount', 0.0) or 0.0)
                    desc = str(getattr(item, 'remark', getattr(item, 'comment', 'Tiger Funding')))
                    tx_id = str(getattr(item, 'id', f"{d_str}_{t_type}_{abs(amt)}"))

                    action = "DEPOSIT" if ("DEP" in t_type or "IN" in t_type or amt > 0) else "WITHDRAWAL"
                    results.append(CashTransactionItem(
                        transaction_id=tx_id,
                        account_id=self.account_id,
                        broker=self.broker,
                        date=d_str or datetime.date.today().strftime('%Y-%m-%d'),
                        type=action,
                        amount=abs(amt),
                        description=desc,
                        raw_type=t_type
                    ))
        except Exception as e:
            # Graceful fallback: Tiger funding API may not be permissioned on all retail keys
            pass

        return results
