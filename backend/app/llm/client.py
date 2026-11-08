"""The ONE place the app talks to an LLM.

Handles: timeouts, one retry, structured-output parsing + Pydantic validation, redacted logging
of every call (prompt summary, output, latency, tokens) to the llm_calls table. Callers get an
LLMResult and never see an exception: a failed call is simply ok=False.
"""
import asyncio
import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import BACKEND_DIR, settings
from app.db import SessionLocal
from app.llm import mock
from app.models import LLMCall
from app.redact import redact

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMResult:
    ok: bool
    data: Any = None  # a validated Pydantic object when ok
    error: str | None = None


@lru_cache
def prompt(name: str) -> str:
    return (BACKEND_DIR / "prompts" / f"{name}.md").read_text()


@lru_cache
def _client():
    from openai import AsyncOpenAI
    # One shared client = connection pooling across calls. SDK retries disabled: we retry ourselves.
    return AsyncOpenAI(api_key=settings.openai_api_key, timeout=settings.llm_timeout_seconds, max_retries=0)


async def call_llm(*, purpose: str, model: str, schema: type[T], messages: list[dict],
                   prompt_summary: str, mock_input: dict, run_id: int | None) -> LLMResult:
    started = time.monotonic()
    tries, tokens_in, tokens_out = 0, 0, 0
    data, error = None, None

    for tries in (1, 2):  # first try + one retry
        try:
            if settings.llm_mode == "mock":
                raw = await mock.respond(purpose, mock_input)
                data = schema.model_validate(raw)
            else:
                extra = {"reasoning_effort": "low"} if model.startswith(("gpt-5", "o")) else {"temperature": 0}
                completion = await asyncio.wait_for(
                    _client().chat.completions.parse(model=model, messages=messages, response_format=schema, **extra),
                    timeout=settings.llm_timeout_seconds,
                )
                message = completion.choices[0].message
                if message.refusal or message.parsed is None:
                    raise ValueError("model refused or returned no parsable output")
                data = schema.model_validate(message.parsed.model_dump())  # validate again ourselves
                if completion.usage:
                    tokens_in += completion.usage.prompt_tokens
                    tokens_out += completion.usage.completion_tokens
            error = None
            break
        except (ValidationError, ValueError) as exc:
            error = f"invalid output: {type(exc).__name__}"
        except asyncio.TimeoutError:
            error = "timeout"
        except Exception as exc:
            error = f"{type(exc).__name__}"
        data = None

    latency_ms = int((time.monotonic() - started) * 1000)
    _record(run_id, purpose, model, prompt_summary, data, error, tries, latency_ms, tokens_in, tokens_out)
    if error:
        log.warning("llm call failed purpose=%s tries=%s error=%s", purpose, tries, error)
        return LLMResult(ok=False, error=error)
    return LLMResult(ok=True, data=data)


def _record(run_id, purpose, model, summary, data, error, tries, latency_ms, tokens_in, tokens_out):
    with SessionLocal() as db:
        db.add(LLMCall(
            run_id=run_id, purpose=purpose,
            model=model if settings.llm_mode != "mock" else f"mock:{model}",
            prompt_summary=redact(summary), output_json=redact(data.model_dump()) if data else None,
            ok=error is None, error=error, attempts=tries, latency_ms=latency_ms,
            tokens_in=tokens_in, tokens_out=tokens_out,
        ))
        db.commit()
