"""Online evaluators on a sample of real Asks (docs/08 "Online evals and review loop").

Each pipeline pass takes Ask turns (`ask_turns`, already PII-masked) not yet evaluated, keeps a
deterministic `online_eval.sample_pct` sample, and scores them:
- citation_presence: every shown sentence carries a citation (deterministic)
- premise_handled: a question that presupposes something (G-IN-05 pattern) got a premise note or
  an abstain (deterministic)
- faithfulness: the independent judge re-checks the answer against its cited articles (LLM, at most
  `judge_per_pass` per pass so Ask keeps its free-tier quota)
Results are `guard_events` rows (stage `online_eval`, purged with their turn) and LangSmith feedback
`online.<metric>` on the Ask trace. A metric whose 24 h mean falls below its floor logs
`online_eval.alert` (see `make pipeline-logs`).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Text, cast, func, select
from sqlalchemy.orm import Session

from lens.agents.offline.evidence import ArticleIn, EvidenceArticle, article_text, render
from lens.agents.prompts import system_prompt
from lens.core.config_files import load_yaml
from lens.core.logging import get_logger
from lens.db.models import Article, AskTurn, GuardEvent, Source
from lens.evals.ask_adversarial import PREMISE_NOTES, SENTENCE_SECTIONS
from lens.guardrails.input import _PRESUPPOSES
from lens.schemas.analysis import FaithfulnessVerdict

log = get_logger(__name__)
STAGE = "online_eval"
LLMCall = Any  # lens.llm.client.structured, injectable for tests


def _cfg() -> dict[str, Any]:
    cfg: dict[str, Any] = load_yaml("eval_gates.yaml")["online_eval"]
    return cfg


def _is_uuid(s: str) -> bool:
    try:
        uuid.UUID(s)
    except ValueError:
        return False
    return True


def sampled(turn_id: object, pct: int) -> bool:
    return int(hashlib.sha256(str(turn_id).encode()).hexdigest(), 16) % 100 < pct


def _sentences(answer: dict[str, Any]) -> list[dict[str, Any]]:
    return [s for k in SENTENCE_SECTIONS for s in answer.get(k) or []]


def citation_presence(turn: AskTurn) -> float | None:
    sents = _sentences(turn.answer or {}) if turn.outcome in ("answer", "fallback") else []
    return sum(bool(s.get("citations")) for s in sents) / len(sents) if sents else None


def premise_handled(turn: AskTurn) -> float | None:
    if not _PRESUPPOSES.search(turn.raw_query):
        return None
    if turn.outcome == "abstain":
        return 1.0
    a = turn.answer or {}
    notes = [x for x in a.get("limitations") or [] if x.startswith(PREMISE_NOTES)]
    return 1.0 if a.get("premises_addressed") or notes else 0.0


def faithfulness(session: Session, turn: AskTurn, llm: LLMCall) -> float | None:
    sents = _sentences(turn.answer or {}) if turn.outcome == "answer" else []
    ids = list(dict.fromkeys(c["article_id"] for s in sents for c in s.get("citations") or []))
    ids = [i for i in ids if _is_uuid(i)]  # rows stored before the PII-mask UUID fix can hold masked ids
    if not ids:
        return None
    rows = {
        str(a.id): (a, src)
        for a, src in session.execute(
            select(Article, Source).join(Source, Source.id == Article.source_id).where(Article.id.in_(ids))
        )
    }
    refs = {aid: f"A{i + 1}" for i, aid in enumerate(i for i in ids if i in rows)}
    evidence = [
        EvidenceArticle(
            ref,
            ArticleIn(aid, str(src.id), src.name, a.language, a.published_at, a.title, a.snippet, "unrated"),
            article_text(a.title, a.snippet),
        )
        for aid, ref in refs.items()
        for a, src in [rows[aid]]
    ]
    lines = "\n".join(
        f"- {s['text']} (cites {', '.join(refs[c['article_id']] for c in s['citations'] if c['article_id'] in refs)})"
        for s in sents
    )
    system, version = system_prompt("judge_faithfulness")
    v: FaithfulnessVerdict = llm(
        "ask_judge",
        FaithfulnessVerdict,
        system,
        f"{render(evidence)}\n\nSentences to check:\n{lines}",
        run_name="online.faithfulness",
        prompt_version=version,
    )
    return 1 - len(v.unsupported_sentences) / len(sents)


def run(session: Session, llm: LLMCall, now: datetime | None = None, feedback: Any = None) -> dict[str, Any]:
    cfg, now = _cfg(), now or datetime.now(UTC)
    done = select(GuardEvent.meta["ask_turn_id"].astext).where(GuardEvent.stage == STAGE)
    turns = (
        session.execute(
            select(AskTurn)
            .where(
                AskTurn.created_at >= now - timedelta(hours=cfg["lookback_hours"]),
                cast(AskTurn.id, Text).not_in(done),
            )
            .order_by(AskTurn.created_at)
        )
        .scalars()
        .all()
    )
    judged, scored = 0, 0
    for t in turns:
        scores: dict[str, float | None] = {}
        if sampled(t.id, cfg["sample_pct"]):
            scores = {"citation_presence": citation_presence(t), "premise_handled": premise_handled(t)}
            if judged < cfg["judge_per_pass"]:
                try:
                    scores["faithfulness"] = faithfulness(session, t, llm)
                    judged += scores["faithfulness"] is not None
                except Exception as e:  # quota or provider trouble: skip the judge, keep the rest
                    log.warning("online_eval.judge_skipped", error=f"{type(e).__name__}: {e}"[:300])
        # A marker row even when unsampled or unscored, so the turn is never considered again.
        marks: dict[str, float | None] = {k: v for k, v in scores.items() if v is not None} or {"sampled_out": None}
        for metric, value in marks.items():
            session.add(
                GuardEvent(
                    run_id=t.langsmith_run_id or str(t.id),
                    guard_id=f"online.{metric}",
                    stage=STAGE,
                    passed=value is None or value >= cfg["floors"].get(metric, 0),
                    action="allow",
                    reason=None,
                    score=value,
                    meta={"ask_turn_id": str(t.id)},
                )
            )
            if value is not None and feedback is not None and t.langsmith_run_id:
                feedback(t.langsmith_run_id, key=f"online.{metric}", score=value)
        scored += bool(scores)
    session.flush()
    return {"turns": len(turns), "sampled": scored, "judged": judged, "alerts": alerts(session, now)}


def alerts(session: Session, now: datetime) -> list[dict[str, Any]]:
    cfg, out = _cfg(), []
    for metric, floor in cfg["floors"].items():
        n, mean = session.execute(
            select(func.count(GuardEvent.score), func.avg(GuardEvent.score)).where(
                GuardEvent.stage == STAGE,
                GuardEvent.guard_id == f"online.{metric}",
                GuardEvent.created_at >= now - timedelta(hours=24),
            )
        ).one()
        if n >= cfg["min_samples_for_alert"] and mean < floor:
            out.append({"metric": metric, "mean_24h": round(mean, 3), "floor": floor, "n": n})
            log.error("online_eval.alert", metric=metric, mean_24h=round(mean, 3), floor=floor, n=n)
    return out
