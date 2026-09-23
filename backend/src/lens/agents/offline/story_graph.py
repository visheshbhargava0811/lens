"""Story analysis graph (Graph 1, nodes 6-10 without stance; ADR-0022).

claims (G-GEN-02) -> framing (G-GEN-01) -> summarize (G-GEN-01) -> judge (G-GEN-03)
  -> [retry summarize with the unsupported sentences, max MAX_VERIFIER_RETRIES]
  -> [fallback: prune the sentences the judge flagged; fail if no summary sentence survives]
  -> sensitive (G-OUT-07)

Nodes are pure functions of state plus the injected `llm` (lens.llm.client.structured in
production, a fake in tests). Claims and framing are best-effort: if they fail, the summary
still runs. The summary is published only when G-GEN-01 and G-GEN-03 pass; G-OUT-07 holds it
for review instead of publishing.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from lens.agents.offline.evidence import EvidenceArticle, render
from lens.agents.prompts import system_prompt
from lens.guardrails.base import GuardResult
from lens.guardrails.generation import check_citations, check_faithfulness, check_quotes, check_sensitive
from lens.llm.client import LLMError
from lens.schemas.analysis import CitedSentence, Claim, ClaimList, FaithfulnessVerdict, StoryFraming, SummaryDraft

MAX_VERIFIER_RETRIES = 2  # docs/06: bounded loops only
RETRY_NOTE = "A checker found these sentences unsupported by their cited articles; rewrite or drop them:"


class LLM(Protocol):
    def __call__(
        self,
        tier_name: str,
        model: type[Any],
        system: str,
        user: str,
        *,
        run_name: str,
        prompt_version: str,
        tags: list[str] | None = None,
        exclude_families: set[str] | None = None,
        meta: dict[str, str] | None = None,
    ) -> Any: ...


class StoryState(TypedDict, total=False):
    story_id: str
    headline: str
    evidence: list[EvidenceArticle]
    sensitive_keywords: dict[str, list[str]]
    claims: list[Claim]
    framing: StoryFraming | None
    summary: SummaryDraft | None
    verdict: FaithfulnessVerdict | None
    attempts: int
    feedback: str | None
    guards: list[GuardResult]
    prompt_versions: dict[str, str]
    models: dict[str, dict[str, str]]  # task -> provider/model/family actually used (audit, G-OPS-04)
    errors: list[str]
    outcome: Literal["published", "review", "failed"]
    pruned: list[CitedSentence]


def _user(state: StoryState, extra: str = "") -> str:
    return f"Story headline (for context only): {state['headline']}\n\n{render(state['evidence'])}{extra}"


def _sentences(summary: SummaryDraft) -> str:
    rows = [
        f"- [{name}] {s.text} (cites {', '.join(s.citations)})"
        for name, section in (
            ("summary", summary.summary),
            ("agreement", summary.agreements),
            ("disagreement", summary.disagreements),
        )
        for s in section
    ]
    return "\n".join(rows)


def build(llm: LLM) -> Any:
    def call(
        state: StoryState, task: str, tier: str, model: type[BaseModel], user: str, exclude: set[str] | None = None
    ) -> tuple[Any, dict[str, Any]]:
        """Returns the output and the state update recording prompt version and model used.
        (LangGraph merges only what a node returns, so nodes must return this update.)"""
        system, version = system_prompt(task)
        meta: dict[str, str] = {}
        out = llm(
            tier,
            model,
            system,
            user,
            run_name=f"story.{task}",
            prompt_version=version,
            tags=[f"story:{state['story_id']}"],
            exclude_families=exclude,
            meta=meta,
        )
        return out, {
            "prompt_versions": {**state.get("prompt_versions", {}), task: version},
            "models": {**state.get("models", {}), task: meta},
        }

    def claims(state: StoryState) -> dict[str, Any]:
        try:
            out, rec = call(state, "claims_extraction", "analysis", ClaimList, _user(state))
        except LLMError as e:
            return {"claims": [], "errors": [*state.get("errors", []), f"claims: {e}"]}
        res = check_quotes(out.claims, {e.ref: e for e in state["evidence"]})
        kept = [out.claims[i] for i in res.meta["kept"]]
        return {"claims": kept, "guards": [*state.get("guards", []), res], **rec}

    def framing(state: StoryState) -> dict[str, Any]:
        try:
            out, rec = call(state, "framing_contrast", "analysis", StoryFraming, _user(state))
        except LLMError as e:
            return {"framing": None, "errors": [*state.get("errors", []), f"framing: {e}"]}
        refs = {e.ref for e in state["evidence"]}
        res = check_citations(
            {"framing_differences": out.framing_differences, "only_in_some": out.only_in_some_coverage}, refs
        )
        return {
            "framing": out if res.passed else None,
            "guards": [*state.get("guards", []), res],
            **rec,
        }

    def summarize(state: StoryState) -> dict[str, Any]:
        attempts = state.get("attempts", 0) + 1
        fix = f"\n\n{RETRY_NOTE}\n{state['feedback']}" if state.get("feedback") else ""
        try:
            out, rec = call(state, "synthesis_system", "synthesis", SummaryDraft, _user(state, fix))
        except LLMError as e:
            return {"summary": None, "attempts": attempts, "errors": [*state.get("errors", []), f"summary: {e}"]}
        res = check_citations(
            {"summary": out.summary, "agreements": out.agreements, "disagreements": out.disagreements},
            {e.ref for e in state["evidence"]},
        )
        return {
            "summary": out if res.passed else None,
            "attempts": attempts,
            "feedback": None if res.passed else "\n".join(res.meta["sentences"]),
            "guards": [*state.get("guards", []), res],
            **rec,
        }

    def judge(state: StoryState) -> dict[str, Any]:
        summary = state["summary"]
        assert summary is not None
        user = _user(state, f"\n\nSentences to check:\n{_sentences(summary)}")
        try:
            # The judge must not share a family with the model that wrote this summary (docs/08).
            writer = state.get("models", {}).get("synthesis_system", {}).get("family")
            verdict, rec = call(
                state, "judge_faithfulness", "judge", FaithfulnessVerdict, user, exclude={writer} if writer else None
            )
        except LLMError as e:
            # No verdict means no publication: the summary is never shown unverified.
            return {
                "verdict": None,
                "attempts": MAX_VERIFIER_RETRIES + 1,
                "errors": [*state.get("errors", []), f"judge: {e}"],
            }
        res = check_faithfulness(verdict)
        return {
            "verdict": verdict,
            "feedback": None if res.passed else "\n".join(verdict.unsupported_sentences),
            "guards": [*state.get("guards", []), res],
            **rec,
        }

    def prune(state: StoryState) -> dict[str, Any]:
        """G-GEN-03 fallback (docs/07): keep only sentences the judge did not flag. Every kept
        sentence was checked and judged supported; nothing unverified is added."""
        summary, verdict = state["summary"], state["verdict"]
        assert summary is not None and verdict is not None
        flagged = verdict.unsupported_sentences

        def keep(section: list[CitedSentence]) -> list[CitedSentence]:
            return [x for x in section if not any(x.text.strip() in f for f in flagged)]

        main, agree, disagree = keep(summary.summary), keep(summary.agreements), keep(summary.disagreements)
        kept_ids = {id(x) for x in (*main, *agree, *disagree)}
        removed = [x for x in (*summary.summary, *summary.agreements, *summary.disagreements) if id(x) not in kept_ids]
        if not main:
            return {"summary": None, "pruned": removed}
        return {"summary": SummaryDraft(summary=main, agreements=agree, disagreements=disagree), "pruned": removed}

    def after_prune(state: StoryState) -> str:
        return "sensitive" if state.get("summary") is not None else "failed"

    def sensitive(state: StoryState) -> dict[str, Any]:
        texts = [state["headline"], *(e.text for e in state["evidence"])]
        res = check_sensitive(texts, state["sensitive_keywords"])
        return {"outcome": "published" if res.passed else "review", "guards": [*state.get("guards", []), res]}

    def failed(state: StoryState) -> dict[str, Any]:
        return {"outcome": "failed"}

    def after_summarize(state: StoryState) -> str:
        if state.get("summary") is not None:
            return "judge"
        return "summarize" if state.get("attempts", 0) <= MAX_VERIFIER_RETRIES else "failed"

    def after_judge(state: StoryState) -> str:
        v = state.get("verdict")
        if v is not None and v.verdict == "pass" and not v.unsupported_sentences:
            return "sensitive"
        if v is None:
            return "failed"  # no verdict (judge unavailable): never publish unverified
        return "summarize" if state.get("attempts", 0) <= MAX_VERIFIER_RETRIES else "prune"

    g = StateGraph(StoryState)
    for name, fn in (
        ("claims", claims),
        ("framing", framing),
        ("summarize", summarize),
        ("judge", judge),
        ("prune", prune),
        ("sensitive", sensitive),
        ("failed", failed),
    ):
        g.add_node(name, fn)
    g.add_edge(START, "claims")
    g.add_edge("claims", "framing")
    g.add_edge("framing", "summarize")
    g.add_conditional_edges("summarize", after_summarize, ["judge", "summarize", "failed"])
    g.add_conditional_edges("judge", after_judge, ["sensitive", "summarize", "prune", "failed"])
    g.add_conditional_edges("prune", after_prune, ["sensitive", "failed"])
    g.add_edge("sensitive", END)
    g.add_edge("failed", END)
    return g.compile(name="story_analysis")
