"""FastAPI application factory."""

import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException  # also covers unknown routes (404)

from lens import __version__
from lens.api.routers import admin, ask, health, public
from lens.core.logging import configure_logging
from lens.core.settings import get_settings
from lens.core.tracing import configure_tracing
from lens.schemas.common import ErrorBody, ErrorResponse

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, json=settings.app_env != "dev")
    configure_tracing(settings)

    app = FastAPI(title="Lens API", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(request_id=rid)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers["x-request-id"] = rid
        return response

    # docs/09: every error uses the { error: { code, message } } shape.
    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        code = {401: "unauthorized", 403: "forbidden", 404: "not_found", 503: "unavailable"}.get(
            exc.status_code, "http_error"
        )
        body = ErrorResponse(error=ErrorBody(code=code, message=str(exc.detail)))
        return JSONResponse(body.model_dump(exclude_none=True), status_code=exc.status_code)

    @app.exception_handler(ask.RateLimited)
    async def rate_limited(request: Request, exc: ask.RateLimited) -> JSONResponse:
        msg = "You're asking faster than Lens can check sources. Please wait and try again."
        body = ErrorResponse(error=ErrorBody(code="rate_limited", message=msg, retry_after_s=exc.retry_after_s))
        return JSONResponse(body.model_dump(), status_code=429, headers={"Retry-After": str(exc.retry_after_s)})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = ", ".join(".".join(str(p) for p in e["loc"][1:]) for e in exc.errors())
        body = ErrorResponse(error=ErrorBody(code="invalid_request", message=f"Check these parameters: {fields}."))
        return JSONResponse(body.model_dump(exclude_none=True), status_code=422)

    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(public.router, prefix=API_PREFIX)
    app.include_router(ask.router, prefix=API_PREFIX)
    app.include_router(admin.router, prefix=API_PREFIX)
    app.include_router(health.router)  # bare /health for container probes
    return app


app = create_app()
