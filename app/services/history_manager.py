from __future__ import annotations

import asyncio
from typing import List, Dict, Any
from logging import getLogger

from app.utils import json_db
from app.utils.openai_client import get_async_client

logger = getLogger(__name__)


async def summarize_messages(messages: List[Dict[str, Any]]) -> str:
    """Summarize a list of chat messages using deepseek-reasoner."""
    if not messages:
        return ""
    system = {"role": "system", "content": "Summarize the following conversation briefly."}
    aclient = get_async_client()
    completion = await aclient.chat.completions.create(
        model="deepseek-reasoner",
        messages=[system, *messages],
        temperature=0.2,
        max_tokens=150,
    )
    return completion.choices[0].message.content


async def trim_history(session_id: str, window: int = 5, chunk: int = 10) -> None:
    """Summarize old messages so only the latest *window* remain unsummarized."""
    history = await json_db.load_history(session_id)
    if len(history) <= window + chunk:
        return

    # find index of last summary or system message
    last_idx = 0
    for i in range(len(history) - 1, -1, -1):
        meta = history[i].get("meta")
        if meta and meta.get("summary_of") is not None:
            last_idx = i
            break
        if history[i]["role"] == "system":
            last_idx = i
            break

    unsummarized = history[last_idx + 1 :]
    if len(unsummarized) <= window + chunk:
        return

    old = unsummarized[:chunk]
    try:
        summary = await summarize_messages(old)
    except Exception as e:
        logger.exception("Failed to summarize messages: %s", e)
        return

    summary_msg = {"role": "assistant", "content": summary, "meta": {"summary_of": old}}
    new_history = history[: last_idx + 1] + [summary_msg] + unsummarized[chunk:]
    await json_db.save_history(session_id, new_history)


def schedule_trim(session_id: str) -> None:
    """Launch background task to trim history for *session_id*."""
    asyncio.create_task(trim_history(session_id))
