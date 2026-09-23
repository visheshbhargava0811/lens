"""Structured LLM calls by tier (docs/02, docs/06 "Structured output rules", ADR-0022).

`structured(tier, Model, system, user, run_name=...)` returns a validated Pydantic `Model`.
- The provider and model come from config/models.yaml; nothing here names a model.
- Output is constrained with the provider's JSON-schema mode (never "answer in JSON" prose).
- Invalid output is retried with the validation error (max `MAX_FIX_RETRIES`); rate limits
  honour `retry-after` (max `MAX_RATE_RETRIES`). Then `LLMError` is raised for the caller's fallback.
- Every call is a named LangSmith run carrying tier, model and prompt version.
Tests replace `_post` (see tests/test_llm_client.py); no test calls a real provider.
"""

from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass
from typing import Any, cast

import httpx
from langsmith import traceable
from pydantic import BaseModel, ValidationError

from lens.core.config_files import load_yaml
from lens.core.settings import get_settings

MAX_FIX_RETRIES = 2
MAX_RATE_RETRIES = 3
MAX_RATE_WAIT_S = 60.0
USER_AGENT = "lens-backend/0.1"  # Groq's CDN rejects the default Python-urllib agent

ENDPOINTS = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "sarvam": "https://api.sarvam.ai/v1/chat/completions",
}


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class Tier:
    name: str
    provider: str
    model: str
    max_tokens: int
    temperature: float
    reasoning_effort: str | None = None


def tier(name: str) -> Tier:
    cfg = load_yaml("models.yaml")["tiers"][name]
    if cfg.get("provider") not in ENDPOINTS:
        raise LLMError(f"tier {name!r} has no supported provider configured: {cfg}")
    return Tier(
        name=name,
        provider=cfg["provider"],
        model=cfg["model"],
        max_tokens=int(cfg.get("max_tokens", 1024)),
        temperature=float(cfg.get("temperature", 0)),
        reasoning_effort=cfg.get("reasoning_effort"),
    )


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON schema in the shape strict decoding needs: refs inlined, every property
    required, no additional properties, no defaults or titles. Optional fields stay nullable."""
    raw = model.model_json_schema()
    defs = raw.pop("$defs", {})

    def fix(node: Any) -> Any:
        if isinstance(node, list):
            return [fix(n) for n in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return fix(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
        out = {k: fix(v) for k, v in node.items() if k not in ("title", "default")}
        if out.get("type") == "object" and "properties" in out:
            out["required"] = list(out["properties"])
            out["additionalProperties"] = False
        return out

    return fix(raw)  # type: ignore[no-any-return]


def _post(provider: str, body: dict[str, Any]) -> httpx.Response:
    s = get_settings()
    key = {"groq": s.groq_api_key, "sarvam": s.sarvam_api_key}[provider]
    if key is None:
        raise LLMError(f"{provider.upper()}_API_KEY is not set")
    headers = {"User-Agent": USER_AGENT, "Content-Type": "application/json"}
    if provider == "sarvam":
        headers["api-subscription-key"] = key.get_secret_value()
    else:
        headers["Authorization"] = f"Bearer {key.get_secret_value()}"
    return httpx.post(ENDPOINTS[provider], json=body, headers=headers, timeout=s.llm_timeout_s)


def _body(t: Tier, messages: list[dict[str, str]], schema: dict[str, Any], name: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": t.model,
        "messages": messages,
        "temperature": t.temperature,
        "response_format": {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}},
    }
    body["max_completion_tokens" if t.provider == "groq" else "max_tokens"] = t.max_tokens
    if t.reasoning_effort:
        body["reasoning_effort"] = t.reasoning_effort
    return body


def _send(t: Tier, body: dict[str, Any]) -> dict[str, Any]:
    for attempt in range(MAX_RATE_RETRIES + 1):
        try:
            r = _post(t.provider, body)
        except httpx.HTTPError as e:
            if attempt == MAX_RATE_RETRIES:
                raise LLMError(f"{t.provider} request failed: {e.__class__.__name__}") from e
            time.sleep(2**attempt)
            continue
        if r.status_code == 429 or r.status_code >= 500:
            if attempt == MAX_RATE_RETRIES:
                raise LLMError(f"{t.provider} returned {r.status_code} after {attempt + 1} tries")
            wait = float(r.headers.get("retry-after") or 2**attempt)
            time.sleep(min(wait, MAX_RATE_WAIT_S))
            continue
        if r.status_code != 200:
            raise LLMError(f"{t.provider} returned {r.status_code}: {r.text[:300]}")
        return r.json()  # type: ignore[no-any-return]
    raise AssertionError("unreachable")


def structured[T: BaseModel](
    tier_name: str,
    model: type[T],
    system: str,
    user: str,
    *,
    run_name: str,
    prompt_version: str,
    tags: list[str] | None = None,
) -> T:
    t = tier(tier_name)
    traced = traceable(
        name=run_name,
        run_type="llm",
        tags=["graph:offline", f"tier:{t.name}", *(tags or [])],
        metadata={"tier": t.name, "provider": t.provider, "model": t.model, "prompt_version": prompt_version},
    )(_structured)
    return cast(T, traced(t, model, system, user))  # traceable erases the return type


def _structured[T: BaseModel](t: Tier, model: type[T], system: str, user: str) -> T:
    schema = strict_schema(model)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    last_error = ""
    for _ in range(MAX_FIX_RETRIES + 1):
        data = _send(t, _body(t, messages, schema, model.__name__))
        choice = (data.get("choices") or [{}])[0]
        content = choice.get("message", {}).get("content") or ""
        try:
            return model.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError) as e:
            if content:
                last_error = str(e)[:1000]
            elif choice.get("finish_reason") == "length":
                last_error = f"empty content: hit max_tokens ({t.max_tokens}) while reasoning"
            else:
                last_error = "empty content"
            messages = [
                *messages,
                {"role": "assistant", "content": content},
                {"role": "user", "content": f"That output was invalid: {last_error}. Return corrected output only."},
            ]
    raise LLMError(f"{t.name}: no valid {model.__name__} after {MAX_FIX_RETRIES + 1} tries: {last_error}")
