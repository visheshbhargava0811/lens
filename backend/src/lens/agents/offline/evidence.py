"""Evidence for story analysis (docs/06 "Untrusted-content handling", ADR-0022). Pure code, no I/O.

- One article per outlet (the one with the most text), balanced across bias buckets and then
  languages so no side dominates the prompt, capped at `max_articles`.
- Masked: the model sees refs (A1..An), never outlet names. Code maps refs back.
- Cleaned: HTML tags, zero-width and control characters are stripped before insertion.
"""

from __future__ import annotations

import html
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from itertools import zip_longest

_TAG = re.compile(r"<[^>]+>")
_INVISIBLE = re.compile(r"[​-‏‪-‮⁠-⁤﻿­]")  # zero-width, bidi, soft hyphen
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACE = re.compile(r"\s+")


def clean(text: str | None) -> str:
    """Untrusted feed text -> plain text safe to put inside <evidence>. Keeps the original script."""
    if not text:
        return ""
    t = html.unescape(_TAG.sub(" ", text))
    t = _CONTROL.sub(" ", _INVISIBLE.sub("", t))
    # Angle brackets become single guillemets (U+2039, U+203A): article text can never close our tags.
    t = t.replace("<", "\u2039").replace(">", "\u203a")
    return unicodedata.normalize("NFC", _SPACE.sub(" ", t)).strip()


def normalize(text: str) -> str:
    """G-GEN-02 comparison form: NFC and collapsed whitespace only (docs/04 section 6)."""
    return _SPACE.sub(" ", unicodedata.normalize("NFC", text)).strip()


@dataclass(frozen=True)
class ArticleIn:
    article_id: str
    source_id: str
    source_name: str
    language: str
    published_at: datetime
    title: str
    snippet: str | None
    bias: str  # left | center | right | unrated (stats bucket)


@dataclass(frozen=True)
class EvidenceArticle:
    ref: str
    article: ArticleIn
    text: str  # cleaned "headline\nsummary": what the model sees and what quotes are checked against


def article_text(title: str, snippet: str | None) -> str:
    """What the model sees for one article, and what its quotes are checked against."""
    t, sn = clean(title), clean(snippet)
    return f"{t}\n{sn}" if sn and sn != t else t


def _text(a: ArticleIn) -> str:
    return article_text(a.title, a.snippet)


def select_evidence(articles: list[ArticleIn], max_articles: int) -> list[EvidenceArticle]:
    best: dict[str, ArticleIn] = {}
    for a in sorted(articles, key=lambda a: (a.published_at, a.article_id)):
        cur = best.get(a.source_id)
        if cur is None or len(_text(a)) > len(_text(cur)):
            best[a.source_id] = a
    # Round-robin over bias buckets; inside a bucket, round-robin over languages.
    by_bias: dict[str, dict[str, list[ArticleIn]]] = defaultdict(lambda: defaultdict(list))
    for a in sorted(best.values(), key=lambda a: (a.published_at, a.article_id)):
        by_bias[a.bias][a.language.split("-")[0]].append(a)
    columns = [
        [a for group in zip_longest(*langs.values()) for a in group if a is not None]
        for _, langs in sorted(by_bias.items())
    ]
    ordered = [a for row in zip_longest(*columns) for a in row if a is not None][:max_articles]
    return [EvidenceArticle(ref=f"A{i + 1}", article=a, text=_text(a)) for i, a in enumerate(ordered)]


def render(evidence: list[EvidenceArticle]) -> str:
    """The <evidence> block. No outlet names (masked), original language, publish time for order."""
    parts = ["<evidence>"]
    for e in evidence:
        a = e.article
        parts.append(f'<article ref="{e.ref}" lang="{a.language}" published="{a.published_at:%Y-%m-%d %H:%M} UTC">')
        parts.append(e.text)
        parts.append("</article>")
    parts.append("</evidence>")
    return "\n".join(parts)


def quote_span(quote: str, text: str) -> tuple[int, int] | None:
    """G-GEN-02: where the quote occurs verbatim in the (normalized) article text, else None."""
    q, t = normalize(quote), normalize(text)
    if not q:
        return None
    i = t.find(q)
    return (i, i + len(q)) if i >= 0 else None
