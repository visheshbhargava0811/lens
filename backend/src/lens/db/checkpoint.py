"""LangGraph Postgres checkpointer for the Ask graph (docs/06: "Use the LangGraph Postgres
checkpointer for the online graph"). One thread per Ask turn: thread_id == ask_turns.id.

Verified against langgraph-checkpoint-postgres 3.1.2 / langgraph-checkpoint 4.2.0: connections must be
autocommit with dict rows; `setup()` creates the checkpoint tables (outside Alembic, owned by the
library). Deserialization is restricted to the built-in safe types plus the Ask state types, instead
of the library's permissive default.
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from lens.agents.offline.evidence import ArticleIn, EvidenceArticle
from lens.agents.online.ask_graph import Evidence
from lens.core.settings import get_settings
from lens.guardrails.base import GuardResult
from lens.schemas.analysis import CitedSentence, FaithfulnessVerdict
from lens.schemas.ask import AskDraft, PremiseNote, QueryUnderstanding, Translation

STATE_TYPES: list[type] = [
    QueryUnderstanding,
    AskDraft,
    PremiseNote,
    CitedSentence,
    FaithfulnessVerdict,
    Translation,
    GuardResult,
    Evidence,
    EvidenceArticle,
    ArticleIn,
]


def serializer() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=None).with_msgpack_allowlist(STATE_TYPES)


def conninfo(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def make_saver(database_url: str, max_size: int = 4) -> PostgresSaver:
    pool: ConnectionPool = ConnectionPool(
        conninfo(database_url),
        min_size=1,
        max_size=max_size,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=True,
    )
    saver = PostgresSaver(pool, serde=serializer())  # type: ignore[arg-type]
    saver.setup()
    return saver


@lru_cache
def ask_checkpointer() -> PostgresSaver:
    return make_saver(get_settings().database_url)
