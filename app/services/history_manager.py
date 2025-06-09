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

    logger.debug("Summarizing %d messages", len(messages))
    system = {
        "role": "system",
        "content": "Summarize the following conversation briefly.",
    }
    aclient = get_async_client()
    completion = await aclient.chat.completions.create(
        model="deepseek-reasoner",
        messages=[system, *messages],
        temperature=0.2,
        max_tokens=150,
    )
    summary = completion.choices[0].message.content
    logger.debug("Summary result: %s", summary)
    return summary


async def trim_history(session_id: str, window: int = 5, chunk: int = 10) -> None:
    """Summarize old messages so only the latest *window* remain unsummarized."""
    logger.debug("Trimming history for session %s", session_id)
    history = await json_db.load_history(session_id)
    logger.debug("Loaded %d total messages", len(history))
    if len(history) <= window + chunk:
        logger.debug("History size below threshold; skipping trim")
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
    logger.debug("Unsummarized messages: %d", len(unsummarized))
    if len(unsummarized) <= window + chunk:
        logger.debug("Not enough messages to trim")
        return

    old = unsummarized[:chunk]
    # ensure we don't cut off in the middle of a tool-call sequence
    while old and old[-1].get("role") == "tool":
        logger.debug("Dropping trailing tool message to keep history valid")
        old.pop()
    while old and old[-1].get("role") == "assistant" and "tool_calls" in old[-1]:
        logger.debug("Dropping trailing assistant tool-call message to keep history valid")
        old.pop()
    logger.debug("Summarizing %d old messages", len(old))
    try:
        summary = await summarize_messages(old)
    except Exception as e:
        logger.exception("Failed to summarize messages: %s", e)
        return

    summary_msg = {
        "role": "assistant",
        "content": summary,
        "meta": {"summary_of": old},
    }
    new_history = history[: last_idx + 1] + [summary_msg] + unsummarized[chunk:]
    await json_db.save_history(session_id, new_history)

    logger.debug("Trimmed history saved; new length: %d", len(new_history))


def schedule_trim(session_id: str) -> None:
    """Launch background task to trim history for *session_id*."""
    logger.debug("Scheduling trim for session %s", session_id)
    asyncio.create_task(trim_history(session_id))
