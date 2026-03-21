"""
LLM client — auto-selects Groq or Anthropic based on available API keys.

Priority: GROQ_API_KEY → ANTHROPIC_API_KEY
Groq is free tier; Anthropic requires a paid API account.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Groq model IDs
GROQ_FILTER_MODEL = "llama-3.1-8b-instant"       # fast, free, good for classification
GROQ_SUMMARIZE_MODEL = "llama-3.3-70b-versatile"  # capable, free tier

# Anthropic fallback model IDs
ANTHROPIC_FILTER_MODEL = "claude-haiku-4-5"
ANTHROPIC_SUMMARIZE_MODEL = "claude-sonnet-4-6"


def get_provider() -> str:
    """Return 'groq' or 'anthropic' based on which key is available."""
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    raise RuntimeError(
        "No LLM API key found. Set GROQ_API_KEY (free) or ANTHROPIC_API_KEY."
    )


async def chat(
    system: str,
    user: str,
    role: str = "filter",  # "filter" | "summarize"
) -> str:
    """
    Send a chat completion request to whichever provider is configured.
    Returns the assistant text response.
    """
    provider = get_provider()

    if provider == "groq":
        return await _groq_chat(system, user, role)
    return await _anthropic_chat(system, user, role)


async def _groq_chat(system: str, user: str, role: str) -> str:
    from groq import AsyncGroq  # type: ignore[import]

    model = GROQ_FILTER_MODEL if role == "filter" else GROQ_SUMMARIZE_MODEL
    client = AsyncGroq(api_key=os.environ["GROQ_API_KEY"])

    response = await client.chat.completions.create(
        model=model,
        max_tokens=4096 if role == "summarize" else 2048,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    logger.debug("Groq (%s): %d tokens used", model, response.usage.total_tokens)
    return response.choices[0].message.content or ""


async def _anthropic_chat(system: str, user: str, role: str) -> str:
    import anthropic

    model = ANTHROPIC_FILTER_MODEL if role == "filter" else ANTHROPIC_SUMMARIZE_MODEL
    client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    response = await client.messages.create(
        model=model,
        max_tokens=4096 if role == "summarize" else 2048,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return next((b.text for b in response.content if b.type == "text"), "")
