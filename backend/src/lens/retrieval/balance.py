"""Source-balanced evidence selection (docs/05). Pure code, no I/O.

A plain top-k often returns many chunks from two outlets, which destroys a coverage comparison.
After reranking:
1. collapse syndicated copies (keep originals),
2. round-robin by source in rank order, with a per-source cap, up to `max_chunks`,
3. force-include the best remaining chunk of any language group or bias bucket (ADR-0020) that the
   candidates contain but the selection lacks, replacing the lowest-ranked picks if needed.
Personalization never changes this selection (CLAUDE.md rule 5).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from lens.retrieval.search import Hit


def _group(h: Hit, bias_of: Mapping[str, str], dim: str) -> str:
    if dim == "language":
        return "en" if h.language.split("-")[0] == "en" else "indic"
    return bias_of.get(h.source_id, "unrated")


def select(hits: Sequence[Hit], bias_of: Mapping[str, str], cfg: Mapping[str, Any]) -> list[Hit]:
    pool = [h for h in hits if not (cfg["collapse_syndicated"] and h.is_syndicated)]
    # Round-robin by source: rank r of each source's chunks, then original rank.
    rank_in_source: Counter[str] = Counter()
    keyed = []
    for i, h in enumerate(pool):
        keyed.append((rank_in_source[h.source_id], i, h))
        rank_in_source[h.source_id] += 1
    picked: list[Hit] = []
    per_source: Counter[str] = Counter()
    for _, _, h in sorted(keyed, key=lambda t: (t[0], t[1])):
        if per_source[h.source_id] >= cfg["per_source_cap"]:
            continue
        picked.append(h)
        per_source[h.source_id] += 1
        if len(picked) >= cfg["max_chunks"]:
            break

    dims = [d for d, on in (("language", cfg["ensure_language_groups"]), ("bias", cfg["ensure_bias_buckets"])) if on]
    for dim in dims:
        have = {_group(h, bias_of, dim) for h in picked}
        for h in pool:  # pool is in rank order: the first chunk of a missing group is its best
            g = _group(h, bias_of, dim)
            if g in have or h in picked:
                continue
            if len(picked) >= cfg["max_chunks"]:
                # Replace the lowest-ranked pick whose group stays represented without it.
                for j in range(len(picked) - 1, -1, -1):
                    rest = picked[:j] + picked[j + 1 :]
                    if all(any(_group(x, bias_of, d) == _group(picked[j], bias_of, d) for x in rest) for d in dims):
                        picked.pop(j)
                        break
                else:
                    continue
            picked.append(h)
            have.add(g)
    return picked
