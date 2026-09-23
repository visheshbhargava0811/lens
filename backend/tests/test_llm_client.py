"""LLM client: schema shaping, validation and rate-limit retries, and provider fallback (Gemini).
`_post` is faked per provider; no test calls a real provider."""

import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, Field

from lens.llm import client
from lens.llm.client import LLMError, strict_schema, structured, tier_chain


class Inner(BaseModel):
    n: int = Field(description="a number")


class Out(BaseModel):
    reasoning: str
    items: list[Inner]
    note: str | None = None


OK: dict[str, Any] = {"reasoning": "r", "items": [], "note": None}


def _resp(status: int, content: Any = None, headers: dict[str, str] | None = None) -> httpx.Response:
    text = content if isinstance(content, str) else json.dumps(content)
    body = {"choices": [{"message": {"content": text}}]}
    return httpx.Response(status, json=body, headers=headers or {}, request=httpx.Request("POST", "https://x"))


def _err(status: int, text: str = "err", headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status, text=text, headers=headers or {}, request=httpx.Request("POST", "https://x"))


class Fake:
    """Stands in for the providers: per-provider response queues; records requests and sleeps.
    A provider with an empty queue behaves as down (HTTP 503)."""

    def __init__(self) -> None:
        self.queues: dict[str, list[httpx.Response]] = {"groq": [], "sarvam": [], "gemini": []}
        self.requests: list[dict[str, Any]] = []
        self.slept: list[float] = []

    def post(self, provider: str, body: dict[str, Any]) -> httpx.Response:
        self.requests.append({"provider": provider, **body})
        q = self.queues[provider]
        return q.pop(0) if q else _err(503, headers={"retry-after": "999"})

    def providers(self) -> list[str]:
        return [r["provider"] for r in self.requests]


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Fake:
    f = Fake()
    monkeypatch.setattr(client, "_post", f.post)
    monkeypatch.setattr("lens.llm.client.time.sleep", f.slept.append)
    return f


def test_strict_schema_inlines_refs_and_requires_everything() -> None:
    s = strict_schema(Out)
    assert "$defs" not in json.dumps(s)
    assert s["required"] == ["reasoning", "items", "note"] and s["additionalProperties"] is False
    inner = s["properties"]["items"]["items"]
    assert inner["required"] == ["n"] and inner["additionalProperties"] is False
    assert inner["properties"]["n"]["description"] == "a number"  # descriptions guide the model


def test_valid_output_is_parsed_and_request_uses_json_schema(fake: Fake) -> None:
    fake.queues["groq"].append(_resp(200, {"reasoning": "r", "items": [{"n": 1}], "note": None}))
    meta: dict[str, str] = {}
    out = structured("synthesis", Out, "sys", "user", run_name="t", prompt_version="1", meta=meta)
    assert out.items[0].n == 1
    req = fake.requests[0]
    assert req["provider"] == "groq" and req["response_format"]["json_schema"]["strict"] is True
    assert "max_completion_tokens" in req
    assert meta["provider"] == "groq" and meta["fallback"] == "false"


def test_invalid_output_is_retried_with_the_error(fake: Fake) -> None:
    fake.queues["groq"].extend([_resp(200, "not json"), _resp(200, OK)])
    assert structured("analysis", Out, "sys", "user", run_name="t", prompt_version="1").reasoning == "r"
    assert "invalid" in fake.requests[1]["messages"][-1]["content"]


def test_rate_limit_waits_short_retry_after_then_succeeds(fake: Fake) -> None:
    fake.queues["groq"].extend([_resp(429, headers={"retry-after": "7"}), _resp(200, OK)])
    structured("analysis", Out, "sys", "user", run_name="t", prompt_version="1")
    assert fake.slept == [7.0] and fake.providers() == ["groq", "groq"]


def test_long_retry_after_fails_over_to_gemini_without_waiting(fake: Fake) -> None:
    fake.queues["groq"].append(_resp(429, headers={"retry-after": "300"}))
    fake.queues["gemini"].append(_resp(200, OK))
    meta: dict[str, str] = {}
    structured("synthesis", Out, "sys", "user", run_name="t", prompt_version="1", meta=meta)
    # The other Groq model is down too (empty queue), so the chain reaches Gemini; nobody waited.
    first_gemini = next(t for t in tier_chain("synthesis") if t.provider == "gemini")
    assert fake.slept == [] and fake.providers()[-1] == "gemini"
    assert meta == {"provider": "gemini", "model": first_gemini.model, "family": "gemini", "fallback": "true"}
    assert "max_tokens" in fake.requests[-1]  # Gemini's OpenAI-compatible body


def test_invalid_output_after_fix_retries_fails_over(fake: Fake) -> None:
    fake.queues["groq"].extend([_resp(200, "")] * (client.MAX_FIX_RETRIES + 1))
    fake.queues["gemini"].append(_resp(200, OK))
    assert structured("analysis", Out, "sys", "user", run_name="t", prompt_version="1").reasoning == "r"


def test_second_gemini_model_is_tried_when_the_first_is_down(fake: Fake) -> None:
    fake.queues["groq"].append(_err(400, "bad"))
    fake.queues["gemini"].extend([_err(503, headers={"retry-after": "999"}), _resp(200, OK)])
    structured("analysis", Out, "sys", "user", run_name="t", prompt_version="1")
    models = [r["model"] for r in fake.requests if r["provider"] == "gemini"]
    assert models == [t.model for t in tier_chain("analysis") if t.provider == "gemini"][:2]


def test_groq_models_back_each_other_up_before_gemini(fake: Fake) -> None:
    fake.queues["groq"].extend([_resp(429, headers={"retry-after": "900"}), _resp(200, OK)])
    meta: dict[str, str] = {}
    structured("analysis", Out, "sys", "user", run_name="t", prompt_version="1", meta=meta)
    assert fake.providers() == ["groq", "groq"] and meta["model"] == tier_chain("analysis")[1].model


def test_every_provider_failing_raises_with_all_reasons(fake: Fake) -> None:
    fake.queues["groq"].append(_err(400, "bad schema"))
    with pytest.raises(LLMError, match="every provider failed") as exc:
        structured("analysis", Out, "sys", "user", run_name="t", prompt_version="1")
    assert "bad schema" in str(exc.value) and "gemini" in str(exc.value)


def test_judge_skips_a_fallback_of_the_summarizers_family(fake: Fake) -> None:
    # The primary judge is down; Gemini wrote the summary, so a Gemini judge would grade its own family.
    with pytest.raises(LLMError, match="family gemini excluded"):
        structured("judge", Out, "sys", "user", run_name="t", prompt_version="1", exclude_families={"gemini"})
    assert "gemini" not in fake.providers()


def test_judge_falls_back_to_sarvam_last_when_credits_return(fake: Fake) -> None:
    fake.queues["sarvam"].append(_resp(200, OK))  # groq and gemini down
    meta: dict[str, str] = {}
    structured("judge", Out, "sys", "user", run_name="t", prompt_version="1", meta=meta)
    assert fake.providers()[-1] == "sarvam" and meta["family"] == "sarvam"
    req = fake.requests[-1]
    assert "max_tokens" in req and req["reasoning_effort"] == "low"


def test_judge_family_differs_from_the_summarizer() -> None:
    assert tier_chain("judge")[0].family != tier_chain("synthesis")[0].family
