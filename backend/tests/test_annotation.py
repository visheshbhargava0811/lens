"""docs/08 review loop: failed guard runs reach the annotation queue once each."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from lens.ops import annotation

T0 = datetime(2026, 9, 27, tzinfo=UTC)


class Fake:
    def __init__(self, failed: list[str], queued: list[str]) -> None:
        self.failed, self.queued = failed, queued
        self.added: list[Any] = []
        self.selects: list[str] | None = None
        self.runs = self

    async def _iter(self) -> Any:
        for i in self.failed:
            yield SimpleNamespace(id=i, start_time=T0)

    def query(self, **kw: Any) -> Any:
        self.selects = kw["selects"]
        assert kw["filter"] == annotation.FAILED_GUARDS
        return self._iter()

    def read_project(self, project_name: str) -> Any:
        return SimpleNamespace(id="p1")

    def list_annotation_queues(self, name: str) -> list[Any]:
        return [SimpleNamespace(id="q1")]

    def list_runs_from_annotation_queue(self, qid: str) -> list[Any]:
        return [SimpleNamespace(id=i) for i in self.queued]

    def add_runs_to_annotation_queue(self, qid: str, runs: list[Any]) -> None:
        self.added += runs


def test_sweep_queues_only_new_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(annotation, "load_yaml", lambda name: {"annotation": {"sweep_hours": 48}})
    fake = Fake(failed=["r1", "r2", "r3"], queued=["r2"])
    assert annotation.sweep(fake, T0) == {"failed_guard_runs": 3, "queued": 2}  # type: ignore[arg-type]
    assert [k["run_id"] for k in fake.added] == ["r1", "r3"] and all(k["start_time"] == T0 for k in fake.added)
    assert fake.selects is not None and "START_TIME" in fake.selects  # the API returns only ids otherwise
