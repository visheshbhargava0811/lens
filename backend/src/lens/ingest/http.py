"""Shared HTTP client for fetching public feeds. Identifies itself honestly; never spoofs a browser."""

import httpx

from lens.core.settings import get_settings

TIMEOUT = httpx.Timeout(20.0, connect=10.0)


def user_agent() -> str:
    return get_settings().ingest_user_agent


def make_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": user_agent(), "Accept-Language": "en-IN,hi-IN;q=0.9"},
        timeout=TIMEOUT,
        follow_redirects=True,
    )
