"""Story analysis graph with a scripted fake LLM: guards, bounded retries, routing, and failures."""

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from lens.agents.offline.evidence import ArticleIn, select_evidence
from lens.agents.offline.story_graph import MAX_VERIFIER_RETRIES, StoryState, build
from lens.llm.client import LLMError
from lens.schemas.analysis import CitedSentence, Claim, ClaimList, FaithfulnessVerdict, StoryFraming, SummaryDraft

T0 = datetime(2026, 9, 23, tzinfo=UTC)
KEYWORDS = {"terror_incident": ["bombing"]}


def _state(headline: str = "Metro line budget approved") -> StoryState:
    arts = [
        ArticleIn(
            "a1", "s1", "Outlet One", "en", T0, "State approves metro budget", "Funds cleared for phase one.", "left"
        ),
        ArticleIn("a2", "s2", "Outlet Two", "hi", T0, "राज्य सरकार ने मेट्रो बजट मंज़ूर किया", None, "right"),
    ]
    return {
        "story_id": "st1",
        "headline": headline,
        "evidence": select_evidence(arts, 12),
        "sensitive_keywords": KEYWORDS,
    }


def _cs(text: str, *refs: str) -> CitedSentence:
    return CitedSentence(text=text, citations=list(refs))


GOOD_CLAIMS = ClaimList(
    claims=[
        Claim(
            article_ref="A1",
            text="Budget approved",
            source_quote="State approves metro budget",
            attributed_to=None,
            checkable=True,
        ),
        Claim(article_ref="A2", text="x", source_quote="made up quote", attributed_to=None, checkable=True),
    ]
)
FRAMING = StoryFraming(
    rationale="r", framing_differences=[_cs("A1 mentions phase one.", "A1")], only_in_some_coverage=[]
)
SUMMARY = SummaryDraft(summary=[_cs("The state approved a metro budget.", "A1", "A2")], agreements=[], disagreements=[])
PASS = FaithfulnessVerdict(reasoning="ok", unsupported_sentences=[], verdict="pass")
FAIL = FaithfulnessVerdict(reasoning="no", unsupported_sentences=["The state approved a metro budget."], verdict="fail")


class FakeLLM:
    """Returns scripted outputs per schema, in order; records every user prompt per schema."""

    def __init__(self, script: dict[type, list[Any]]) -> None:
        self.script = {k: list(v) for k, v in script.items()}
        self.prompts: dict[type, list[str]] = defaultdict(list)
        self.kwargs: dict[type, list[dict[str, Any]]] = defaultdict(list)
        self.families: dict[str, str] = {}

    def __call__(self, tier_name: str, model: type[Any], system: str, user: str, **kw: Any) -> Any:
        self.prompts[model].append(user)
        self.kwargs[model].append(kw)
        if kw.get("meta") is not None:
            kw["meta"].update(
                provider="fake", model=f"{tier_name}-model", family=self.families.get(tier_name, tier_name)
            )
        out = self.script[model].pop(0) if len(self.script[model]) > 1 else self.script[model][0]
        if isinstance(out, Exception):
            raise out
        return out


def _run(script: dict[type, list[Any]], state: StoryState | None = None) -> tuple[StoryState, FakeLLM]:
    llm = FakeLLM(script)
    return build(llm).invoke(state or _state()), llm


def test_happy_path_publishes_and_drops_unverifiable_quotes() -> None:
    out, _ = _run(
        {ClaimList: [GOOD_CLAIMS], StoryFraming: [FRAMING], SummaryDraft: [SUMMARY], FaithfulnessVerdict: [PASS]}
    )
    assert out["outcome"] == "published"
    assert [c.source_quote for c in out["claims"]] == ["State approves metro budget"]  # G-GEN-02 dropped the other
    assert {g.guard_id for g in out["guards"]} == {"G-GEN-01", "G-GEN-02", "G-GEN-03", "G-OUT-07"}
    assert set(out["prompt_versions"]) == {
        "claims_extraction",
        "framing_contrast",
        "synthesis_system",
        "judge_faithfulness",
    }


def test_judge_failure_retries_summary_with_the_unsupported_sentences() -> None:
    out, llm = _run(
        {ClaimList: [GOOD_CLAIMS], StoryFraming: [FRAMING], SummaryDraft: [SUMMARY], FaithfulnessVerdict: [FAIL, PASS]}
    )
    assert out["outcome"] == "published" and out["attempts"] == 2
    assert "The state approved a metro budget." in llm.prompts[SummaryDraft][1]


