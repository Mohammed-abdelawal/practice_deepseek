# app/services/chat_service.py
"""High‑level orchestration layer for the Acme support‑bot.

Refactor notes (2025‑06‑07)
--------------------------
* Switched all `choice.message["…"]` look‑ups to *attribute* access
  (`choice.message.content`, `.function_call`, etc.) to match the
  fast‑moving OpenAI Python v1 objects (they are no longer dict‑like).
* Added `_msg_to_dict()` so we can safely push SDK objects back into the
  history list (which stores plain dicts).
* `_chat_completion()` now returns `ChatCompletion` typed as `Any` to
  avoid stale import paths when the SDK updates.
"""

from __future__ import annotations

import json
from typing import Dict, List, Tuple, Any

from openai import AsyncOpenAI
import openai  # for type hints only
from logging import getLogger

from app.utils.openai_client import get_async_client, get_chat_model_name
from app.utils import json_db
from app.services.history_manager import schedule_trim
import logging

logging.basicConfig(level=logging.DEBUG)
aclient: AsyncOpenAI = get_async_client()

logger = getLogger(__name__)

# ────────────────────────────────────────────────────────────────────────────
#  System prompt
# ────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are a friendly customer‑support bot for **Acme Corp**.\n"
    "• Respond politely and concisely.\n"
    "• Call one of the provided functions when you need live data."
)

# ────────────────────────────────────────────────────────────────────────────
#  Callable tool JSON schemas
# ────────────────────────────────────────────────────────────────────────────
TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_order",
            "description": "Retrieve order status by ID.",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_order",
            "description": "Add a new order to the system.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer": {"type": "string"},
                    "status": {"type": "string"},
                    "total_price": {"type": "number"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "sku": {"type": "string"},
                                "qty": {"type": "integer"},
                                "price": {"type": "number"},
                            },
                            "required": ["sku", "qty", "price"],
                        },
                    },
                },
                "required": ["customer", "status", "total_price", "items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_order",
            "description": "Patch fields of an existing order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "fields": {"type": "object"},
                },
                "required": ["order_id", "fields"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_order",
            "description": "Delete an order.",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_orders",
            "description": "Search orders via simple filters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string"},
                                "op": {
                                    "type": "string",
                                    "enum": ["==", "!=", ">", "<", "~"],
                                },
                                "value": {},
                            },
                            "required": ["field", "op", "value"],
                        },
                    }
                },
                "required": ["filters"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_order_items",
            "description": "Perform an action on the items list (e.g. duplicate all items).",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "sku": {"type": "string"},
                                "qty": {"type": "integer"},
                                "price": {"type": "number"},
                            },
                            "required": ["sku", "qty", "price"],
                        },
                    },
                },
                "required": ["order_id", "items"],
            },
        },
    },
]

# ────────────────────────────────────────────────────────────────────────────
#  Helper utilities
# ────────────────────────────────────────────────────────────────────────────


def _ensure_system(history: List[Dict[str, str]]) -> None:
    if not history or history[0]["role"] != "system":
        history.insert(0, {"role": "system", "content": SYSTEM_PROMPT})


def _add_user(history: List[Dict[str, str]], text: str) -> None:
    logger.debug("Adding user message to history: %s", text)
    history.append({"role": "user", "content": text})


def _msg_to_dict(
    msg: openai.types.chat.chat_completion.ChatCompletionMessage,
) -> Dict[str, Any]:
    """Convert SDK message object → plain dict (for our history list)."""
    base = {"role": msg.role, "content": msg.content}
    if msg.function_call is not None:
        base["function_call"] = msg.function_call.model_dump(exclude_none=True)
    return base


async def _chat(history: List[Dict[str, str]], choice: str = "auto") -> Any:
    """Send chat request; choice='auto' or 'none'."""
    return await aclient.chat.completions.create(
        model=get_chat_model_name(),
        messages=history,
        tools=TOOLS,
        tool_choice=choice,
        temperature=0.4,
        max_tokens=300,
    )


async def _run_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    logger.debug("Running tool: %s with args: %s", name, args)
    if name == "get_order":
        order = await json_db.get_order(args["order_id"])
        if not order:
            raise ValueError("Order not found")
        return {"order": order}
    if name == "create_order":
        return await json_db.create_order(args)
    if name == "update_order":
        return await json_db.update_order(args["order_id"], args["fields"])
    if name == "delete_order":
        return {"deleted": await json_db.delete_order(args["order_id"])}
    if name == "search_orders":
        return {"results": await json_db.search_orders(args["filters"])}
    if name == "update_order_items":
        order = await json_db.get_order(args["order_id"])
        if not order:
            return {"error": "not_found"}

        items = args["items"]
        new_total = sum(i["qty"] * i["price"] for i in items)

        updated = await json_db.update_order(
            args["order_id"], {"items": items, "total_price": new_total}
        )
        return {"order": updated}
    raise RuntimeError(f"Unknown function: {name}")


async def _handle(choice: Any, history: List[Dict[str, str]]) -> str:
    """Handle either plain text or tool‑call response."""
    if choice.finish_reason not in ("function_call", "tool_calls"):
        assistant = choice.message.content or "(no content)"
        history.append({"role": "assistant", "content": assistant})
        return assistant

    if getattr(choice.message, "tool_calls", None):
        tool_call = choice.message.tool_calls[0]
    else:
        tool_call = choice.message.function_call  # legacy single call

    history.append(
        {
            "role": "assistant",
            "content": choice.message.content or "",
            "tool_calls": [
                tc.model_dump(exclude_none=True)
                for tc in getattr(choice.message, "tool_calls", [tool_call])
            ],
        }
    )

    name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)
    args = json.loads(tool_call.function.arguments)

    result = await _run_tool(name, args)

    history.append(
        {
            "role": "tool",
            "tool_call_id": tool_call.id if hasattr(tool_call, "id") else "legacy",
            "name": name,
            "content": json.dumps(result),
        }
    )

    follow = await _chat(history, choice="none")
    assistant = follow.choices[0].message.content
    history.append({"role": "assistant", "content": assistant})
    return assistant


# ────────────────────────────────────────────────────────────────────────────
#  Public entry‑point
# ────────────────────────────────────────────────────────────────────────────
async def process_user_message(
    session_id: str, user_message: str
) -> Tuple[str, List[Dict[str, str]]]:
    history = await json_db.load_history(session_id)
    _ensure_system(history)
    history.append({"role": "user", "content": user_message})

    first = await _chat(history)
    reply = await _handle(first.choices[0], history)

    await json_db.save_history(session_id, history)

    # schedule background trimming so we don't block the user request
    schedule_trim(session_id)

    return reply, history
