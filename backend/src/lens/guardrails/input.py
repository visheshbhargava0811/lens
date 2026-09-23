"""Input guards for Ask (docs/07). Deterministic; run before any model call."""

from __future__ import annotations

import hashlib
import re
import secrets
from collections.abc import Mapping
from typing import Any, Protocol

from lens.guardrails.base import GuardResult, traced_guard


class Counter(Protocol):
    def incr(self, name: str) -> Any: ...
    def expire(self, name: str, time: int) -> Any: ...
    def ttl(self, name: str) -> Any: ...


_SALT = secrets.token_bytes(16)  # per process: counters reset on restart, which a rate limiter tolerates


def client_key(ip: str) -> str:
    """Rate-limit key. The raw IP is never stored (G-OUT-05); the salt keeps the hash from being reversed
    by enumerating the IPv4 space."""
    return hashlib.sha256(_SALT + ip.encode()).hexdigest()[:16]


@traced_guard("G-IN-03", "input")
def check_rate(counter: Counter, client: str, cfg: Mapping[str, Any], now_s: int) -> GuardResult:
    """Fixed-window limits per client: per minute and per day. Blocks with a retry-after."""
    for window, limit in ((60, cfg["rate_per_minute"]), (86_400, cfg["rate_per_day"])):
        key = f"ask:rate:{client}:{window}:{now_s // window}"
        n = int(counter.incr(key))
        if n == 1:
            counter.expire(key, window)
        if n > limit:
            retry = int(counter.ttl(key))
            return GuardResult(
                guard_id="G-IN-03",
                passed=False,
                action="block",
                reason=f"more than {limit} questions per {'minute' if window == 60 else 'day'}",
                meta={"retry_after_s": max(retry, 1)},
            )
    return GuardResult(guard_id="G-IN-03", passed=True, action="allow", reason="within limits")


# G-IN-02: attempts to steer the assistant, in the reader's text. Narrower than a classifier on
# purpose: a normal news question must never be blocked (benign false-block rate is gated).
_USER_INJECTION = re.compile(
    r"(ignore|disregard|forget|override)\s+(all\s+|any\s+)?(the\s+|your\s+)?(previous|prior|above|earlier|system)\s+"
    r"(instructions|rules|prompts?|guidelines)"
    r"|(ignore|disregard|forget|override)\s+(all\s+)?your\s+(instructions|rules|guidelines|programming)"
    r"|\b(reveal|show|print|repeat)\s+(me\s+)?(your|the)\s+(system\s+)?(prompt|instructions)\b"
    r"|\byou\s+are\s+now\b|\bact\s+as\s+(an?\s+)?(unfiltered|jailbroken|dan)\b|\bjailbreak\b|\bdeveloper\s+mode\b"
    r"|पिछले\s+(सभी\s+)?निर्देश(ों)?\s+(को\s+)?(अनदेखा|नज़रअंदाज़|नजरअंदाज)|सिस्टम\s+प्रॉम्प्ट"
    r"|(pichhle|pichle)\s+(sare\s+)?(instructions|nirdesh)\s+(ignore|bhool)",
    re.IGNORECASE,
)


@traced_guard("G-IN-02", "input")
def check_user_injection(text: str) -> GuardResult:
    """User text is always data; this blocks clear attempts to change the assistant's instructions
    before any model call."""
    m = _USER_INJECTION.search(text)
    if m:
        return GuardResult(
            guard_id="G-IN-02", passed=False, action="block", reason="instruction-override attempt in question"
        )
    return GuardResult(guard_id="G-IN-02", passed=True, action="allow", reason="no override attempt")


@traced_guard("G-IN-01", "input")
def check_scope(intent: str, rationale: str) -> GuardResult:
    """Scope decision from query understanding (the classifier), recorded as a guard."""
    if intent == "unsupported":
        return GuardResult(
            guard_id="G-IN-01", passed=False, action="block", reason="out of scope", meta={"why": rationale[:300]}
        )
    return GuardResult(guard_id="G-IN-01", passed=True, action="allow", reason=f"intent {intent}")


@traced_guard("G-IN-04", "input")
def check_language(language: str, confidence: float, min_confidence: float) -> GuardResult:
    """Low language-ID confidence: answer in English and say so (docs/07)."""
    if confidence < min_confidence:
        return GuardResult(
            guard_id="G-IN-04",
            passed=False,
            action="allow",
            reason=f"language {language} at confidence {confidence:.2f}",
            score=confidence,
            meta={"fallback_language": "en"},
        )
    return GuardResult(guard_id="G-IN-04", passed=True, action="allow", reason=f"language {language}", score=confidence)
