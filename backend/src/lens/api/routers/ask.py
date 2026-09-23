"""`POST /ask` (docs/09): Server-Sent Events. Status events while working, then one verified
`answer_final` or an `abstain`. No business logic here: rate-limit, call the Ask service, frame events."""

import time
from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated, Any

import redis
import structlog
from fastapi import APIRouter, Depends, Request, Response
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy.orm import Session

from lens.core.config_files import load_yaml
from lens.core.settings import get_settings
from lens.db.session import get_engine
from lens.guardrails.input import check_rate, client_key
from lens.nlp.embed import get_embedder
from lens.retrieval.qdrant_store import get_qdrant
from lens.schemas import api
from lens.schemas.common import ErrorResponse
from lens.services import ask as svc

router = APIRouter(tags=["ask"])
log = structlog.get_logger()


def open_session() -> Session:
    """The stream's own session (dependency teardown timing differs for streamed responses).
    Tests replace this to use their rolled-back session."""
    return Session(get_engine())


class RateLimited(Exception):
    def __init__(self, retry_after_s: int, reason: str) -> None:
        self.retry_after_s, self.reason = retry_after_s, reason


@lru_cache
def _redis() -> Any:
    return redis.Redis.from_url(get_settings().redis_url)


def before_stream(request: Request, response: Response) -> None:
    """Runs before the stream opens (a generator body runs too late to set headers or a status).
    G-IN-03: a blocked request gets a plain 429 (docs/09). docs/09: `/ask` is `no-store`."""
    response.headers["Cache-Control"] = "no-store"
    ip = request.client.host if request.client else "unknown"
    res = check_rate(_redis(), client_key(ip), load_yaml("guardrails.yaml")["ask"], int(time.time()))
    if not res.passed:
        raise RateLimited(res.meta["retry_after_s"], res.reason)


@router.post(
    "/ask",
    response_class=EventSourceResponse,
    responses={
        200: {"model": api.AskEvents, "description": "SSE stream; payload type per event name (docs/09)"},
        429: {"model": ErrorResponse},
    },
)
def ask(body: api.AskRequest, _: Annotated[None, Depends(before_stream)]) -> Iterator[ServerSentEvent]:
    with open_session() as db:
        try:
            graph = svc.ask_graph(db, get_qdrant(), get_embedder())
            for event, payload in svc.ask_events(db, body.query, graph, body.session_id):
                if event in ("answer_final", "abstain"):
                    db.commit()  # the audit row (G-OPS-04) is stored before the answer is sent
                yield ServerSentEvent(event=event, data=payload)
        except Exception:
            log.exception("ask.failed")  # query text is not logged (PII, G-OUT-05)
            err = api.AskError(code="internal", message="Something went wrong. Please try again.", retry_after_s=5)
            yield ServerSentEvent(event="error", data=err)
