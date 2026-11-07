"""
Broker Reconciliation & Order Ingestion Engine (core/sync/reconcile_engine.py)
Synchronizes filled orders from broker APIs into local database,
compares broker live positions vs database positions to detect drifts,
and maintains shadow mode protection.
"""

import sqlite3
import datetime
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd
from config import DB_PATH
from core.broker.base import FilledOrder, CashTransactionItem
from core.broker.manager import MultiBrokerManager
from core.sanity.signal_guard import get_canonical_layer


class DriftReport:
    def __init__(self):
        self.has_drift: bool = False
        self.drifts: List[Dict[str, Any]] = []
        self.summary_lines: List[str] = []

    def add_drift(self, ticker: str, db_shares: float, broker_shares: float, reason: str = ""):
        self.has_drift = True
        diff = round(broker_shares - db_shares, 4)
        item = {
            "ticker": ticker,
            "db_shares": round(db_shares, 4),
            "broker_shares": round(broker_shares, 4),
            "diff": diff,
            "reason": reason
        }
        self.drifts.append(item)
        sign = "+" if diff > 0 else ""
        self.summary_lines.append(f"• **{ticker}**: DB持仓 `{db_shares:.2f}` vs 券商API `{broker_shares:.2f}` (差异: `{sign}{diff:.2f}`股)")


def init_reconcile_tables(conn: Optional[sqlite3.Connection] = None):
    """Ensure broker_synced_orders table exists for idempotency."""
    close_at_end = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        close_at_end = True

    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS broker_synced_orders (
        order_id TEXT PRIMARY KEY,
        broker TEXT NOT NULL,
        account_id TEXT NOT NULL,
        ticker TEXT NOT NULL,
        action TEXT NOT NULL,
        shares REAL NOT NULL,
        price REAL NOT NULL,
        total_value REAL NOT NULL,
        fee REAL DEFAULT 0.0,
        filled_at TEXT NOT NULL,
        synced_at TEXT NOT NULL,
        trade_id INTEGER
    )
    """)
    conn.commit()
    if close_at_end:
        conn.close()


def check_position_drift(db_positions_df: pd.DataFrame, broker_positions_df: pd.DataFrame) -> DriftReport:
    """
    Compares database positions against broker API positions.
    Detects DRIP dividends, manual adjustments, or unrecorded fills.
    """
    report = DriftReport()

    db_map = {}
    if not db_positions_df.empty:
        for _, row in db_positions_df.iterrows():
            t = str(row['ticker']).upper().strip()
            s = float(row.get('shares', 0.0))
            if s > 0.0001:
                db_map[t] = s

    broker_map = {}
    if not broker_positions_df.empty:
        for _, row in broker_positions_df.iterrows():
            t = str(row['ticker']).upper().strip()
            s = float(row.get('shares', 0.0))
            if s > 0.0001:
                broker_map[t] = s

    all_tickers = sorted(list(set(db_map.keys()) | set(broker_map.keys())))

    for t in all_tickers:
        db_s = db_map.get(t, 0.0)
        bk_s = broker_map.get(t, 0.0)
        diff = bk_s - db_s
        if abs(diff) >= 0.01:
            report.add_drift(t, db_s, bk_s)

    return report


def ingest_broker_orders(
    orders: List[FilledOrder],
    shadow_mode: bool = True,
    conn: Optional[sqlite3.Connection] = None
) -> Tuple[int, List[Dict[str, Any]]]:
    """
    Ingest orders from broker API.
    In shadow mode, detects new orders and verifies them without mutating live trades.
    """
    init_reconcile_tables(conn)
    close_at_end = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        close_at_end = True

    cursor = conn.cursor()
    new_orders: List[Dict[str, Any]] = []

    for o in orders:
        cursor.execute("SELECT 1 FROM broker_synced_orders WHERE order_id = ?", (o.order_id,))
        if cursor.fetchone() is not None:
            continue  # Already ingested

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        order_dict = {
            "order_id": o.order_id,
            "broker": o.broker.value,
            "account_id": o.account_id,
            "ticker": o.ticker,
            "action": o.action,
            "shares": o.shares,
            "price": o.price,
            "total_value": o.total_value,
            "fee": o.fee,
            "filled_at": o.filled_at,
            "layer": get_canonical_layer(o.ticker)
        }
        new_orders.append(order_dict)

        if not shadow_mode:
            # Live ingestion into trades table and sync table
            trade_date = o.filled_at[:10] if len(o.filled_at) >= 10 else datetime.date.today().strftime("%Y-%m-%d")
            cursor.execute("""
            INSERT INTO trades (date, ticker, action, shares, price, total_val, fee, pnl, layer, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?)
            """, (trade_date, o.ticker, o.action, o.shares, o.price, o.total_value, o.fee, order_dict["layer"], f"API Auto-Sync ({o.broker.value})"))
            trade_id = cursor.lastrowid

            cursor.execute("""
            INSERT INTO broker_synced_orders (order_id, broker, account_id, ticker, action, shares, price, total_value, fee, filled_at, synced_at, trade_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (o.order_id, o.broker.value, o.account_id, o.ticker, o.action, o.shares, o.price, o.total_value, o.fee, o.filled_at, now_str, trade_id))

    if not shadow_mode:
        conn.commit()

    if close_at_end:
        conn.close()

    return len(new_orders), new_orders

def ingest_broker_cash_transactions(
    cash_txs: List[CashTransactionItem],
    conn: Optional[sqlite3.Connection] = None
) -> Tuple[int, List[Dict[str, Any]]]:
    """
    Ingest cash deposits and withdrawals from broker APIs into cash_transactions table.
    Ensures strict idempotency: skips records where (date, type, abs(amount)) already exists.
    """
    close_at_end = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        close_at_end = True

    cursor = conn.cursor()
    new_ingested = []

    for ctx in cash_txs:
        # Check idempotency: match date, type, and amount within $0.01 tolerance
        cursor.execute(
            "SELECT id FROM cash_transactions WHERE date = ? AND type = ? AND abs(amount - ?) < 0.01",
            (ctx.date, ctx.type, ctx.amount)
        )
        if cursor.fetchone() is not None:
            continue

        notes = f"[{ctx.broker.value}] {ctx.account_id}: {ctx.description}"
        if ctx.raw_type:
            notes += f" ({ctx.raw_type})"

        cursor.execute(
            "INSERT INTO cash_transactions (date, type, amount, notes) VALUES (?, ?, ?, ?)",
            (ctx.date, ctx.type, ctx.amount, notes)
        )
        new_ingested.append({
            "date": ctx.date,
            "type": ctx.type,
            "amount": ctx.amount,
            "broker": ctx.broker.value,
            "account_id": ctx.account_id,
            "notes": notes
        })

    conn.commit()
    if close_at_end:
        conn.close()

    return len(new_ingested), new_ingested
