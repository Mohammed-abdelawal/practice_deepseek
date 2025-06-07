# app/utils/json_db.py
"""
Light‑weight JSON persistence layer using TinyDB.
------------------------------------------------
* Orders and Sessions live in a single file:  data/db.json
* All helpers are async‑friendly (they return awaitables),
  but TinyDB itself is synchronous.  If you later move to a
  real async DB (e.g. PostgreSQL + asyncpg) you can keep
  identical function signatures.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4
from typing import List, Dict, Any, Literal

from tinydb import TinyDB, where
from tinydb.storages import JSONStorage
from tinydb.middlewares import CachingMiddleware

# ── Locate / create data folder ────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "db.json"

db = TinyDB(DB_PATH, storage=CachingMiddleware(JSONStorage))
orders_table = db.table("orders")
sessions_table = db.table("sessions")

# ──────────────────────────────────────────────────────────────────────────
#  ORDERS
# ──────────────────────────────────────────────────────────────────────────
Order = Dict[str, Any]


async def create_order(order_data: Dict[str, Any]) -> Order:
    """
    Adds a new order.
    - If order_id missing, auto‑generates UUID.
    Returns the full order dict.
    """
    order_data = dict(order_data)  # shallow copy
    order_data.setdefault("order_id", str(uuid4()))
    orders_table.insert(order_data)
    db.storage.flush()  # force write‑through
    return order_data


async def get_order(order_id: str) -> Order | None:
    return orders_table.get(where("order_id") == order_id)


async def update_order(order_id: str, updates: Dict[str, Any]) -> Order | None:
    """
    Partial update (merge).
    Returns the updated order or None if not found.
    """
    if not orders_table.contains(where("order_id") == order_id):
        return None
    orders_table.update(updates, where("order_id") == order_id)
    db.storage.flush()
    return await get_order(order_id)


async def delete_order(order_id: str) -> bool:
    """
    Returns True if order deleted, False if order_id not found.
    """
    removed = orders_table.remove(where("order_id") == order_id)
    if removed:
        db.storage.flush()
    return bool(removed)


ComparisonOp = Literal["==", "!=", ">", "<", "~"]


async def search_orders(filters: List[Dict[str, Any]]) -> List[Order]:
    """
    Return all orders matching *all* filter clauses (AND semantics).
    """

    def _build_query(f):
        field, op, val = f["field"], f["op"], f["value"]
        if op == "==":
            return where(field) == val
        if op == "!=":
            return where(field) != val
        if op == ">":
            return where(field).test(lambda x: x is not None and x > val)
        if op == "<":
            return where(field).test(lambda x: x is not None and x < val)
        if op == "~":  # substring / icontains
            return where(field).search(str(val), flags=re.I)
        raise ValueError(f"Unsupported op: {op}")

    import re

    if not filters:
        return orders_table.all()

    query = _build_query(filters[0])
    for f in filters[1:]:
        query &= _build_query(f)

    return orders_table.search(query)


# ──────────────────────────────────────────────────────────────────────────
#  SESSIONS  (conversation history for chat)
# ──────────────────────────────────────────────────────────────────────────


async def load_history(session_id: str) -> List[Dict[str, str]]:
    row = sessions_table.get(where("session_id") == session_id)
    return row["history"] if row else []


async def save_history(session_id: str, history: List[Dict[str, str]]) -> None:
    sessions_table.upsert(
        {"session_id": session_id, "history": history},
        where("session_id") == session_id,
    )
    db.storage.flush()


async def delete_session(session_id: str) -> bool:
    removed = sessions_table.remove(where("session_id") == session_id)
    if removed:
        db.storage.flush()
    return bool(removed)


# ──────────────────────────────────────────────────────────────────────────
#  Utility: warm‑seed demo orders if file is empty
# ──────────────────────────────────────────────────────────────────────────

if not orders_table:
    import datetime as _dt

    demo_orders = [
        {
            "order_id": "1001",
            "customer": "Ahmed Ali",
            "status": "processing",
            "created_at": _dt.date.today().isoformat(),
            "total_price": 450.0,
            "items": [{"sku": "SKU‑TV‑55‑OLED", "qty": 1, "price": 450.0}],
        },
        {
            "order_id": "1002",
            "customer": "Sara Youssef",
            "status": "shipped",
            "created_at": _dt.date.today().isoformat(),
            "total_price": 120.0,
            "items": [
                {"sku": "SKU‑HDMI‑CABLE", "qty": 2, "price": 20.0},
                {"sku": "SKU‑POWER‑BANK", "qty": 1, "price": 80.0},
            ],
        },
    ]
    orders_table.insert_multiple(demo_orders)
    db.storage.flush()
