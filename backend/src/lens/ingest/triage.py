"""Triage (docs/04 section 2): language ID, news filter and wire-copy markers. Deterministic code first."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from lingua import Language, LanguageDetector, LanguageDetectorBuilder

from lens.core.config_files import load_yaml

# Unicode script -> language, for scripts used by a single launch-candidate language.
_SCRIPT_LANG = {
    "BENGALI": "bn",
    "TAMIL": "ta",
    "TELUGU": "te",
    "GUJARATI": "gu",
    "GURMUKHI": "pa",
    "KANNADA": "kn",
    "MALAYALAM": "ml",
    "ORIYA": "or",
}
_LINGUA_CODE = {Language.HINDI: "hi", Language.MARATHI: "mr", Language.ENGLISH: "en", Language.URDU: "ur"}

# Very common function words in romanized Hindi. Used only on Latin-script text that lingua
# does not confidently call English. Measured, not assumed: see reports/langid_baseline.md.
_HINGLISH = {
    # Words that are also common English words ("the", "me", "log", "par", "ho") are left out on purpose.
    "hai",
    "hain",
    "ka",
    "ki",
    "ke",
    "ko",
    "se",
    "mein",
    "nahi",
    "nahin",
    "aur",
    "kya",
    "bhi",
    "tha",
    "thi",
    "kar",
    "karna",
    "raha",
    "rahi",
    "rahe",
    "baare",
    "batao",
    "kaise",
    "kyun",
    "kyon",
    "wala",
    "wali",
    "wale",
    "gaya",
    "gayi",
    "gaye",
    "diya",
    "liya",
    "sakta",
    "abhi",
    "aaj",
    "yeh",
    "woh",
    "hum",
    "tum",
    "aap",
    "unka",
    "unki",
    "sarkar",
    "desh",
    "kab",
    "kaun",
    "kahan",
    "kitna",
    "kitne",
    "kitni",
    "liye",
    "tak",
    "hoga",
    "hogi",
    "honge",
    "kuch",
    "koi",
    "apna",
    "apni",
    "mujhe",
    "hamein",
    "iske",
    "uske",
    "saath",
    "aayenge",
}

# Hindi vs Marathi (both Devanagari). lingua is weak on short headlines, so whole-word function words
# and Marathi case suffixes decide first; lingua only breaks ties. Measured in reports/langid_*.json.
_HI_WORDS = {
    "का",
    "की",
    "के",
    "में",
    "है",
    "हैं",
    "से",
    "को",
    "और",
    "पर",
    "भी",
    "नहीं",
    "था",
    "थी",
    "थे",
    "गया",
    "गई",
    "गए",
    "किया",
    "लिए",
    "ने",
    "कहा",
    "हुआ",
    "हुई",
    "हुए",
    "रहा",
    "रही",
    "रहे",
    "जाएगा",
    "वाले",
    "वाली",
}
_MR_WORDS = {
    "आहे",
    "आहेत",
    "नाही",
    "आणि",
    "मध्ये",
    "साठी",
    "व",
    "तर",
    "पण",
    "केले",
    "केली",
    "झाले",
    "झाली",
    "होते",
    "होती",
    "म्हणाले",
    "म्हणाली",
    "आता",
    "नंतर",
    "या",
    "हे",
    "ही",
    "येथे",
    "करून",
    "करत",
}
_MR_SUFFIXES = (
    "च्या",
    "ाचे",
    "ाची",
    "ाचा",
    "ांचे",
    "ांची",
    "ांचा",
    "ाला",
    "ाने",
    "ांना",
    "मध्ये",
    "साठी",
    "तील",
    "ातून",
    "नंतर",
)
_DEVA_WORD = re.compile(r"[\u0900-\u097f\u200c\u200d]+")


def _hi_mr_vote(text: str) -> str | None:
    words = _DEVA_WORD.findall(text)
    hi = sum(1 for w in words if w in _HI_WORDS)
    mr = sum(1 for w in words if w in _MR_WORDS)
    mr += sum(1 for w in words if w not in _MR_WORDS and len(w) > 3 and w.endswith(_MR_SUFFIXES))
    mr += text.count("ळ")  # rare in Hindi, common in Marathi
    if hi > mr:
        return "hi"
    if mr > hi:
        return "mr"
    return None


_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


@dataclass(frozen=True)
class LangResult:
    code: str  # ISO 639-1, or "hi-Latn" for romanized Hindi, or "und"
    confidence: float


@lru_cache
def _detector(kind: str) -> LanguageDetector:
    langs = {
        "deva": [Language.HINDI, Language.MARATHI],
        "latn": [Language.ENGLISH, Language.HINDI],  # lingua models romanized text poorly; see below
        "arab": [Language.URDU],
    }[kind]
    return LanguageDetectorBuilder.from_languages(*langs).build()


def _script_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ch in text:
        # Count letters and combining marks: Indic vowel signs and viramas are marks, not letters,
        # and skipping them undercounts Devanagari against Latin in mixed headlines.
        if not unicodedata.category(ch).startswith(("L", "M")):
            continue
        try:
            name = unicodedata.name(ch)
        except ValueError:
            continue
        script = name.split(" ", 1)[0]
        if script == "LATIN":
            key = "LATIN"
        elif script == "DEVANAGARI":
            key = "DEVANAGARI"
        elif script == "ARABIC":
            key = "ARABIC"
        else:
            key = script
        counts[key] = counts.get(key, 0) + 1
    return counts


def detect_language(text: str, declared: str | None = None) -> LangResult:
    """Script first; lingua only where a script is shared (Devanagari: hi/mr; Latin: en/hi-Latn).

    `declared` is the language the feed itself states (RSS <language>, sitemap news:language). It only
    breaks a tie between Hindi and Marathi when the text carries no evidence either way."""
    counts = _script_counts(text)
    total = sum(counts.values())
    if total == 0:
        return LangResult("und", 0.0)
    script, n = max(counts.items(), key=lambda kv: kv[1])
    share = n / total
    if script in _SCRIPT_LANG:
        return LangResult(_SCRIPT_LANG[script], round(share, 3))
    if script == "DEVANAGARI":
        values = _detector("deva").compute_language_confidence_values(text)
        vote = _hi_mr_vote(text)
        if vote is not None:
            conf = next(v.value for v in values if _LINGUA_CODE[v.language] == vote)
            return LangResult(vote, round(max(conf, 0.6) * share, 3))
        hint = (declared or "").split("-")[0].lower()
        if hint in ("hi", "mr"):
            conf = next(v.value for v in values if _LINGUA_CODE[v.language] == hint)
            return LangResult(hint, round(conf * share, 3))
        best = values[0]
        return LangResult(_LINGUA_CODE[best.language], round(best.value * share, 3))
    if script == "ARABIC":
        return LangResult("ur", round(share, 3))
    if script == "LATIN":
        words = [w.casefold() for w in _WORD.findall(text)]
        hits = sum(1 for w in words if w in _HINGLISH)
        ratio = hits / len(words) if words else 0.0
        # Two or more Hindi function words making up at least a fifth of the text: romanized Hindi.
        if hits >= 2 and ratio >= 0.2:
            return LangResult("hi-Latn", round(min(1.0, 0.5 + ratio), 3))
        values = _detector("latn").compute_language_confidence_values(text)
        en = next((v.value for v in values if v.language == Language.ENGLISH), 0.0)
        return LangResult("en", round(en * share, 3))
    return LangResult("und", round(share, 3))


# ------------------------------------------------------------------ news filter


@dataclass(frozen=True)
class NewsVerdict:
    is_news: bool
    is_opinion: bool
    reason: str | None


@lru_cache
def _ingest_cfg() -> dict[str, Any]:
    return load_yaml("ingest.yaml")


def classify_news(url: str, title: str) -> NewsVerdict:
    """Rules first (docs/04). A small classifier can replace or back these later."""
    cfg = _ingest_cfg()["news_filter"]
    u, t = url.casefold(), title.casefold()
    for pat in cfg["drop_url_patterns"]:
        if pat in u:
            return NewsVerdict(False, False, f"url:{pat}")
    for pat in cfg["drop_title_patterns"]:
        if pat.casefold() in t:
            return NewsVerdict(False, False, f"title:{pat}")
    opinion = any(p in u for p in cfg["opinion_url_patterns"])
    return NewsVerdict(True, opinion, "opinion" if opinion else None)


# ------------------------------------------------------------------ wire markers


@lru_cache
def _wire_patterns() -> list[tuple[str, re.Pattern[str], re.Pattern[str]]]:
    out = []
    for agency, markers in _ingest_cfg()["syndication"]["wire_markers"].items():
        names = [re.escape(m.strip("()")) for m in markers]
        alt = "|".join(sorted(set(names), key=len, reverse=True))
        long_names = [re.escape(m) for m in markers if len(m.strip("()")) > 4 and not m.startswith("(")]
        long_alt = "|".join(sorted(set(long_names), key=len, reverse=True)) or r"(?!x)x"
        # Byline: a full agency name anywhere; a short acronym only as the whole byline, in
        # parentheses, or as "inputs from X" (so a reporter named "Ani ..." is not ANI).
        byline = re.compile(
            rf"(?<!\w)(?:{long_alt})(?!\w)|^\s*(?:{alt})\s*$|\((?:{alt})\)|inputs?\s+from\s+(?:{alt})(?!\w)",
            re.I,
        )
        # Text: only dateline/credit forms, e.g. "(PTI)", "- PTI" at the end, "PTI:" at the start.
        text = re.compile(rf"\((?:{alt})\)|(?:^|[\s:])[-–—]\s*(?:{alt})\s*$|^(?:{alt})\s*[:|]", re.I | re.M)  # noqa: RUF001 (en/em dashes are real dateline credits)
        out.append((agency, byline, text))
    return out


def detect_wire(byline: str | None, title: str, snippet: str | None) -> str | None:
    """Agency name if the item carries a wire marker, else None."""
    for agency, byline_re, text_re in _wire_patterns():
        if byline and byline_re.search(byline):
            return agency
        for field in (snippet or "", title):
            if text_re.search(field):
                return agency
    return None
