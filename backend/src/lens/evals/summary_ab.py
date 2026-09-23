"""A/B test a summary prompt against the live one (docs/08: no prompt change without an eval delta).

Both variants summarize the same deterministic sample of analysed stories from the same evidence,
first try only (no retries, no pruning), and the same calibrated judge (primary model only) checks
every sentence. Reported per variant: judge pass rate, share of sentences supported, over-general
scope words, sentences per summary, and G-GEN-01 failures, so a "win" cannot come from writing less.

Usage: make eval-summary-ab [N=12]   (candidate: agents/skills/synthesis_system.candidate.md)
Writes reports/summary_ab_<date>.md and .json
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from lens.agents.offline.evidence import EvidenceArticle, render, select_evidence
from lens.agents.offline.story_graph import judge_lines
from lens.agents.prompts import system_prompt
from lens.core.config_files import load_yaml
from lens.core.settings import REPO_ROOT
from lens.db.models import Story, StorySummary
from lens.db.session import get_engine
from lens.guardrails.generation import check_citations
from lens.llm.client import LLMError, structured, tier_chain
from lens.pipeline.analyze import load_articles
from lens.schemas.analysis import FaithfulnessVerdict, SummaryDraft

SCOPE = re.compile(
    r"\b(all|each|every|most|multiple|several)\b[^.]{0,40}\b(articles?|sources?|reports?|outlets?|coverage)\b", re.I
)


def _sample(n: int, seed: int) -> list[Story]:
    with Session(get_engine()) as s:
        ids = sorted({sid for (sid,) in s.execute(select(StorySummary.story_id))}, key=str)
        random.Random(seed).shuffle(ids)
        return [s.get_one(Story, i) for i in ids[:n]]


def _judge_only_primary() -> set[str]:
    chain = tier_chain("judge")
    return {t.family for t in chain[1:]} - {chain[0].family}


def _run_variant(task: str, story: Story, evidence: list[EvidenceArticle]) -> dict[str, Any]:
    system, version = system_prompt(task)
    user = f"Story headline (for context only): {story.headline}\n\n{render(evidence)}"
    try:
        draft = structured(
            "synthesis", SummaryDraft, system, user, run_name=f"eval.summary_ab.{task}", prompt_version=version
        )
    except LLMError as e:
        return {"error": f"summary: {e}"[:300], "version": version}
    sections = {"summary": draft.summary, "agreements": draft.agreements, "disagreements": draft.disagreements}
    cites = check_citations(sections, {e.ref for e in evidence})
    texts = [s.text for sec in sections.values() for s in sec]
    out: dict[str, Any] = {
        "version": version,
        "sentences": len(texts),
        "citations_ok": cites.passed,
        "scope_words": sum(1 for t in texts if SCOPE.search(t)),
        "texts": texts,
    }
    if not cites.passed:
        return out
    jsys, jver = system_prompt("judge_faithfulness")
    try:
        v = structured(
            "judge",
            FaithfulnessVerdict,
            jsys,
            f"{user}\n\nSentences to check:\n{judge_lines(draft)}",
            run_name="eval.summary_ab.judge",
            prompt_version=jver,
            exclude_families=_judge_only_primary(),
        )
    except LLMError as e:
        out["error"] = f"judge: {e}"[:300]
        return out
    unsupported = sum(1 for t in texts if any(t.strip() and t.strip() in u for u in v.unsupported_sentences))
    out.update(passed=v.verdict == "pass" and not v.unsupported_sentences, unsupported=unsupported)
    return out


def run(n: int, seed: int, candidate: str) -> dict[str, Any]:
    cfg = load_yaml("clustering.yaml")["analysis"]
    variants = {"live": "synthesis_system", "candidate": candidate}
    rows: list[dict[str, Any]] = []
    for story in _sample(n, seed):
        with Session(get_engine()) as s:
            evidence = select_evidence(load_articles(s, story), cfg["max_articles"])
        row: dict[str, Any] = {"story": story.slug}
        row.update({name: _run_variant(task, story, evidence) for name, task in variants.items()})
        rows.append(row)
        print(
            f"{story.slug[:50]:50} live={row['live'].get('passed')} candidate={row['candidate'].get('passed')}",
            flush=True,
        )

    def agg(name: str) -> dict[str, Any]:
        judged = [r[name] for r in rows if "passed" in r[name]]
        sents = sum(r["sentences"] for r in judged)
        return {
            "version": next((r[name]["version"] for r in rows), None),
            "judged": len(judged),
            "errors": sum(1 for r in rows if "error" in r[name]),
            "citation_failures": sum(1 for r in rows if r[name].get("citations_ok") is False),
            "judge_pass_rate": round(sum(r["passed"] for r in judged) / len(judged), 3) if judged else None,
            "sentence_supported_rate": round(1 - sum(r["unsupported"] for r in judged) / sents, 3) if sents else None,
            "sentences_per_summary": round(sents / len(judged), 2) if judged else None,
            "scope_word_sentences": sum(r[name].get("scope_words", 0) for r in rows),
        }

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "n": len(rows),
        "seed": seed,
        "live": agg("live"),
        "candidate": agg("candidate"),
        "rows": rows,
    }
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M")
    (REPO_ROOT / "reports" / f"summary_ab_{stamp}.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    md = _markdown(report)
    (REPO_ROOT / "reports" / f"summary_ab_{stamp}.md").write_text(md, encoding="utf-8")
    print(md)
    return report


def _markdown(r: dict[str, Any]) -> str:
    keys = [
        ("judge_pass_rate", "Judge pass rate (whole summary, first try)"),
        ("sentence_supported_rate", "Sentences supported"),
        ("sentences_per_summary", "Sentences per summary"),
        ("scope_word_sentences", "Sentences with all/each/multiple… wording"),
        ("citation_failures", "G-GEN-01 citation failures"),
        ("errors", "Provider errors"),
        ("judged", "Summaries judged"),
    ]
    lines = [
        f"# Summary prompt A/B ({r['generated_at'][:16]} UTC)",
        "",
        f"n = {r['n']} stories (seed {r['seed']}), same evidence and the same judge (primary model only), "
        "first try, no retries.",
        "",
        f"| Metric | live `{r['live']['version']}` | candidate `{r['candidate']['version']}` |",
        "|---|---|---|",
        *(f"| {label} | {r['live'][k]} | {r['candidate'][k]} |" for k, label in keys),
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=12)
    p.add_argument("--seed", type=int, default=11)
    p.add_argument("--candidate", default="synthesis_system.candidate")
    a = p.parse_args()
    run(a.n, a.seed, a.candidate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
