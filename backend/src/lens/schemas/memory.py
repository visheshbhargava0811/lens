"""Semantic memory schema (docs/06, docs/11). The key enum is closed: nothing outside it is storable, and no
key can hold a political leaning, a stance preference, or reading behaviour (docs/11 hard rules 2 and 3)."""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, Field


class UserFactKey(StrEnum):
    output_language = "output_language"
    ui_language = "ui_language"
    followed_topics = "followed_topics"
    followed_regions = "followed_regions"
    summary_length = "summary_length"
    audio_preference = "audio_preference"


class UserFact(BaseModel):
    key: UserFactKey  # fixed enum: nothing outside this list is storable
    value: str | list[str]


class ConsolidatedFacts(BaseModel):
    """Consolidation job output (docs/11): explicit preference statements only, never a profile."""

    SCHEMA_VERSION: ClassVar[str] = "1.0"
    reasoning: str = Field(description="Which questions state a preference explicitly, and which do not")
    facts: list[UserFact] = Field(description="Only preferences the reader stated explicitly; empty if none")
