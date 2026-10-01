"""Thin wrapper around Token Factory's OpenAI-compatible chat API.

Nemotron models on Token Factory are reasoning models: the final answer may be
in `content`, with the thinking in a separate field -- and some integrations
have seen `content` come back empty. We capture both. Verified 2026-10-01:
Nano returns `reasoning`; Super returns both `reasoning` and
`reasoning_content`. `content` comes back with a leading newline.
"""
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from agent.config import settings


@dataclass
class ChatReply:
    content: str
    reasoning: str | None
    raw: Any


def get_client() -> OpenAI:
    if not settings.api_key:
        raise RuntimeError("NEBIUS_API_KEY is not set. Copy .env.example to .env and fill it in.")
    return OpenAI(base_url=settings.base_url, api_key=settings.api_key)


def _extract_reasoning(message) -> str | None:
    for attr in ("reasoning_content", "reasoning"):
        val = getattr(message, attr, None)
        if val:
            return val
    extra = getattr(message, "model_extra", None) or {}
    return extra.get("reasoning_content") or extra.get("reasoning")


def chat(messages: list[dict], model: str, **kwargs) -> ChatReply:
    if not model:
        raise RuntimeError("No model ID given. Set MODEL_FAST / MODEL_REASONING in .env from the Token Factory catalog.")
    resp = get_client().chat.completions.create(model=model, messages=messages, **kwargs)
    msg = resp.choices[0].message
    return ChatReply(content=(msg.content or "").strip(), reasoning=_extract_reasoning(msg), raw=resp)
