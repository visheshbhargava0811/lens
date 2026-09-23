"""GuardResult and traced_guard (docs/07). Every guard returns a GuardResult and is a named
LangSmith run with the verdict as metadata and feedback. Guards are pure; callers persist the
result to `guard_events` (see lens.agents.offline.story_graph.store)."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, Literal, ParamSpec, cast

from langsmith import Client, traceable
from langsmith.run_helpers import get_current_run_tree
from pydantic import BaseModel, Field

from lens.core.settings import get_settings

P = ParamSpec("P")
Action = Literal["allow", "block", "redact", "retry", "route_to_review", "abstain"]


class GuardResult(BaseModel):
    guard_id: str
    passed: bool
    action: Action
    reason: str
    score: float | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    run_id: str | None = None  # LangSmith run of the guard, when tracing is on


def traced_guard(guard_id: str, stage: str) -> Callable[[Callable[P, GuardResult]], Callable[P, GuardResult]]:
    def deco(fn: Callable[P, GuardResult]) -> Callable[P, GuardResult]:
        @traceable(name=f"guard:{guard_id}", run_type="chain", tags=["guardrail", guard_id, stage])
        @wraps(fn)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> GuardResult:
            res = fn(*args, **kwargs)
            rt = get_current_run_tree()
            if rt is not None:
                rt.add_metadata({"guard": guard_id, "passed": res.passed, "action": res.action, "reason": res.reason})
                res.run_id = str(rt.id)
                if get_settings().langsmith_tracing:
                    Client().create_feedback(
                        rt.id, key=f"guard.{guard_id}", score=1.0 if res.passed else 0.0, comment=res.reason
                    )
            return res

        return cast(Callable[P, GuardResult], wrapped)  # traceable adds an optional langsmith_extra kwarg

    return deco
