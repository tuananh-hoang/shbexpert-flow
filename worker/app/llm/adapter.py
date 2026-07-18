"""LLM provider adapter — the ONLY place agent code touches an LLM SDK.

Reads worker/config/models.yaml for tier -> {provider, model, max_tokens}.
Agents call `complete(tier="reasoning", system=..., user=...)` and never
import `anthropic`/`openai` themselves — this is what makes "đổi provider
là đổi models.yaml, không đụng code agent" (the plan's Phần D) actually
true instead of aspirational.

LLM_MOCK=true short-circuits every tier to a deterministic templated
response (no network call, no API key needed) — required for the
DEMO_REPLAY fallback (PRD 14.4) and for developing without burning API
credits.
"""
from __future__ import annotations

import asyncio
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncIterator

import yaml

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "models.yaml"


@lru_cache(maxsize=1)
def _load_config() -> dict[str, Any]:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _tier_config(tier: str) -> dict[str, Any]:
    config = _load_config()
    try:
        return config["tiers"][tier]
    except KeyError as exc:
        raise ValueError(f"unknown model tier {tier!r} — check worker/config/models.yaml") from exc


def _mock_response(tier: str, system: str, user: str) -> str:
    """Deterministic, seed-free "response" — same input always produces the
    same output, satisfying DEMO_REPLAY without needing a fixed random seed.

    Every agent prompt in this codebase follows the same shape: substantive
    data/context first, then an instruction sentence telling the model what
    to write (starting with "Viết" / "Hãy viết"). Cutting at that sentence
    keeps the mock response readable — the data, not an echoed instruction —
    without needing any actual language generation.
    """
    body = user.strip()
    for marker in ("Viết", "Hãy viết"):
        idx = body.find(marker)
        if idx != -1:
            body = body[:idx].strip()
            break
    return f"[LLM_MOCK/{tier}] {body[:400]}"


async def complete(*, tier: str, system: str, user: str) -> str:
    """Returns the model's text response for one single-turn completion.
    Multi-turn / tool-calling loops belong in the agent code, not here —
    this function is intentionally as thin as `messages.create` gets."""
    if os.environ.get("LLM_MOCK", "false").lower() in ("1", "true", "yes"):
        return _mock_response(tier, system, user)

    cfg = _tier_config(tier)
    provider = cfg["provider"]
    model = cfg["model"]
    max_tokens = cfg.get("max_tokens", 4096)

    if provider == "anthropic":
        return await _complete_anthropic(model=model, max_tokens=max_tokens, system=system, user=user)
    if provider == "openai":
        return await _complete_openai(model=model, max_tokens=max_tokens, system=system, user=user)
    raise ValueError(f"unsupported provider {provider!r} for tier {tier!r}")


async def _complete_anthropic(*, model: str, max_tokens: int, system: str, user: str) -> str:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic()  # reads ANTHROPIC_API_KEY from env
    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


async def _complete_openai(*, model: str, max_tokens: int, system: str, user: str) -> str:
    from openai import AsyncOpenAI

    # OPENAI_BASE_URL lets this point at a self-hosted OpenAI-compatible
    # server (e.g. vLLM serving DeepSeek-V4-Flash) instead of OpenAI's cloud —
    # unset/empty falls back to the SDK default (api.openai.com).
    client = AsyncOpenAI(base_url=os.environ.get("OPENAI_BASE_URL") or None)  # reads OPENAI_API_KEY from env
    response = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Streaming variant — Chat Orchestrator (ai-architecture_v2.md §11.8) only.
# Every expert agent (financial.py, policy.py, ...) uses the single-shot
# `complete()` above and always will: they run inside a LangGraph node,
# write one Finding, and are done — there's no user watching text appear.
# Chat is the opposite: a human is looking at the screen waiting for a
# reply, so this yields text AS THE PROVIDER PRODUCES IT rather than
# buffering the whole answer — the actual behavior requested when "chatbot
# tự do như ChatGPT" was chosen over the earlier queued/buffered design.
# ---------------------------------------------------------------------------
async def stream_complete(*, tier: str, system: str, user: str) -> AsyncIterator[str]:
    if os.environ.get("LLM_MOCK", "false").lower() in ("1", "true", "yes"):
        # No real token stream to tap in mock mode — chunk the same
        # deterministic mock text word-by-word with a tiny delay so the
        # UI exercises its streaming render path in dev/demo without an
        # API key. Never used when LLM_MOCK is off.
        text = _mock_response(tier, system, user)
        for word in text.split(" "):
            yield word + " "
            await asyncio.sleep(0.02)
        return

    cfg = _tier_config(tier)
    provider = cfg["provider"]
    model = cfg["model"]
    max_tokens = cfg.get("max_tokens", 4096)

    if provider == "anthropic":
        async for chunk in _stream_anthropic(model=model, max_tokens=max_tokens, system=system, user=user):
            yield chunk
    elif provider == "openai":
        async for chunk in _stream_openai(model=model, max_tokens=max_tokens, system=system, user=user):
            yield chunk
    else:
        raise ValueError(f"unsupported provider {provider!r} for tier {tier!r}")


async def _stream_anthropic(*, model: str, max_tokens: int, system: str, user: str) -> AsyncIterator[str]:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic()
    async with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        async for text in stream.text_stream:
            yield text


async def _stream_openai(*, model: str, max_tokens: int, system: str, user: str) -> AsyncIterator[str]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(base_url=os.environ.get("OPENAI_BASE_URL") or None)
    stream = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        stream=True,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield delta
