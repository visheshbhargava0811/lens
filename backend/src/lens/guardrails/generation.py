"""Generation and output guards for story analysis (docs/07). Deterministic checks first; the
LLM judge (G-GEN-03) only interprets a verdict that was produced after G-GEN-01/02 passed."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from lens.agents.offline.evidence import EvidenceArticle, quote_span
from lens.guardrails.base import GuardResult, traced_guard
from lens.schemas.analysis import CitedSentence, Claim, FaithfulnessVerdict

QUOTE_FAIL_REVIEW_SHARE = 0.20  # docs/04 section 6: flag the prompt if more than 20% of an article's claims fail


@traced_guard("G-GEN-01", "generation")
def check_citations(sections: Mapping[str, Sequence[CitedSentence]], valid_refs: set[str]) -> GuardResult:
    """Every sentence cites at least one article, and only articles that were in the evidence."""
    bad = [
        f"{name}: {s.text[:80]}"
        for name, sentences in sections.items()
        for s in sentences
        if not s.citations or any(c not in valid_refs for c in s.citations)
    ]
    if bad:
        return GuardResult(
            guard_id="G-GEN-01",
            passed=False,
            action="retry",
            reason=f"{len(bad)} sentences with missing or unknown citations",
            meta={"sentences": bad},
        )
    return GuardResult(guard_id="G-GEN-01", passed=True, action="allow", reason="every sentence cites evidence")


@traced_guard("G-GEN-02", "generation")
def check_quotes(claims: Sequence[Claim], evidence: Mapping[str, EvidenceArticle]) -> GuardResult:
    """Every source_quote appears verbatim in its article. Failing claims are dropped (meta.kept)."""
    kept: list[int] = []
    failed_by_ref: dict[str, int] = {}
    total_by_ref: dict[str, int] = {}
    for i, c in enumerate(claims):
        total_by_ref[c.article_ref] = total_by_ref.get(c.article_ref, 0) + 1
        e = evidence.get(c.article_ref)
        if e is not None and quote_span(c.source_quote, e.text) is not None:
            kept.append(i)
        else:
            failed_by_ref[c.article_ref] = failed_by_ref.get(c.article_ref, 0) + 1
    review = sorted(r for r, n in failed_by_ref.items() if n / total_by_ref[r] > QUOTE_FAIL_REVIEW_SHARE)
    dropped = len(claims) - len(kept)
    return GuardResult(
        guard_id="G-GEN-02",
        passed=dropped == 0,
        action="allow" if dropped == 0 else "redact",
        reason=f"{len(kept)} of {len(claims)} quotes verbatim; {dropped} claims dropped",
        score=len(kept) / len(claims) if claims else 1.0,
        meta={"kept": kept, "prompt_review_refs": review},
    )


@traced_guard("G-GEN-03", "generation")
def check_faithfulness(verdict: FaithfulnessVerdict) -> GuardResult:
    if verdict.verdict == "pass" and not verdict.unsupported_sentences:
        return GuardResult(guard_id="G-GEN-03", passed=True, action="allow", reason="judge: all sentences supported")
    return GuardResult(
        guard_id="G-GEN-03",
        passed=False,
        action="retry",
        reason=f"judge: {len(verdict.unsupported_sentences)} unsupported sentences",
        meta={"unsupported": verdict.unsupported_sentences, "reasoning": verdict.reasoning[:2000]},
    )


def _matches(term: str, text: str) -> bool:
    if term.isascii():
        return re.search(rf"(?<![a-z]){re.escape(term.lower())}(?![a-z])", text) is not None
    return term in text


@traced_guard("G-OUT-07", "output")
def check_sensitive(texts: Sequence[str], keywords: Mapping[str, Sequence[str]]) -> GuardResult:
    """Sensitive-topic routing: matching stories are reviewed by a person before publishing."""
    blob = "\n".join(texts).lower()
    topics = {t: sorted({k for k in terms if _matches(k, blob)}) for t, terms in keywords.items()}
    hits = {t: ks for t, ks in topics.items() if ks}
    if hits:
        return GuardResult(
            guard_id="G-OUT-07",
            passed=False,
            action="route_to_review",
            reason="sensitive topics: " + ", ".join(sorted(hits)),
            meta={"topics": hits},
        )
    return GuardResult(guard_id="G-OUT-07", passed=True, action="allow", reason="no sensitive topic matched")
