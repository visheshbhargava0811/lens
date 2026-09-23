"""Deterministic keys for deduplication: canonical URLs, content hashes and SimHash."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query parameters that only track the click, never select content.
_TRACKING = re.compile(
    r"^(utm_.*|fbclid|gclid|dclid|mc_[a-z]+|igshid|ref|ref_src|ref_url|from|src|source|cmp|campaign|ito|pfrom|ncid|ocid|ns_.*)$",
    re.I,
)
# Word characters plus Indic blocks (U+0900-U+0DFF, Devanagari through Sinhala) and ZWJ/ZWNJ.
# Plain \w excludes vowel signs and viramas (combining marks), which shatters Indic words into
# single letters and makes unrelated Hindi or Marathi texts look like near-duplicates.
_WORD = re.compile(r"[\w\u0900-\u0dff\u200c\u200d]+", re.UNICODE)


def canonical_url(url: str) -> str:
    """Lowercase scheme and host, drop fragment, default ports, tracking params and a trailing slash."""
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    if scheme == "http":
        scheme = "https"  # same article; publishers serve both
    host = (parts.hostname or "").lower()
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"
    query = urlencode(
        sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _TRACKING.match(k))
    )
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return urlunsplit((scheme, host, path, query, ""))


def normalize_text(text: str) -> str:
    """NFC, casefold, collapse whitespace. Keeps the original script (rule 13)."""
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def content_hash(title: str, snippet: str | None) -> str:
    return hashlib.sha256(f"{normalize_text(title)}\n{normalize_text(snippet or '')}".encode()).hexdigest()


def _tokens(text: str) -> list[str]:
    return _WORD.findall(normalize_text(text))


def word_tokens(text: str) -> list[str]:
    """Normalized word tokens, Indic combining marks kept inside words (ADR-0014). Used by BM25."""
    return _tokens(text)


def simhash64(text: str, shingle: int = 1) -> int:
    """64-bit SimHash over word shingles, as a signed int to fit Postgres BIGINT.

    Unigrams by default: headlines are too short for longer shingles."""
    toks = _tokens(text)
    grams = [" ".join(toks[i : i + shingle]) for i in range(max(1, len(toks) - shingle + 1))] if toks else []
    if not grams:
        return 0
    v = [0] * 64
    for g in grams:
        h = int.from_bytes(hashlib.blake2b(g.encode(), digest_size=8).digest(), "big")
        for i in range(64):
            v[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i in range(64):
        if v[i] > 0:
            out |= 1 << i
    return out - (1 << 64) if out >= 1 << 63 else out


def hamming(a: int, b: int) -> int:
    return ((a ^ b) & ((1 << 64) - 1)).bit_count()


def jaccard(a: str, b: str) -> float:
    ta, tb = set(_tokens(a)), set(_tokens(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def is_near_duplicate(a: str, b: str, sim_a: int, sim_b: int, max_hamming: int, min_jaccard: float) -> bool:
    """SimHash pre-filter, then exact word-set overlap to confirm."""
    return hamming(sim_a, sim_b) <= max_hamming and jaccard(a, b) >= min_jaccard
