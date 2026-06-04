"""
Async-safe context for the most recent LLM call + generation audit row.

Mirrors src/utils/correlation.py: the llm_client writes call metadata
(model, token usage, raw content, latency) into a ContextVar as a side
effect of `complete()`, so the outer audit layer can read it without the
return signature of `complete()` having to carry it through every caller.

`last_generation_id` lets the route backfill `application_id` onto the
audit row after the application has been logged (the audit row is written
inside the LLM step, before the application exists).
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class LLMCallMeta:
    model: str = ""
    provider: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    raw_content: str = ""
    duration_ms: int = 0


_llm_meta: ContextVar[LLMCallMeta | None] = ContextVar("llm_meta", default=None)
_last_generation_id: ContextVar[uuid.UUID | None] = ContextVar(
    "last_generation_id", default=None
)
_preview_mode: ContextVar[bool] = ContextVar("preview_mode", default=False)


def reset_llm_meta() -> None:
    """Clear any stale meta at the start of a tracked call."""
    _llm_meta.set(LLMCallMeta())


def set_llm_meta(meta: LLMCallMeta) -> None:
    _llm_meta.set(meta)


def get_llm_meta() -> LLMCallMeta | None:
    return _llm_meta.get()


def set_last_generation_id(value: uuid.UUID) -> None:
    _last_generation_id.set(value)


def get_last_generation_id() -> uuid.UUID | None:
    return _last_generation_id.get()


def set_preview_mode(value: bool) -> None:
    _preview_mode.set(value)


def get_preview_mode() -> bool:
    return _preview_mode.get()
