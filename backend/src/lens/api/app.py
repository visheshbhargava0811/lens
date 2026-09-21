"""FastAPI application factory."""

import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from lens import __version__
from lens.api.routers import health
from lens.core.logging import configure_logging
from lens.core.settings import get_settings
from lens.core.tracing import configure_tracing

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

    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(health.router)  # bare /health for container probes
    return app


app = create_app()
