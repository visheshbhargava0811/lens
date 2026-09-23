"""LLM client: schema shaping, validation retries, rate-limit retries. `_post` is faked; no real calls."""

import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, Field

from lens.llm import client
from lens.llm.client import LLMError, strict_schema, structured


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


class Fake:
    """Stands in for the provider: returns queued responses and records requests and sleeps."""

    def __init__(self) -> None:
        self.queue: list[httpx.Response] = []
        self.requests: list[dict[str, Any]] = []
        self.slept: list[float] = []

    def post(self, provider: str, body: dict[str, Any]) -> httpx.Response:
        self.requests.append({"provider": provider, **body})
        return self.queue.pop(0)


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
    fake.queue.append(_resp(200, {"reasoning": "r", "items": [{"n": 1}], "note": None}))
    out = structured("synthesis", Out, "sys", "user", run_name="t", prompt_version="1")
    assert out.items[0].n == 1
    req = fake.requests[0]
    assert req["provider"] == "groq" and req["response_format"]["json_schema"]["strict"] is True
    assert "max_completion_tokens" in req


def test_invalid_output_is_retried_with_the_error(fake: Fake) -> None:
    fake.queue.extend([_resp(200, "not json"), _resp(200, OK)])
    assert structured("analysis", Out, "sys", "user", run_name="t", prompt_version="1").reasoning == "r"
    assert "invalid" in fake.requests[1]["messages"][-1]["content"]


def test_gives_up_after_bounded_fix_retries(fake: Fake) -> None:
    fake.queue.extend([_resp(200, "")] * (client.MAX_FIX_RETRIES + 1))
    with pytest.raises(LLMError, match="empty content"):
        structured("analysis", Out, "sys", "user", run_name="t", prompt_version="1")


def test_rate_limit_waits_retry_after_then_succeeds(fake: Fake) -> None:
    fake.queue.extend([_resp(429, headers={"retry-after": "7"}), _resp(200, OK)])
    structured("analysis", Out, "sys", "user", run_name="t", prompt_version="1")
    assert fake.slept == [7.0]


def test_judge_tier_uses_sarvam_body(fake: Fake) -> None:
    fake.queue.append(_resp(200, OK))
    structured("judge", Out, "sys", "user", run_name="t", prompt_version="1")
    req = fake.requests[0]
    assert req["provider"] == "sarvam" and "max_tokens" in req and req["reasoning_effort"] == "low"


def test_client_error_is_not_retried(fake: Fake) -> None:
    fake.queue.append(httpx.Response(400, text="bad schema", request=httpx.Request("POST", "https://x")))
    with pytest.raises(LLMError, match="400"):
        structured("analysis", Out, "sys", "user", run_name="t", prompt_version="1")
