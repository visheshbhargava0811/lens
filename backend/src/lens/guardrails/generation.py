"""Generation and output guards for story analysis (docs/07). Deterministic checks first; the
LLM judge (G-GEN-03) only interprets a verdict that was produced after G-GEN-01/02 passed."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from itertools import pairwise

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


_UNIVERSAL = re.compile(r"\b(all|each|every)\b[^.]{0,40}\b(articles?|sources?|reports?|outlets?|coverage)\b", re.I)
_MOST = re.compile(r"\bmost\b[^.]{0,40}\b(articles?|sources?|reports?|outlets?|coverage)\b", re.I)
_SOME = re.compile(r"\b(multiple|several)\b[^.]{0,40}\b(articles?|sources?|reports?|outlets?)\b", re.I)


def scope_violation(sentence: CitedSentence, n_evidence: int) -> str | None:
    """Why a sentence's scope claim contradicts its own citations, or None. Wrong by construction:
    "all articles" citing 3 of 12 cannot be true of the evidence, whatever the articles say."""
    cited = len(set(sentence.citations))
    if _UNIVERSAL.search(sentence.text) and cited < n_evidence:
        return f"says all/each/every but cites {cited} of {n_evidence} articles"
    if _MOST.search(sentence.text) and cited * 2 <= n_evidence:
        return f"says most but cites {cited} of {n_evidence} articles"
    if _SOME.search(sentence.text) and cited < 2:
        return f"says multiple/several but cites {cited} article"
    return None


@traced_guard("G-GEN-08", "generation")
def check_scope(sections: Mapping[str, Sequence[CitedSentence]], n_evidence: int) -> GuardResult:
    """Deterministic, before the judge: scope words must match the citations, and each agreement
    must cite at least two articles (meta.drop = sentence texts)."""
    bad = {s.text: why for sec in sections.values() for s in sec if (why := scope_violation(s, n_evidence))}
    # An agreement needs at least two articles: one article cannot agree with itself.
    bad |= {
        s.text: "an agreement citing one article" for s in sections.get("agreements", []) if len(set(s.citations)) < 2
    }
    if bad:
        return GuardResult(
            guard_id="G-GEN-08",
            passed=False,
            action="redact",
            reason=f"{len(bad)} sentences claim more coverage than they cite",
            meta={"drop": list(bad), "why": bad},
        )
    return GuardResult(guard_id="G-GEN-08", passed=True, action="allow", reason="scope claims match citations")


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


@traced_guard("G-IN-05", "generation")
def check_premises(removed: Sequence[str], addressed: Sequence[str]) -> GuardResult:
    """Every premise removed from the question comes back in the answer (docs/06): either with what
    the evidence says about it, or as "no article reports that". Silently dropping one fails."""
    got = {p.strip().casefold() for p in addressed}
    missing = [p for p in removed if p.strip().casefold() not in got]
    if missing:
        return GuardResult(
            guard_id="G-IN-05",
            passed=False,
            action="retry",
            reason=f"{len(missing)} of {len(removed)} removed premises not addressed",
            meta={"missing": missing},
        )
    return GuardResult(guard_id="G-IN-05", passed=True, action="allow", reason=f"{len(removed)} premises addressed")


@traced_guard("G-OUT-03", "generation")
def check_attribution(
    sections: Mapping[str, Sequence[CitedSentence]], terms: Sequence[str], markers: Sequence[str]
) -> GuardResult:
    """Defamation caution (docs/07): an allegation must be attributed to its source ("according to A2",
    "police said", "alleged"), never stated as fact. Unattributed sentences are dropped (meta.drop)."""
    drop: list[str] = []
    for sentences in sections.values():
        for s in sentences:
            low = s.text.lower()
            if any(_matches(t, low) for t in terms) and not any(_matches(m, low) for m in markers):
                drop.append(s.text)
    if drop:
        return GuardResult(
            guard_id="G-OUT-03",
            passed=False,
            action="redact",
            reason=f"{len(drop)} unattributed allegation(s) dropped",
            meta={"drop": drop},
        )
    return GuardResult(guard_id="G-OUT-03", passed=True, action="allow", reason="allegations attributed")


_DIGITS = re.compile(r"\d[\d,.]*")
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_ATTRIBUTION_EN = re.compile(r"\b(according to|said|says|alleged|allegedly|claimed|claims|told|accused)\b", re.I)
_ATTRIBUTION = {
    "hi": re.compile(r"अनुसार|मुताबिक|कहा|कहना|आरोप|दावा|बताया"),
    "mr": re.compile(r"नुसार|म्हणाले|म्हणाल्या|म्हटले|सांगितले|आरोप|दावा"),
}

# Named-entity check across scripts: a Devanagari rendering is reduced to a consonant skeleton and compared
# with the English name's skeleton (Modi -> "md", मोदी -> "md"), so a changed name fails while spelling
# variants pass. Aspirates fold into their plain consonant because English spellings vary.
_DEVA = {
    **dict.fromkeys("कखक़ख़", "k"),
    **dict.fromkeys("गघग़", "g"),
    **dict.fromkeys("चछ", "c"),
    **dict.fromkeys("जझज़", "j"),
    **dict.fromkeys("टठतथ", "t"),
    **dict.fromkeys("डढदधड़ढ़", "d"),
    **dict.fromkeys("णनञङंँ", "n"),
    "प": "p",
    **dict.fromkeys("फफ़", "f"),
    **dict.fromkeys("बभ", "b"),
    "म": "m",
    "य": "y",
    "र": "r",
    **dict.fromkeys("लळ", "l"),
    "व": "v",
    **dict.fromkeys("शषस", "s"),
    "ह": "h",
}
_LETTER_NAMES = {
    "a": "",
    "b": "b",
    "c": "s",
    "d": "d",
    "e": "",
    "f": "f",
    "g": "j",
    "h": "c",
    "i": "",
    "j": "j",
    "k": "k",
    "l": "l",
    "m": "m",
    "n": "n",
    "o": "",
    "p": "p",
    "q": "ky",
    "r": "r",
    "s": "s",
    "t": "t",
    "u": "y",
    "v": "v",
    "w": "dbly",
    "x": "ks",
    "y": "v",
    "z": "jd",
}
# English function words, weekdays and months: capitalized but never names (they are translated). Domain
# words come from config.
_FUNCTION_WORDS = frozenset(
    [
        "the",
        "a",
        "an",
        "this",
        "that",
        "these",
        "those",
        "however",
        "meanwhile",
        "according",
        "after",
        "before",
        "while",
        "when",
        "he",
        "she",
        "they",
        "it",
        "we",
        "his",
        "her",
        "their",
        "its",
        "in",
        "on",
        "at",
        "for",
        "with",
        "some",
        "several",
        "many",
        "both",
        "one",
        "two",
        "three",
        "no",
        "all",
        "also",
        "but",
        "and",
        "or",
        "if",
        "as",
        "by",
        "from",
        "there",
        "here",
        "what",
        "who",
        "which",
        "where",
        "why",
        "how",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    ]
)
_RUN = re.compile(r"(?:[A-Z][a-z']+|[A-Z]{2,5})(?:\s+(?:[A-Z][a-z']+|[A-Z]{2,5}))+")
_NAME = re.compile(r"\b(?:[A-Z][a-z]+|[A-Z]{2,5})\b")


def _collapse(s: str) -> str:
    return re.sub(r"(.)\1+", r"\1", s)


def _skel_deva(word: str) -> str:
    out = []
    for i, ch in enumerate(word):
        c = _DEVA.get(ch, "")
        if ch in "ंँ":  # anusvara sounds m before a labial (मुंबई -> "mb"), n elsewhere (गांधी -> "gnd")
            nxt = next((_DEVA[x] for x in word[i + 1 :] if x in _DEVA and x not in "ंँ"), "")
            c = "m" if nxt in ("p", "f", "b", "m") else "n"
        out.append(c)
    return _collapse("".join(out))


def _skel_en(word: str) -> str:
    w = re.sub(r"^x", "s", word.lower())  # an initial x is not "ks": Xi -> शी
    w = w.replace("sh", "S").replace("ch", "C").replace("ph", "F")  # sounds with their own Devanagari letter
    w = re.sub(r"(?<=[bcdfgjklmnpqrstvwxz])h", "", w)  # other h after a consonant: aspirate or silent (Delhi)
    for a, b in (
        ("ck", "k"),
        ("q", "k"),
        ("x", "ks"),
        ("w", "v"),
        ("z", "j"),
        ("c", "k"),
        ("S", "s"),
        ("C", "c"),
        ("F", "f"),
    ):
        w = w.replace(a, b)
    return _collapse(re.sub(r"[aeiou]", "", w))


def _similar(a: str, b: str) -> bool:
    from difflib import SequenceMatcher

    # A name can be part of a longer word ("Sri" in श्रीलंका -> "srlnk").
    return a == b or (len(a) >= 2 and (a in b or SequenceMatcher(None, a, b).ratio() >= 0.75))


def entities_kept(
    source: str,
    translated: str,
    skip: AbstractSet[str],
    aliases: Mapping[str, list[str]],
    phrase_words: AbstractSet[str] = frozenset(),
) -> list[str]:
    """Names (capitalized words, acronyms) in `source` with no recognisable rendering in `translated`."""
    # ponytail: a sentence's first word is only checked when it is an acronym, because capitalized common words
    # ("Phase", "Officials") start sentences; a name opening a sentence goes unchecked. NER if that matters.
    first = {m.group(1) for m in re.finditer(r"(?:^|[.!?]\s+)([A-Za-z]+)", source) if not m.group(1).isupper()}
    words = [w.strip(".,;:!?\"'()") for w in translated.split()]
    skels = [_skel_deva(w) for w in words]
    missing = []
    # A capitalized phrase with an institutional or event word ("Asian Games", "United States", "First
    # Amendment") is a name that gets translated, not transliterated: skip every word in it.
    in_phrase = {
        w for run in _RUN.findall(source) if any(x.lower() in phrase_words for x in run.split()) for w in run.split()
    }
    for name in dict.fromkeys(_NAME.findall(source)):
        if name.lower() in skip or name.lower() in phrase_words or name in first or name in in_phrase:
            continue
        if name in translated or any(a in translated for a in aliases.get(name, [])):
            continue
        cands = {_skel_en(name)} | ({"".join(_LETTER_NAMES[c] for c in name.lower())} if name.isupper() else set())
        cands = {c for c in cands if len(c) >= 2}
        if not cands:
            continue  # too short to compare reliably (for example "Ali")
        joined = [s1 + s2 for s1, s2 in pairwise(skels)]
        if not any(_similar(c, sk) for c in cands for sk in [*skels, *joined] if sk):
            missing.append(name)
    return missing


def _numbers(text: str) -> list[str]:
    return sorted(n.rstrip(".,") for n in _DIGITS.findall(text.translate(_DEVANAGARI_DIGITS)))


@traced_guard("G-OUT-06", "output")
def check_translation(
    source: Sequence[str],
    translated: Sequence[str],
    lang: str = "hi",
    skip_words: Sequence[str] = (),
    aliases: Mapping[str, list[str]] | None = None,
    phrase_words: Sequence[str] = (),
) -> GuardResult:
    """Post-translation check (docs/07): one output per input, every number kept, attribution not dropped,
    and every named entity still recognisable in the target script."""
    if len(source) != len(translated):
        return GuardResult(
            guard_id="G-OUT-06", passed=False, action="block", reason=f"{len(translated)} lines for {len(source)}"
        )
    attribution = _ATTRIBUTION.get(lang, _ATTRIBUTION["hi"])
    skip, al = _FUNCTION_WORDS | {w.lower() for w in skip_words}, dict(aliases or {})
    problems: dict[int, list[str]] = {}
    for i, (s, t) in enumerate(zip(source, translated, strict=True)):
        why = []
        if not t.strip():
            why.append("empty")
        if _numbers(s) != _numbers(t):
            why.append("number")
        if _ATTRIBUTION_EN.search(s) is not None and attribution.search(t) is None:
            why.append("attribution")
        if lost := entities_kept(s, t, skip, al, {w.lower() for w in phrase_words}):
            why.append("entity:" + ",".join(lost))
        if why:
            problems[i] = why
    if problems:
        return GuardResult(
            guard_id="G-OUT-06",
            passed=False,
            action="block",
            reason=f"{len(problems)} line(s) lost a number, an attribution or a name",
            meta={"lines": sorted(problems), "why": {str(k): v for k, v in problems.items()}},
        )
    return GuardResult(guard_id="G-OUT-06", passed=True, action="allow", reason=f"{len(source)} lines checked")


# A sentence may mention a debunked claim only while saying it was fact-checked (G-GEN-06).
_FACTCHECK_MARKER = re.compile(r"fact.?check|\brated\b|debunk|फैक्ट.?चेक|तथ्य.?जांच|भ्रामक|झूठा|फर्जी", re.I)


@traced_guard("G-GEN-06", "generation")
def check_false_balance(texts: Sequence[str], similarity: Sequence[float], threshold: float) -> GuardResult:
    """No false balance (docs/07): a sentence that restates a claim a fact-checker rated false or misleading
    (similarity >= threshold, computed by the caller) must present the fact-check, not the claim as one side.
    Such sentences are dropped; the answer shows the fact-checker's rating and link separately."""
    drop = [t for t, s in zip(texts, similarity, strict=True) if s >= threshold and not _FACTCHECK_MARKER.search(t)]
    if drop:
        return GuardResult(
            guard_id="G-GEN-06",
            passed=False,
            action="redact",
            reason=f"{len(drop)} sentence(s) restate a claim fact-checkers rated false or misleading",
            meta={"drop": drop},
        )
    return GuardResult(guard_id="G-GEN-06", passed=True, action="allow", reason="no debunked claim restated")


@traced_guard("G-OUT-06", "output")
def check_translation_judged(unfaithful: Sequence[int], total: int) -> GuardResult:
    """G-OUT-06 light check: lines an independent judge found unfaithful (meaning, not only names and numbers)."""
    if unfaithful:
        return GuardResult(
            guard_id="G-OUT-06",
            passed=False,
            action="block",
            reason=f"judge: {len(unfaithful)} of {total} line(s) not faithful",
            meta={"lines": list(unfaithful), "check": "judge"},
        )
    return GuardResult(
        guard_id="G-OUT-06",
        passed=True,
        action="allow",
        reason=f"judge: {total} lines faithful",
        meta={"check": "judge"},
    )
