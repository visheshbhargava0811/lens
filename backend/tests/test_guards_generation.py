"""Failing-case and passing-case tests for G-GEN-01, G-GEN-02, G-GEN-03, G-OUT-07 (docs/07)."""

from datetime import UTC, datetime

from lens.agents.offline.evidence import ArticleIn, EvidenceArticle
from lens.core.config_files import load_yaml
from lens.guardrails.generation import check_citations, check_faithfulness, check_quotes, check_sensitive
from lens.schemas.analysis import CitedSentence, Claim, FaithfulnessVerdict

KEYWORDS = load_yaml("guardrails.yaml")["sensitive_keywords"]


def _ev(ref: str, text: str) -> EvidenceArticle:
    a = ArticleIn(ref, ref, ref, "hi", datetime(2026, 9, 23, tzinfo=UTC), text, None, "unrated")
    return EvidenceArticle(ref=ref, article=a, text=text)


def _claim(ref: str, quote: str) -> Claim:
    return Claim(article_ref=ref, text="t", source_quote=quote, attributed_to=None, checkable=True)


def test_g_gen_01_passes_valid_and_fails_unknown_refs() -> None:
    ok = {"summary": [CitedSentence(text="x", citations=["A1"])]}
    assert check_citations(ok, {"A1"}).passed
    bad = {"summary": [CitedSentence(text="x", citations=["A9"])]}
    res = check_citations(bad, {"A1"})
    assert not res.passed and res.action == "retry"


def test_g_gen_02_drops_non_verbatim_quotes_and_flags_prompt_review() -> None:
    ev = {"A1": _ev("A1", "राज्य सरकार ने नई मेट्रो लाइन के लिए बजट मंज़ूर किया")}
    claims = [_claim("A1", "नई मेट्रो लाइन"), _claim("A1", "new metro line"), _claim("A2", "anything")]
    res = check_quotes(claims, ev)
    assert not res.passed and res.meta["kept"] == [0]
    assert res.meta["prompt_review_refs"] == ["A1", "A2"]  # A1: 1 of 2 failed (> 20%)
    assert check_quotes([claims[0]], ev).passed


def test_g_gen_03_follows_the_judge_and_never_passes_with_unsupported_sentences() -> None:
    assert check_faithfulness(FaithfulnessVerdict(reasoning="r", unsupported_sentences=[], verdict="pass")).passed
    inconsistent = FaithfulnessVerdict(reasoning="r", unsupported_sentences=["x"], verdict="pass")
    assert not check_faithfulness(inconsistent).passed
    assert (
        check_faithfulness(FaithfulnessVerdict(reasoning="r", unsupported_sentences=["x"], verdict="fail")).action
        == "retry"
    )


def test_g_out_07_routes_sensitive_stories_in_any_language() -> None:
    res = check_sensitive(["Sri Lanka court convicts 14 over Easter Sunday bombings"], KEYWORDS)
    assert res.action == "route_to_review" and "terror_incident" in res.meta["topics"]
    assert check_sensitive(["नाबालिग से दुष्कर्म का आरोपी गिरफ्तार"], KEYWORDS).meta["topics"].keys() >= {
        "minor_involved",
        "sexual_offence_case",
    }


def test_g_out_07_matches_whole_words_only() -> None:
    assert check_sensitive(["Metro line budget approved", "Territorial army recruitment"], KEYWORDS).passed
