"""Public read endpoints (docs/09). No business logic here: parse, call a service, shape errors."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from lens.db.session import get_session
from lens.schemas import api
from lens.schemas.common import ErrorBody, ErrorResponse
from lens.services import stories as svc

router = APIRouter(tags=["public"])
DB = Annotated[Session, Depends(get_session)]
NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorResponse}}


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(ErrorResponse(error=ErrorBody(code=code, message=message)).model_dump(), status_code=status)


@router.get("/feed", response_model=api.StoryCardPage, responses={400: {"model": ErrorResponse}})
def feed(
    db: DB,
    response: Response,
    tab: Literal["home", "blindspot", "local"] = "home",
    topic: str | None = None,
    state: str | None = None,
    lang: str | None = None,  # display language; story headlines stay in their original language
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> api.StoryCardPage | JSONResponse:
    try:
        page = svc.feed(db, tab=tab, topic=topic, state=state, cursor=cursor, limit=limit)
    except ValueError:
        return _error(400, "invalid_cursor", "This page link has expired. Reload the feed to start again.")
    response.headers["Cache-Control"] = "public, max-age=30, stale-while-revalidate=60"
    return page


@router.get("/stories/{id_or_slug}", response_model=api.StoryDetail, responses=NOT_FOUND)
def story(db: DB, id_or_slug: str, lang: str | None = None) -> api.StoryDetail | JSONResponse:
    s = svc.find_story(db, id_or_slug)
    if s is None:
        return _error(404, "not_found", "No story with that id.")
    return svc.story_detail(db, s)


@router.get("/stories/{id_or_slug}/articles", response_model=api.StoryArticles, responses=NOT_FOUND)
def story_articles(
    db: DB,
    id_or_slug: str,
    group: Literal["stance", "language", "all"] = "all",  # grouping is done by the client
    stance: str | None = None,
    lang: str | None = None,
) -> api.StoryArticles | JSONResponse:
    s = svc.find_story(db, id_or_slug)
    if s is None:
        return _error(404, "not_found", "No story with that id.")
    return svc.story_articles(db, s, stance=stance, lang=lang)


@router.get("/blindspots", response_model=api.Blindspots)
def blindspots(db: DB, type: Literal["stance", "language"] = "stance", lang: str | None = None) -> api.Blindspots:
    return svc.blindspots(db, type)


@router.get("/topics", response_model=api.Topics)
def topics(db: DB, lang: str | None = None) -> api.Topics:
    return svc.topics(db)


@router.get("/sources", response_model=api.SourceList)
def sources(db: DB) -> api.SourceList:
    return svc.sources(db)


@router.get("/sources/{id_or_slug}", response_model=api.SourceDetail, responses=NOT_FOUND)
def source(db: DB, id_or_slug: str) -> api.SourceDetail | JSONResponse:
    s = svc.find_source(db, id_or_slug)
    if s is None:
        return _error(404, "not_found", "No source with that id.")
    return svc.source_detail(db, s)


@router.get("/methodology", response_model=api.Methodology)
def methodology(db: DB) -> api.Methodology:
    return svc.methodology(db)
