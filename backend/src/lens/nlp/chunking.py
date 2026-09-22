"""Indic-aware sentence splitting and chunking with character offsets (docs/04 section 4).

Offsets index into the analyzed text (full_text if present, else title + "\\n" + snippet). Quote
verification and citation highlighting depend on them, so every chunk keeps char_start/char_end.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

# Sentence ends: . ? ! and the Devanagari danda / double danda, followed by whitespace.
_SENT_END = re.compile(r"(?<=[.!?।॥])\s+")
# Common abbreviations that end with a period but do not end a sentence.
_ABBREV = re.compile(
    r"(?:\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|No|Vs|vs|Govt|govt|Dept|Rs|Ltd|Co|Inc|Gen|Col|Lt|Capt|Hon|Sh|Smt)|\b[A-Z])\.$"
)


@dataclass(frozen=True)
class Chunk:
    text: str
    start: int
    end: int


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) character spans of sentences. Never loses or reorders characters."""
    spans: list[tuple[int, int]] = []
    start = 0
    for m in _SENT_END.finditer(text):
        piece = text[start : m.start()]
        if _ABBREV.search(piece):
            continue  # "Dr. Singh" is one sentence
        if piece.strip():
            spans.append((start, m.start()))
        start = m.end()
    if text[start:].strip():
        spans.append((start, len(text.rstrip())))
    return spans


def recursive_chunks(text: str, max_chars: int = 1200) -> list[Chunk]:
    """Baseline: paragraphs first, then sentences, packed up to max_chars."""
    chunks: list[Chunk] = []
    for para in re.finditer(r"[^\n]+(?:\n(?!\n)[^\n]+)*", text):
        p0 = para.start()
        cur_start = cur_end = None
        for a, b in sentence_spans(para.group()):
            a, b = a + p0, b + p0
            if cur_start is None:
                cur_start, cur_end = a, b
            elif b - cur_start > max_chars:
                chunks.append(Chunk(text[cur_start:cur_end], cur_start, cur_end))  # type: ignore[arg-type]
                cur_start, cur_end = a, b
            else:
                cur_end = b
        if cur_start is not None and cur_end is not None:
            chunks.append(Chunk(text[cur_start:cur_end], cur_start, cur_end))
    return chunks or ([Chunk(text, 0, len(text))] if text.strip() else [])


def semantic_chunks(
    text: str,
    embed: Callable[[Sequence[str]], np.ndarray],
    pct: float = 90,
    min_sents: int = 2,
    max_chars: int = 1200,
) -> list[Chunk]:
    """Split where adjacent-sentence distance exceeds the pct-th percentile (docs/04 reference)."""
    spans = sentence_spans(text)
    if len(spans) < 2:
        return [Chunk(text, 0, len(text))] if text.strip() else []
    emb = np.asarray(embed([text[a:b] for a, b in spans]), dtype=np.float32)
    dist = 1.0 - (emb[:-1] * emb[1:]).sum(axis=1)
    cut = float(np.percentile(dist, pct))
    groups: list[tuple[int, int]] = []
    s0 = 0
    for i, d in enumerate(dist):
        size = spans[i][1] - spans[s0][0]
        if (d > cut and i + 1 - s0 >= min_sents) or size > max_chars:
            groups.append((s0, i))
            s0 = i + 1
    groups.append((s0, len(spans) - 1))
    return [Chunk(text[spans[a][0] : spans[b][1]], spans[a][0], spans[b][1]) for a, b in groups]


def analyzed_text(title: str, snippet: str | None, full_text: str | None) -> str:
    """The text that chunk offsets refer to (docs/03)."""
    if full_text:
        return full_text
    return f"{title}\n{snippet}" if snippet else title


def chunk_article(title: str, snippet: str | None, full_text: str | None, **kw: object) -> list[Chunk]:
    """Snippet and headline-only articles are one chunk (docs/04); full text uses recursive chunking
    until Phase 5 shows semantic chunking earns its cost."""
    text = analyzed_text(title, snippet, full_text)
    if not full_text:
        return [Chunk(text, 0, len(text))]
    return recursive_chunks(text, **kw)  # type: ignore[arg-type]
