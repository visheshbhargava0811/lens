"""G-OUT-05 PII masking (docs/07): Aadhaar, PAN, phone numbers, vehicle plates and emails.

One `mask` function serves three places: Ask output (a traced guard), log records (a structlog
processor) and LangSmith traces (the client's hide_inputs / hide_outputs), so user text and article
text never leave the process with these identifiers in them. Regexes, India-specific; Presidio can
sit behind this later.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any

from lens.guardrails.base import GuardResult, traced_guard

_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("aadhaar", re.compile(r"\b[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}\b")),
    ("pan", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("phone", re.compile(r"(?<![\w+])(?:\+91[ -]?|0)?[6-9]\d{4}[ -]?\d{5}\b")),
    ("vehicle_plate", re.compile(r"\b[A-Z]{2}[ -]?\d{1,2}[ -]?[A-Z]{1,3}[ -]?\d{4}\b")),
]


def mask(text: str) -> tuple[str, dict[str, int]]:
    """Replaces each identifier with [kind]; returns the masked text and counts per kind."""
    counts: dict[str, int] = {}
    for kind, pattern in _RULES:
        text, n = pattern.subn(f"[{kind}]", text)
        if n:
            counts[kind] = counts.get(kind, 0) + n
    return text, counts


def mask_any(data: Any) -> Any:
    """Masks every string inside nested dicts, lists and tuples (for traces)."""
    if isinstance(data, str):
        return mask(data)[0]
    if isinstance(data, Mapping):
        return {k: mask_any(v) for k, v in data.items()}
    if isinstance(data, list | tuple):
        return type(data)(mask_any(v) for v in data)
    return data


def structlog_processor(_: Any, __: str, event: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    for k, v in event.items():
        event[k] = mask_any(v)
    return event


@traced_guard("G-OUT-05", "output")
def check_pii(texts: Sequence[str]) -> GuardResult:
    """Reports identifiers in output texts; callers replace the texts with `mask`."""
    total: dict[str, int] = {}
    for t in texts:
        for kind, n in mask(t)[1].items():
            total[kind] = total.get(kind, 0) + n
    if total:
        return GuardResult(
            guard_id="G-OUT-05",
            passed=False,
            action="redact",
            reason=f"masked {sum(total.values())} identifier(s)",
            meta=total,
        )
    return GuardResult(guard_id="G-OUT-05", passed=True, action="allow", reason="no personal identifiers")
