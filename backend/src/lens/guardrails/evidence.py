"""Evidence guards for Ask (docs/07), run after retrieval and before any model sees the evidence.

G-EV-01 indirect injection: `clean()` already strips HTML, zero-width and control characters and
neutralizes angle brackets. This guard also redacts instruction-like sentences aimed at an AI, and
logs the source for review. Deterministic patterns; a classifier can be added behind them.
G-EV-03 minimum evidence: fewer distinct outlets than `min_sources_for_bar` means limited coverage
(the answer says so and shows no bar; zero evidence abstains upstream).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

from lens.agents.offline.evidence import EvidenceArticle
from lens.guardrails.base import GuardResult, traced_guard

REDACTED = "[removed: instruction-like text]"
# Phrases addressed to a model rather than a reader. English and Hindi; case-insensitive. Kept narrow on
# purpose: news text says "new instructions" or "AI:" legitimately, so those are not patterns.
_INJECTION = re.compile(
    r"(ignore|disregard|forget)\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above|earlier)\s+(instructions|rules|prompts?)"
    r"|\byou\s+are\s+(now\s+)?(an?\s+)?(ai|assistant|language\s+model|chatgpt|claude|llm)\b"
    r"|\b(system|developer)\s+(prompt|message|instructions)\b"
    r"|\byou\s+are\s+now\s+dan\b|\bdo\s+anything\s+now\b"
    r"|\[\s*/?\s*(assistant|system|user|inst)\s*\]|<\|?\s*(im_start|im_end|system|assistant)\s*\|?>"  # chat role tags
    r"|पिछले\s+(सभी\s+)?निर्देश(ों)?\s+(को\s+)?(अनदेखा|नज़रअंदाज़|नजरअंदाज)"
    r"|सिस्टम\s+प्रॉम्प्ट",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"(?<=[.!?।])\s+|\n")


def _scrub(text: str) -> tuple[str, int]:
    parts = _SENTENCE.split(text)
    hits = sum(bool(_INJECTION.search(p)) for p in parts)
    if not hits:
        return text, 0
    return " ".join(REDACTED if _INJECTION.search(p) else p for p in parts), hits


@traced_guard("G-EV-01", "evidence")
def check_injection(articles: Sequence[EvidenceArticle]) -> GuardResult:
    """Reports instruction-like text per article; `redact_injection` applies the redaction."""
    flagged = {a.ref: a.article.source_id for a in articles if _INJECTION.search(a.text)}
    if flagged:
        return GuardResult(
            guard_id="G-EV-01",
            passed=False,
            action="redact",
            reason=f"instruction-like text in {len(flagged)} article(s), redacted",
            meta={"refs": sorted(flagged), "source_ids": sorted(set(flagged.values()))},
        )
    return GuardResult(guard_id="G-EV-01", passed=True, action="allow", reason="no instruction-like text")


def redact_injection(articles: Sequence[EvidenceArticle]) -> list[EvidenceArticle]:
    return [replace(a, text=_scrub(a.text)[0]) for a in articles]


@traced_guard("G-EV-03", "evidence")
def check_min_evidence(articles: Sequence[EvidenceArticle], min_sources: int) -> GuardResult:
    n = len({a.article.source_id for a in articles})
    if n == 0:
        return GuardResult(guard_id="G-EV-03", passed=False, action="abstain", reason="no evidence")
    if n < min_sources:
        return GuardResult(
            guard_id="G-EV-03",
            passed=False,
            action="allow",
            reason=f"limited coverage: {n} outlet(s), below {min_sources}",
            meta={"limited": True, "sources": n},
        )
    return GuardResult(guard_id="G-EV-03", passed=True, action="allow", reason=f"{n} outlets", meta={"sources": n})


@traced_guard("G-EV-04", "evidence")
def check_freshness(articles: Sequence[EvidenceArticle], now: datetime, stale_hours: float) -> GuardResult:
    """Tags how recent the evidence is. Stale evidence triggers freshness once and a limitation note."""
    if not articles:
        return GuardResult(guard_id="G-EV-04", passed=False, action="allow", reason="no evidence", meta={"stale": True})
    newest = max(a.article.published_at for a in articles)
    hours = max((now - newest).total_seconds() / 3600, 0.0)
    stale = hours > stale_hours
    return GuardResult(
        guard_id="G-EV-04",
        passed=not stale,
        action="allow",
        reason=f"newest article {hours:.1f} h old",
        score=hours,
        meta={"stale": stale, "newest_hours": round(hours, 1), "newest_at": newest.isoformat()},
    )
