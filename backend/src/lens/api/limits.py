"""General rate limiting (pre-deploy checklist, docs/07 G-IN-03 extended to every route group). Budgets per
client IP (hashed, never stored raw) and bucket are in config/security.yaml `rate_limits`. Ask keeps its own
stricter, traced limit. Behind a proxy, run uvicorn with --proxy-headers and --forwarded-allow-ips set to
the proxy only, so `request.client` is the reader and not the load balancer."""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import lru_cache
from typing import Any

import redis
import structlog
from fastapi import HTTPException, Request

from lens.core.config_files import load_yaml
from lens.core.settings import get_settings
from lens.guardrails.input import client_key, rate_exceeded

log = structlog.get_logger()


class TooManyRequests(HTTPException):
    def __init__(self, reason: str, retry_after_s: int) -> None:
        super().__init__(429, reason, headers={"Retry-After": str(retry_after_s)})


@lru_cache
def _redis() -> Any:
    return redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=0.5, socket_timeout=0.5)


def limit(bucket: str, fail_closed: bool = False) -> Callable[[Request], None]:
    """FastAPI dependency. If Redis is down, reads stay up (fail open, logged); admin fails closed."""

    def dependency(request: Request) -> None:
        cfg = load_yaml("security.yaml")["rate_limits"][bucket]
        ip = request.client.host if request.client else "unknown"
        try:
            hit = rate_exceeded(_redis(), bucket, client_key(ip), cfg, int(time.time()))
        except redis.RedisError:
            log.warning("rate_limit.unavailable", bucket=bucket)
            if fail_closed:
                raise HTTPException(503, "temporarily unavailable") from None
            return
        if hit is not None:
            raise TooManyRequests(*hit)

    return dependency
