"""Input guards for Ask (docs/07). Deterministic; run before any model call."""

from __future__ import annotations

import hashlib
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
