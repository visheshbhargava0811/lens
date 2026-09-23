"""Admin endpoints (docs/09). Separate credentials: a bearer token from ADMIN_TOKEN.
Unset token means admin is disabled. Never exposed through the public web origin."""

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from lens.core.settings import get_settings
from lens.db.session import get_session
from lens.ingest.source_import import ImportRejected, import_csv
from lens.schemas.api import SourceImportResult
from lens.schemas.common import ErrorBody, ErrorResponse


def require_admin(authorization: Annotated[str | None, Header()] = None) -> None:
    token = get_settings().admin_token
    if token is None:
        raise HTTPException(503, "Admin endpoints are disabled: ADMIN_TOKEN is not set.")
    given = (authorization or "").removeprefix("Bearer ").encode()
    if not hmac.compare_digest(given, token.get_secret_value().encode()):
        raise HTTPException(401, "Admin credentials are missing or wrong.")


router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


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
    try:
        r = import_csv(db, text)
    except ImportRejected as e:
        db.rollback()
        msg = "Nothing was imported. Fix these rows: " + "; ".join(e.errors)
        body = ErrorResponse(error=ErrorBody(code="import_rejected", message=msg))
        return JSONResponse(body.model_dump(), status_code=422)
    db.commit()
    return SourceImportResult(ownership_added=r.ownership_added, ratings_added=r.ratings_added, unchanged=r.unchanged)
