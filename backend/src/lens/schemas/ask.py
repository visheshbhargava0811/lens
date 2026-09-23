"""LLM output schemas for Ask (Graph 2, docs/06). Reasoning fields come before verdicts.

As in story analysis, the model sees masked article refs ("A1", ...) and cites those; code maps refs
back to articles and outlets. Limitations and coverage numbers are written by code, not the model.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from lens.schemas.analysis import CitedSentence

Intent = Literal["story_lookup", "compare_outlets", "fact_check", "background", "unsupported"]


class QueryUnderstanding(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "1.0"
    rationale: str = Field(description="Your notes on the question: language, intent, any loaded premise")
    language: str = Field(description="'en', 'hi', 'hi-Latn' for Hinglish or romanized Hindi, 'mr', ...")
    language_confidence: float = Field(description="0 to 1")
    neutral_query: str = Field(description="The question rewritten neutrally, as a search query in English")
    removed_premises: list[str] = Field(description="Loaded or unverified assumptions taken out of the question")
    intent: Intent
    entities: list[str] = Field(description="People, organisations, places and events named in the question")
    time_hint: str | None = Field(description="Time the question refers to, e.g. 'today', 'last week'; null if none")


class PremiseNote(BaseModel):
    premise: str = Field(description="One removed premise, copied exactly")
    evidence_says: CitedSentence | None = Field(
        description="What the articles report on this premise, cited; null if no article addresses it"
    )


class AskDraft(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "1.0"
    tldr: list[CitedSentence] = Field(min_length=1, description="1 to 2 sentences that answer the question")
    what_happened: list[CitedSentence] = Field(description="Up to 5 sentences of supporting detail")
    agreements: list[CitedSentence] = Field(description="Up to 3 points more than one article reports")
    disagreements: list[CitedSentence] = Field(description="Up to 3 points where articles differ in facts or figures")
    premises: list[PremiseNote] = Field(description="One entry per removed premise, in the given order")
    follow_up_questions: list[str] = Field(description="Up to 3 neutral questions the reader could ask")  # code keeps 3


SECTIONS = ("tldr", "what_happened", "agreements", "disagreements")


def cited_sections(d: AskDraft) -> dict[str, list[CitedSentence]]:
    """Every cited sentence of a draft by section, premise findings included."""
    out = {name: list(getattr(d, name)) for name in SECTIONS}
    out["premises"] = [p.evidence_says for p in d.premises if p.evidence_says is not None]
    return out


class Translation(BaseModel):
    """Localization node output (docs/06 node 13): one translation per input line, same order."""

    SCHEMA_VERSION: ClassVar[str] = "1.0"
    texts: list[str]
