"""Shared API shapes (docs/09 conventions)."""

from typing import Literal

from pydantic import BaseModel

SCHEMA_VERSION = "1"


class ErrorBody(BaseModel):
    code: str
    message: str
    retry_after_s: int | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    env: str
