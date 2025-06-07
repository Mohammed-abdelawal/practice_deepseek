# app/utils/openai_client.py
import os
from openai import AsyncOpenAI

__all__ = [
    "configure_openai",
    "get_chat_model_name",
    "get_async_client",
]

_client: AsyncOpenAI | None = None  # singleton


def configure_openai(api_key: str, api_base: str):
    """
    Call once at startup to configure BOTH the global openai module
    and a reusable AsyncOpenAI() client.
    """
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_BASE_URL"] = api_base

    global _client
    _client = AsyncOpenAI(api_key=api_key, base_url=api_base)


configure_openai(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    api_base=os.getenv("DEEPSEEK_API_BASE"),
)


def get_async_client() -> AsyncOpenAI:
    """
    Returns the singleton AsyncOpenAI client that was configured at startup.
    """
    if _client is None:
        raise RuntimeError("configure_openai() must be called first")
    return _client


def get_chat_model_name() -> str:
    """
    Central place to pick the Deepseek chat model ID.
    """
    return "deepseek-chat"
