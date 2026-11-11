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


def sync_broker_positions_to_db(
    broker_positions_df: pd.DataFrame,
    shadow_mode: bool = True
) -> Dict[str, Any]:
    """
    Synchronizes broker API positions directly into the positions table (SQLite + Supabase Cloud).
    In shadow mode, no changes are committed.
    """
    if shadow_mode or broker_positions_df is None:
        return {"synced": False, "reason": "Shadow mode active or empty dataframe"}

    from database import update_position, get_positions
    db_pos = get_positions()
    db_tickers = set(db_pos['ticker'].tolist()) if not db_pos.empty else set()
    broker_tickers = set()

    synced_items = []
    if not broker_positions_df.empty:
        for _, row in broker_positions_df.iterrows():
            ticker = str(row['ticker']).upper().strip()
            shares = float(row.get('shares', 0.0))
            cost_basis = float(row.get('cost_basis', 0.0))
            layer = str(row.get('layer', get_canonical_layer(ticker)))
            if shares > 0.0001:
                broker_tickers.add(ticker)
                update_position(ticker, shares, cost_basis, layer)
                synced_items.append({"ticker": ticker, "shares": shares, "cost_basis": cost_basis, "layer": layer})

    # Remove positions no longer held at broker
    closed_tickers = db_tickers - broker_tickers
    for t in closed_tickers:
        update_position(t, 0.0, 0.0, "CLOSED")

    return {"synced": True, "updated": synced_items, "closed": list(closed_tickers)}


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
    
    # Query already-synced orders upfront to avoid long-lived lock
    c_check = sqlite3.connect(DB_PATH, timeout=30.0)
    cur_check = c_check.cursor()
    cur_check.execute("SELECT order_id FROM broker_synced_orders")
    synced_order_ids = set(str(row[0]) for row in cur_check.fetchall())
    c_check.close()

    new_orders: List[Dict[str, Any]] = []

    for o in orders:
        if str(o.order_id) in synced_order_ids:
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

        # Auto determine classification and strategy relevance
        layer_norm = order_dict["layer"]
        if layer_norm in ["L1", "L2", "L0", "SGOV", "Non-Equity"]:
            category = f"STRATEGY_{layer_norm.upper()}"
            is_strat = 1
        else:
            category = "MANUAL_OVERRIDE"
            is_strat = 0

        order_dict["category"] = category
        order_dict["is_strategy"] = is_strat

        if not shadow_mode:
            trade_date = o.filled_at[:10] if len(o.filled_at) >= 10 else datetime.date.today().strftime("%Y-%m-%d")
            
            # Fetch current position for cost/pnl calculation
            c_pos = sqlite3.connect(DB_PATH, timeout=30.0)
            cur_pos = c_pos.cursor()
            cur_pos.execute("SELECT shares, cost_basis FROM positions WHERE ticker = ?", (o.ticker,))
            pos_row = cur_pos.fetchone()
            c_pos.close()

            curr_shares = float(pos_row[0]) if pos_row else 0.0
            curr_cost = float(pos_row[1]) if pos_row else o.price

            trade_pnl = 0.0
            from database import update_position, record_trade
            if o.action.upper() == "BUY":
                new_shares = curr_shares + o.shares
                new_cost = (curr_shares * curr_cost + o.total_value + o.fee) / new_shares if new_shares > 0 else o.price
                update_position(o.ticker, new_shares, new_cost, layer_norm)
            else: # SELL
                new_shares = max(0.0, curr_shares - o.shares)
                trade_pnl = round((o.price - curr_cost) * o.shares - o.fee, 2)
                update_position(o.ticker, new_shares, curr_cost if new_shares > 0 else 0.0, layer_norm)

            # Record trade into trades table (SQLite + Supabase Cloud)
            record_trade(
                date_str=trade_date,
                ticker=o.ticker,
                action=o.action.upper(),
                shares=o.shares,
                price=o.price,
                total_val=o.total_value,
                fee=o.fee,
                pnl=trade_pnl,
                layer=layer_norm,
                reason=f"API Auto-Sync ({o.broker.value})",
                category=category,
                is_strategy=is_strat
            )

            # Mark in broker_synced_orders for idempotency
            c_mark = sqlite3.connect(DB_PATH, timeout=30.0)
            cur_mark = c_mark.cursor()
            cur_mark.execute("""
            INSERT INTO broker_synced_orders (order_id, broker, account_id, ticker, action, shares, price, total_value, fee, filled_at, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (o.order_id, o.broker.value, o.account_id, o.ticker, o.action, o.shares, o.price, o.total_value, o.fee, o.filled_at, now_str))
            c_mark.commit()
            c_mark.close()
            synced_order_ids.add(str(o.order_id))

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
