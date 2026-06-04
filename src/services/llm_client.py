"""
LLM provider abstraction.

A thin async wrapper around an OpenAI-compatible chat-completions endpoint
(`POST {base_url}/chat/completions`). The same client targets:

  - a locally deployed model (e.g. Ollama, vLLM, llama.cpp server) — set
    LLM_BASE_URL=http://localhost:11434/v1 and LLM_API_KEY may be blank
  - OpenAI / Together / Groq / Fireworks / Anyscale / etc. — set
    LLM_BASE_URL and LLM_API_KEY accordingly

Only one entry point: `complete(prompt, *, system=None, json=True)`.
When `json=True`, the response is parsed as JSON and returned as a dict;
otherwise raw text is returned. Callers handle validation (e.g. into a
Pydantic schema).

Errors are surfaced as `LLMError` so route handlers can map them to a
clean 502 instead of an opaque 500.
"""
from __future__ import annotations

import json as _json
import re
import time
from typing import Any

import httpx

from src.core.config import settings
from src.utils.llm_context import LLMCallMeta, set_llm_meta
from src.utils.logger import get_logger

logger = get_logger(__name__)


class LLMError(RuntimeError):
    """Raised when the upstream LLM call fails or returns unusable output."""


def _strip_json_fences(text: str) -> str:
    """Best-effort extraction of a JSON object from raw model output.

    Many open models wrap JSON in ```json ... ``` fences or precede it
    with a short preamble. We strip fences, then fall back to the first
    `{...}` block found.
    """
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    # Fallback: greedy brace match from first '{' to last '}'.
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return text


async def complete(
    prompt: str,
    *,
    system: str | None = None,
    json: bool = True,
    temperature: float = 0.2,
) -> Any:
    """Run a single chat completion against the configured LLM.

    Args:
        prompt: User-turn content.
        system: Optional system-turn content.
        json: If True, parse the response as JSON and return a dict/list.
              If False, return the raw text.
        temperature: Sampling temperature.

    Returns:
        Parsed JSON (when `json=True`) or raw string.

    Raises:
        LLMError on network failure, HTTP error, or unparseable output.
    """
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    body: dict[str, Any] = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    # Hint OpenAI-compatible servers to emit JSON when supported. Servers
    # that don't recognise the field simply ignore it.
    if json:
        body["response_format"] = {"type": "json_object"}

    api_key = settings.LLM_API_KEY.get_secret_value() if settings.LLM_API_KEY else ""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    url = settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SEC) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error(
            "LLM HTTP error",
            extra={"status": e.response.status_code, "url": url, "body": e.response.text[:500]},
        )
        raise LLMError(f"LLM upstream returned {e.response.status_code}") from e
    except httpx.HTTPError as e:
        logger.error("LLM network error", extra={"url": url, "error": str(e)})
        raise LLMError(f"LLM network error: {e}") from e

    duration_ms = int((time.perf_counter() - start) * 1000)

    try:
        content: str = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        logger.error("LLM response malformed", extra={"payload": payload})
        raise LLMError("LLM response missing choices[0].message.content") from e

    # Record call metadata for the audit layer (token usage, latency, raw
    # output). Stored in a ContextVar so callers don't have to thread it
    # through their return types. Set before JSON parsing so a parse
    # failure still has the raw content to log.
    usage = payload.get("usage") or {}
    set_llm_meta(
        LLMCallMeta(
            model=payload.get("model") or settings.LLM_MODEL,
            provider=settings.LLM_PROVIDER,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            raw_content=content,
            duration_ms=duration_ms,
        )
    )

    if not json:
        return content

    try:
        return _json.loads(_strip_json_fences(content))
    except _json.JSONDecodeError as e:
        logger.error("LLM JSON parse failed", extra={"content_preview": content[:500]})
        raise LLMError(f"LLM returned unparseable JSON: {e}") from e
