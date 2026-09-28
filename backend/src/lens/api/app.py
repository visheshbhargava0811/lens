"""FastAPI application factory."""

import re
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException  # also covers unknown routes (404)

from lens import __version__
from lens.api.routers import admin, ask, health, me, public
from lens.core.logging import configure_logging
from lens.core.settings import get_settings
from lens.core.tracing import configure_tracing
from lens.schemas.common import ErrorBody, ErrorResponse

API_PREFIX = "/api/v1"
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, json=settings.app_env != "dev")
    configure_tracing(settings)

    # Interactive docs and the schema are for development only (pre-deploy checklist, ADR-0042).
    docs = not settings.deployed
    app = FastAPI(
        title="Lens API",
        version=__version__,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_credentials=True,  # the /me session cookie (ADR-0041)
        allow_headers=["accept", "content-type", "authorization", "x-lens-client", "x-request-id"],
    )

    @app.middleware("http")
    async def body_limit(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Refuses oversized bodies before they are read (the admin CSV import gets 5x)."""
        cap = settings.max_body_bytes * (5 if request.url.path.startswith(f"{API_PREFIX}/admin") else 1)
        declared = request.headers.get("content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > cap):
            body = ErrorResponse(error=ErrorBody(code="payload_too_large", message="The request body is too large."))
            return JSONResponse(body.model_dump(exclude_none=True), status_code=413)
        return await call_next(request)

    @app.middleware("http")
    async def reject_control_chars(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """NUL and other control characters in a path or query are never legitimate; Postgres rejects NUL in text,
        which surfaced as a 500 before this check (pre-deploy checklist, input sanitizing)."""
        params = [x for kv in request.query_params.multi_items() for x in kv]  # decoded keys and values
        if _CONTROL.search(request.url.path) or any(_CONTROL.search(x) for x in params):
            body = ErrorResponse(
                error=ErrorBody(code="invalid_request", message="The request contains invalid characters.")
            )
            return JSONResponse(body.model_dump(exclude_none=True), status_code=400)
        return await call_next(request)

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "no-referrer")
        h.setdefault("Cross-Origin-Resource-Policy", "same-site")
        if not request.url.path.endswith(("/docs", "/redoc")):  # the dev docs page needs its scripts
            h.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        if settings.deployed:
            h.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return response

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
        code = {401: "unauthorized", 403: "forbidden", 404: "not_found", 429: "rate_limited", 503: "unavailable"}.get(
            exc.status_code, "http_error"
        )
        body = ErrorResponse(error=ErrorBody(code=code, message=str(exc.detail)))
        return JSONResponse(body.model_dump(exclude_none=True), status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(ask.RateLimited)
    async def rate_limited(request: Request, exc: ask.RateLimited) -> JSONResponse:
        msg = "You're asking faster than Lens can check sources. Please wait and try again."
        body = ErrorResponse(error=ErrorBody(code="rate_limited", message=msg, retry_after_s=exc.retry_after_s))
        return JSONResponse(body.model_dump(), status_code=429, headers={"Retry-After": str(exc.retry_after_s)})

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        """Never a stack trace or internal detail in a response; the log has it (PII-masked, G-OUT-05)."""
        structlog.get_logger().exception("api.unhandled_error", path=request.url.path)
        body = ErrorResponse(error=ErrorBody(code="internal", message="Something went wrong. Please try again."))
        return JSONResponse(body.model_dump(exclude_none=True), status_code=500)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = ", ".join(".".join(str(p) for p in e["loc"][1:]) for e in exc.errors())
        body = ErrorResponse(error=ErrorBody(code="invalid_request", message=f"Check these parameters: {fields}."))
        return JSONResponse(body.model_dump(exclude_none=True), status_code=422)

    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(public.router, prefix=API_PREFIX)
    app.include_router(ask.router, prefix=API_PREFIX)
    app.include_router(me.router, prefix=API_PREFIX)
    app.include_router(admin.router, prefix=API_PREFIX)
    app.include_router(health.router)  # bare /health for container probes
    return app


app = create_app()
