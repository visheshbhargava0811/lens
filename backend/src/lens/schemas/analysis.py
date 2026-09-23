"""LLM output schemas for story analysis (docs/06, ADR-0022). Reasoning fields come before verdicts.

Articles reach the model as masked refs ("A1", "A2", ...) with no outlet names; code maps refs
back to article ids and re-attaches outlet names. `SCHEMA_VERSION` is stored with every output
and kept out of the JSON schema the model sees.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, Field

ARTICLE_REF = r"^A[0-9]+$"


class Claim(BaseModel):
    article_ref: str = Field(pattern=ARTICLE_REF, description="The article the quote comes from, e.g. A3")
    text: str = Field(description="One atomic, checkable statement, in the article's language")
    source_quote: str = Field(description="Exact span copied from that article's text, character for character")
    attributed_to: str | None = Field(description="Who said it; null if the outlet states it itself")
    checkable: bool


class ClaimList(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "1.0"
    claims: list[Claim]


class CitedSentence(BaseModel):
    text: str
    citations: list[str] = Field(min_length=1, description="Refs of the articles that support this sentence")


class StoryFraming(BaseModel):
    """Contrastive pass over masked articles: how the coverage differs, not who is right."""

    SCHEMA_VERSION: ClassVar[str] = "1.0"
    rationale: str = Field(description="Your comparison notes, written before the findings")
    framing_differences: list[CitedSentence]
    only_in_some_coverage: list[CitedSentence]


class SummaryDraft(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "1.0"
    summary: list[CitedSentence] = Field(min_length=1)
    agreements: list[CitedSentence]
    disagreements: list[CitedSentence]


class FaithfulnessVerdict(BaseModel):
    """Judge output (docs/08): narrow and binary, reasoning first."""

    SCHEMA_VERSION: ClassVar[str] = "1.0"
    reasoning: str
    unsupported_sentences: list[str] = Field(description="Sentences not supported by their cited articles, verbatim")
    verdict: Literal["pass", "fail"]
