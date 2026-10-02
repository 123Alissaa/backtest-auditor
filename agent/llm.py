"""Thin wrapper around Token Factory's OpenAI-compatible chat API.

Nemotron models on Token Factory are reasoning models: the final answer may be
in `content`, with the thinking in a separate field -- and some integrations
have seen `content` come back empty. We capture both. Verified 2026-10-01:
Nano returns `reasoning`; Super returns both `reasoning` and
`reasoning_content`. `content` comes back with a leading newline.
Verified 2026-10-02: with reasoning_effort="none", Nano puts its JSON answer
in `reasoning` and leaves `content` empty -- chat_json() handles that.
"""
import json
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


class LLMJSONError(RuntimeError):
    """The model didn't return valid JSON after retrying."""


def chat_json(messages: list[dict], model: str, schema: dict, name: str, retries: int = 1, **kwargs) -> dict:
    """Chat with a strict JSON schema and return the parsed object.

    Falls back to the reasoning field when `content` is empty (seen on Nano),
    and retries on invalid JSON.
    """
    response_format = {"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}}
    last = ""
    for _ in range(retries + 1):
        reply = chat(messages, model=model, response_format=response_format, **kwargs)
        for text in (reply.content, (reply.reasoning or "").strip()):
            if not text:
                continue
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                last = text
    raise LLMJSONError(f"{model} returned no valid JSON for {name!r}: {last[:200]!r}")
