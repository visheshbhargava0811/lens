"""Admin endpoints (docs/09). Separate credentials: a bearer token from ADMIN_TOKEN.
Unset token means admin is disabled. Never exposed through the public web origin."""

import hmac
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from lens.api.limits import limit
from lens.core.config_files import load_yaml
from lens.core.logging import get_logger
from lens.core.settings import get_settings
from lens.db.models import GuardEvent
from lens.db.session import get_session
from lens.ingest.source_import import ImportRejected, import_csv
from lens.ops import kill
from lens.schemas.api import SourceImportResult
from lens.schemas.common import ErrorBody, ErrorResponse
from lens.services import review

log = get_logger(__name__)


def require_admin(authorization: Annotated[str | None, Header()] = None) -> None:
    token = get_settings().admin_token
    if token is None or not token.get_secret_value():  # an empty token never matches (ADR-0042)
        raise HTTPException(503, "Admin endpoints are disabled: ADMIN_TOKEN is not set.")
    given = (authorization or "").removeprefix("Bearer ").encode()
    if not given or not hmac.compare_digest(given, token.get_secret_value().encode()):
        raise HTTPException(401, "Admin credentials are missing or wrong.")


# The limit runs before the token check, so it also slows token guessing; it fails closed.
router = APIRouter(
    prefix="/admin", tags=["admin"], dependencies=[Depends(limit("admin", fail_closed=True)), Depends(require_admin)]
)


@router.post(
    "/sources/import",
    response_model=SourceImportResult,
    responses={422: {"model": ErrorResponse}},
    openapi_extra={"requestBody": {"required": True, "content": {"text/csv": {"schema": {"type": "string"}}}}},
)
async def import_sources(
    request: Request, db: Annotated[Session, Depends(get_session)]
) -> SourceImportResult | JSONResponse:
    """Body: the CSV itself (Content-Type: text/csv). Columns: see lens.ingest.source_import."""
    try:
        text = (await request.body()).decode("utf-8")
    except UnicodeDecodeError:
        body = ErrorResponse(error=ErrorBody(code="import_rejected", message="The file must be UTF-8 CSV."))
        return JSONResponse(body.model_dump(), status_code=422)
    if "\x00" in text:
        body = ErrorResponse(error=ErrorBody(code="import_rejected", message="The file contains invalid characters."))
        return JSONResponse(body.model_dump(), status_code=422)
    try:
        r = import_csv(db, text)
    except ImportRejected as e:
        db.rollback()
        msg = "Nothing was imported. Fix these rows: " + "; ".join(e.errors)
        body = ErrorResponse(error=ErrorBody(code="import_rejected", message=msg))
        return JSONResponse(body.model_dump(), status_code=422)
    db.commit()
    return SourceImportResult(ownership_added=r.ownership_added, ratings_added=r.ratings_added, unchanged=r.unchanged)


@router.get("/review-queue")
def review_queue(db: Annotated[Session, Depends(get_session)]) -> dict[str, list[dict[str, Any]]]:
    """Held story summaries (G-OUT-07), oldest first."""
    return {"items": review.open_items(db)}


class Resolved(BaseModel):
    status: Literal["approved", "rejected"]


@router.post("/review-queue/{item_id}/resolve", response_model=Resolved, responses={404: {"model": ErrorResponse}})
def resolve_review(
    item_id: uuid.UUID, decision: Literal["approve", "reject"], db: Annotated[Session, Depends(get_session)]
) -> Resolved | JSONResponse:
    if not review.resolve(db, item_id, decision, reviewer="admin"):
        body = ErrorResponse(error=ErrorBody(code="not_found", message="No open review item with that id."))
        return JSONResponse(body.model_dump(), status_code=404)
    db.commit()
    return Resolved(status="approved" if decision == "approve" else "rejected")


# ---------------------------------------------------------------- kill switch (G-OPS-03, ADR-0045)


class StoryKill(BaseModel):
    story_id: str
    killed: bool


def _story_kill(db: Session, story_id: uuid.UUID, killed: bool) -> StoryKill | JSONResponse:
    if not kill.set_story_killed(db, story_id, killed):
        body = ErrorResponse(error=ErrorBody(code="not_found", message="No story with that id."))
        return JSONResponse(body.model_dump(), status_code=404)
    db.commit()
    log.warning("ops.story_kill", story_id=str(story_id), killed=killed)
    return StoryKill(story_id=str(story_id), killed=killed)


@router.post("/stories/{story_id}/kill", response_model=StoryKill, responses={404: {"model": ErrorResponse}})
def kill_story(story_id: uuid.UUID, db: Annotated[Session, Depends(get_session)]) -> StoryKill | JSONResponse:
    """Takes a story down: hidden everywhere, never analysed, never Ask evidence."""
    return _story_kill(db, story_id, True)


@router.post("/stories/{story_id}/restore", response_model=StoryKill, responses={404: {"model": ErrorResponse}})
def restore_story(story_id: uuid.UUID, db: Annotated[Session, Depends(get_session)]) -> StoryKill | JSONResponse:
    return _story_kill(db, story_id, False)


class GenerationSwitch(BaseModel):
    off: bool = False  # no live generation anywhere
    off_topics: list[str] = []  # no live generation for stories in these topics


@router.get("/kill-switch", response_model=GenerationSwitch)
def get_kill_switch(db: Annotated[Session, Depends(get_session)]) -> GenerationSwitch:
    g = kill.generation(db)
    return GenerationSwitch(off=g.off, off_topics=sorted(g.off_topics))


@router.post("/kill-switch", response_model=GenerationSwitch, responses={422: {"model": ErrorResponse}})
def set_kill_switch(
    body: GenerationSwitch, db: Annotated[Session, Depends(get_session)]
) -> GenerationSwitch | JSONResponse:
    """Global and per-topic switch for live generation; story pages keep their stored verified summaries."""
    known = set(load_yaml("memory.yaml")["values"]["followed_topics"])
    unknown = sorted(set(body.off_topics) - known)
    if unknown:
        msg = f"Unknown topics: {', '.join(unknown)}. Known: {', '.join(sorted(known))}."
        return JSONResponse(
            ErrorResponse(error=ErrorBody(code="unknown_topic", message=msg)).model_dump(), status_code=422
        )
    g = kill.set_generation(db, body.off, body.off_topics)
    db.commit()
    log.warning("ops.kill_switch", off=g.off, off_topics=sorted(g.off_topics))
    return GenerationSwitch(off=g.off, off_topics=sorted(g.off_topics))


@router.get("/guard-events")
def guard_events(
    db: Annotated[Session, Depends(get_session)], limit_: Annotated[int, Query(alias="limit", ge=1, le=500)] = 100
) -> dict[str, list[dict[str, Any]]]:
    """Most recent guard events, newest first (docs/09)."""
    rows = db.execute(select(GuardEvent).order_by(GuardEvent.created_at.desc()).limit(limit_)).scalars()
    return {
        "items": [
            {
                "id": str(e.id),
                "run_id": e.run_id,
                "guard_id": e.guard_id,
                "stage": e.stage,
                "passed": e.passed,
                "action": e.action,
                "reason": e.reason,
                "created_at": e.created_at.isoformat(),
            }
            for e in rows
        ]
    }