def test_retries_are_bounded_then_fail_closed_when_nothing_survives() -> None:
    out, llm = _run(
        {ClaimList: [GOOD_CLAIMS], StoryFraming: [FRAMING], SummaryDraft: [SUMMARY], FaithfulnessVerdict: [FAIL]}
    )
    assert out["outcome"] == "failed"  # the only summary sentence was flagged every time
    assert len(llm.prompts[SummaryDraft]) == MAX_VERIFIER_RETRIES + 1


def test_fallback_prunes_only_the_flagged_sentences() -> None:
    two = SummaryDraft(
        summary=[_cs("The state approved a metro budget.", "A1"), _cs("Funds were cleared for phase one.", "A1")],
        agreements=[_cs("Both report the approval.", "A1", "A2")],
        disagreements=[],
    )
    # The judge echoes flagged sentences with prefixes; matching is by the sentence text.
    flag = FaithfulnessVerdict(
        reasoning="r", unsupported_sentences=["[summary] Funds were cleared for phase one. (cites A1)"], verdict="fail"
    )
    out, _ = _run({ClaimList: [GOOD_CLAIMS], StoryFraming: [FRAMING], SummaryDraft: [two], FaithfulnessVerdict: [flag]})
    assert out["outcome"] == "published"
    summary = out["summary"]
    assert summary is not None
    assert [x.text for x in summary.summary] == ["The state approved a metro budget."]
    assert [x.text for x in summary.agreements] == ["Both report the approval."]
    assert [x.text for x in out["pruned"]] == ["Funds were cleared for phase one."]


def test_summary_citing_unknown_articles_never_reaches_the_judge() -> None:
    bad = SummaryDraft(summary=[_cs("Invented.", "A9")], agreements=[], disagreements=[])
    out, llm = _run(
        {ClaimList: [GOOD_CLAIMS], StoryFraming: [FRAMING], SummaryDraft: [bad], FaithfulnessVerdict: [PASS]}
    )
    assert out["outcome"] == "failed" and FaithfulnessVerdict not in llm.prompts


def test_sensitive_story_is_held_for_review() -> None:
    out, _ = _run(
        {ClaimList: [GOOD_CLAIMS], StoryFraming: [FRAMING], SummaryDraft: [SUMMARY], FaithfulnessVerdict: [PASS]},
        _state("Court convicts 14 over bombing"),
    )
    assert out["outcome"] == "review"


def test_claims_and_framing_errors_do_not_block_the_summary() -> None:
    out, _ = _run(
        {
            ClaimList: [LLMError("down")],
            StoryFraming: [LLMError("down")],
            SummaryDraft: [SUMMARY],
            FaithfulnessVerdict: [PASS],
        }
    )
    assert out["outcome"] == "published" and out["claims"] == [] and out["framing"] is None
    assert len(out["errors"]) == 2


def test_judge_error_never_publishes_unverified() -> None:
    out, _ = _run(
        {
            ClaimList: [GOOD_CLAIMS],
            StoryFraming: [FRAMING],
            SummaryDraft: [SUMMARY],
            FaithfulnessVerdict: [LLMError("down")],
        }
    )
    assert out["outcome"] == "failed"


def test_prompts_never_contain_outlet_names() -> None:
    _, llm = _run(
        {ClaimList: [GOOD_CLAIMS], StoryFraming: [FRAMING], SummaryDraft: [SUMMARY], FaithfulnessVerdict: [PASS]}
    )
    for prompts in llm.prompts.values():
        assert all("Outlet One" not in p and "Outlet Two" not in p for p in prompts)


def test_judge_excludes_the_family_that_wrote_the_summary_and_models_are_recorded() -> None:
    llm = FakeLLM(
        {ClaimList: [GOOD_CLAIMS], StoryFraming: [FRAMING], SummaryDraft: [SUMMARY], FaithfulnessVerdict: [PASS]}
    )
    llm.families = {"synthesis": "gemini"}  # e.g. Groq was down and Gemini wrote the summary
    out = build(llm).invoke(_state())
    assert llm.kwargs[FaithfulnessVerdict][0]["exclude_families"] == {"gemini"}
    assert out["models"]["synthesis_system"]["family"] == "gemini"
    assert set(out["models"]) == {"claims_extraction", "framing_contrast", "synthesis_system", "judge_faithfulness"}
