"""Postgres advisory locks shared by processes that write the same rows."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import text

from lens.db.session import get_engine

PIPELINE_LOCK = 7_310_001  # index + cluster: the pipeline worker and Ask's freshness node


@contextmanager
def pipeline_lock(wait: bool = True) -> Iterator[bool]:
    """Holds the pipeline lock on its own connection for the block. With wait=False, yields False at
    once when another process holds it (the caller skips its work)."""
    with get_engine().connect() as conn:
        fn = "pg_advisory_lock" if wait else "pg_try_advisory_lock"
        got = conn.execute(text(f"SELECT {fn}(:k)"), {"k": PIPELINE_LOCK}).scalar()
        got = True if got is None else bool(got)  # pg_advisory_lock returns void (None)
        try:
            yield got
        finally:
            if got:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": PIPELINE_LOCK})
