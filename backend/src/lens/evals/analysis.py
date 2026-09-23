"""Story analysis evals (docs/08, ADR-0022): judge calibration labeling and the baseline report.

  export  sentences from stored summaries (kept and judge-flagged) with their cited evidence, for a
          person to label supported yes/no. The judge's own verdict is not shown to the labeler.
          -> data/evals/judge_calibration/to_label_<date>.csv
  import  a labeled CSV -> data/evals/judge_calibration/gold_<name>.jsonl (docs/08 format)
  run     baseline report from stored outputs (publish/prune/fail rates, guard pass rates, quote-match
          rate re-checked over every stored claim) and, when a gold file exists, the judge's
          agreement with the human labels (Cohen's kappa, overall and per language).
          -> reports/analysis_<name>.md and .json

Usage: make judge-label-export | make judge-label-import FILE=... ANNOTATOR=... | make eval-analysis
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sklearn.metrics import cohen_kappa_score
from sqlalchemy import select
from sqlalchemy.orm import Session

from lens.agents.offline.evidence import article_text, clean, quote_span
from lens.agents.prompts import system_prompt
from lens.core.settings import REPO_ROOT
from lens.db.models import Article, Claim, GuardEvent, StorySummary
from lens.db.session import get_engine
from lens.llm.client import LLMError, structured, tier, tier_chain
from lens.schemas.analysis import FaithfulnessVerdict

GOLD_DIR = REPO_ROOT / "data/evals/judge_calibration"
REPORTS = REPO_ROOT / "reports"
COLUMNS = ["row", "supported", "notes", "sentence", "evidence", "languages", "summary_id", "section", "article_ids"]
KAPPA_TARGET = 0.6  # docs/08 starting target


def _sentences(session: Session) -> list[dict[str, Any]]:
    """Every stored sentence with citations: summary, agreements, disagreements, and pruned ones."""
    out: list[dict[str, Any]] = []
    for row in session.execute(select(StorySummary)).scalars():
        pruned = [p for p in (row.verifier_result or {}).get("pruned", []) if isinstance(p, dict)]
        for section, sentences in (
            ("summary", row.summary),
            ("agreements", row.agreements),
            ("disagreements", row.disagreements),
            ("pruned", pruned),
        ):
            for s in sentences or []:
                ids = [c["article_id"] for c in s.get("citations", [])]
                if ids:
                    out.append({"text": s["text"], "article_ids": ids, "summary_id": str(row.id), "section": section})
    return out


def _evidence(session: Session, article_ids: list[str]) -> tuple[str, list[str]]:
    rows = {
        str(a.id): a
        for a in session.execute(select(Article).where(Article.id.in_([uuid.UUID(i) for i in article_ids]))).scalars()
    }
    parts, langs = [], []
    for i, aid in enumerate(article_ids, 1):
        a = rows.get(aid)
        if a is not None:
            parts.append(f"[{i}] ({a.language}) {article_text(a.title, a.snippet)}")
            langs.append(a.language.split("-")[0])
    return "\n\n".join(parts), sorted(set(langs))


def export(n: int, seed: int = 7) -> Path:
    with Session(get_engine()) as session:
        items = _sentences(session)
        # Keep every judge-flagged sentence (likely negatives) and sample the rest, so both labels occur.
        flagged = [s for s in items if s["section"] == "pruned"]
        rest = [s for s in items if s["section"] != "pruned"]
        random.Random(seed).shuffle(rest)
        chosen = (flagged + rest)[:n]
        random.Random(seed + 1).shuffle(chosen)  # the labeler cannot tell flagged ones by position
        GOLD_DIR.mkdir(parents=True, exist_ok=True)
        path = GOLD_DIR / f"to_label_{datetime.now(UTC):%Y%m%d}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            for i, s in enumerate(chosen, 1):
                evidence, langs = _evidence(session, s["article_ids"])
                w.writerow(
                    {
                        "row": i,
                        "supported": "",
                        "notes": "",
                        "sentence": clean(s["text"]),
                        "evidence": evidence,
                        "languages": ",".join(langs),
                        "summary_id": s["summary_id"],
                        "section": "",  # hidden: "pruned" would reveal the judge's verdict
                        "article_ids": ",".join(s["article_ids"]),
                    }
                )
    print(f"wrote {path.relative_to(REPO_ROOT)}: {len(chosen)} sentences ({len(flagged)} judge-flagged in the pool)")
    return path


def import_labels(csv_path: Path, annotator: str, name: str) -> Path:
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    out = GOLD_DIR / f"gold_{name}.jsonl"
    labels = {"yes": True, "y": True, "no": False, "n": False}
    kept = 0
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            label = labels.get(r["supported"].strip().lower())
            if label is None:
                continue  # unlabeled or "skip"
            kept += 1
            f.write(
                json.dumps(
                    {
                        "id": f"judge-{name}-{r['row']}",
                        "inputs": {"sentence": r["sentence"], "evidence": r["evidence"]},
                        "reference_outputs": {"supported": label},
                        "tags": {"languages": r["languages"].split(","), "notes": r["notes"] or None},
                        "annotator_ids": [annotator],
                        "created_at": datetime.now(UTC).isoformat(),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(f"wrote {out.relative_to(REPO_ROOT)}: {kept} labeled of {len(rows)} rows")
    return out


def _judge_one(item: dict[str, Any]) -> bool | None:
    """The production judge prompt on one sentence, on the primary judge model only: a fallback
    would mix two judges into one kappa. None if the primary judge was unavailable."""
    chain = tier_chain("judge")
    others = {t.family for t in chain[1:]} - {chain[0].family}
    system, version = system_prompt("judge_faithfulness")
    ev = item["inputs"]["evidence"]
    sentence = item["inputs"]["sentence"]
    user = f"<evidence>\n{ev}\n</evidence>\n\nSentences to check:\n- {sentence} (cites all articles above)"
    try:
        v = structured(
            "judge",
            FaithfulnessVerdict,
            system,
            user,
            run_name="eval.judge_calibration",
            prompt_version=version,
            exclude_families=others,
        )
    except LLMError:
        return None
    return v.verdict == "pass" and not v.unsupported_sentences


def run(name: str, gold: Path | None) -> dict[str, Any]:
    with Session(get_engine()) as session:
        rows = list(session.execute(select(StorySummary)).scalars())
        states = Counter(r.state for r in rows)
        attempts = Counter((r.verifier_result or {}).get("attempts", 0) for r in rows)
        pruned = sum(1 for r in rows if (r.verifier_result or {}).get("pruned"))
        guards: dict[str, Counter[bool]] = defaultdict(Counter)
        for gid, passed in session.execute(
            select(GuardEvent.guard_id, GuardEvent.passed).where(GuardEvent.stage == "story_analysis")
        ):
            guards[gid][passed] += 1
        claims = session.execute(select(Claim, Article).join(Article, Article.id == Claim.article_id)).all()
        quote_ok = sum(1 for c, a in claims if quote_span(c.source_quote, article_text(a.title, a.snippet)) is not None)

    report: dict[str, Any] = {
        "name": name,
        "generated_at": datetime.now(UTC).isoformat(),
        "stories_analysed": len({r.story_id for r in rows}),
        "summary_versions": len(rows),
        "outcomes": dict(states),
        "attempts": {str(k): v for k, v in sorted(attempts.items())},
        "versions_with_pruned_sentences": pruned,
        "first_try_judge_pass_rate": (
            round(guards["G-GEN-03"][True] / sum(guards["G-GEN-03"].values()), 3) if guards["G-GEN-03"] else None
        ),
        "guard_pass_rates": {g: round(c[True] / sum(c.values()), 3) for g, c in sorted(guards.items())},
        "stored_claims": len(claims),
        "quote_match_rate": round(quote_ok / len(claims), 4) if claims else None,
        "framing_present": sum(1 for r in rows if r.framing),
    }

    if gold is not None and gold.exists():
        items = [json.loads(line) for line in gold.read_text(encoding="utf-8").splitlines() if line.strip()]
        human, judge, langs = [], [], []
        for it in items:
            j = _judge_one(it)
            if j is None:
                continue
            human.append(it["reference_outputs"]["supported"])
            judge.append(j)
            langs.append("+".join(it["tags"]["languages"]))
        by_lang: dict[str, dict[str, Any]] = {}
        for lang in sorted(set(langs)):
            idx = [i for i, x in enumerate(langs) if x == lang]
            h, j2 = [human[i] for i in idx], [judge[i] for i in idx]
            by_lang[lang] = {
                "n": len(idx),
                "kappa": _kappa(h, j2),
                "agreement": round(sum(a == b for a, b in zip(h, j2, strict=True)) / len(idx), 3),
            }
        report["judge_calibration"] = {
            "gold": str(gold.relative_to(REPO_ROOT)),
            "judge": f"{tier('judge').provider}/{tier('judge').model}",
            "n": len(human),
            "unscored": len(items) - len(human),
            "kappa": _kappa(human, judge),
            "agreement": round(sum(a == b for a, b in zip(human, judge, strict=True)) / len(human), 3)
            if human
            else None,
            "human_supported_share": round(sum(human) / len(human), 3) if human else None,
            "by_language": by_lang,
            "target": KAPPA_TARGET,
        }

    REPORTS.mkdir(exist_ok=True)
    (REPORTS / f"analysis_{name}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (REPORTS / f"analysis_{name}.md").write_text(_markdown(report), encoding="utf-8")
    print(_markdown(report))
    return report


def _kappa(a: list[bool], b: list[bool]) -> float | None:
    if len(a) < 2 or len(set(a) | set(b)) < 2:
        return None  # undefined with one class
    return round(float(cohen_kappa_score(a, b)), 3)


def _markdown(r: dict[str, Any]) -> str:
    lines = [
        f"# Story analysis eval: {r['name']}",
        "",
        f"Generated {r['generated_at'][:16]} UTC. Raw numbers: `reports/analysis_{r['name']}.json`.",
        "Inputs are headlines and feed summaries only (snippet_only).",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Stories analysed / summary versions | {r['stories_analysed']} / {r['summary_versions']} |",
        f"| Outcomes | {', '.join(f'{k} {v}' for k, v in sorted(r['outcomes'].items()))} |",
        f"| Summary attempts (1 = passed first time) | {', '.join(f'{k}: {v}' for k, v in r['attempts'].items())} |",
        f"| Versions with judge-pruned sentences | {r['versions_with_pruned_sentences']} |",
        f"| G-GEN-03 judge pass rate (per check) | {r['first_try_judge_pass_rate']} |",
        f"| Guard pass rates | {', '.join(f'{k} {v}' for k, v in r['guard_pass_rates'].items())} |",
        f"| Stored claims / quote-match rate (re-checked) | {r['stored_claims']} / {r['quote_match_rate']} |",
        f"| Versions with framing differences | {r['framing_present']} |",
    ]
    jc = r.get("judge_calibration")
    if jc:
        lines += [
            "",
            f"## Judge calibration (`{jc['gold']}`)",
            "",
            f"Judge `{jc['judge']}` (primary only). n = {jc['n']} ({jc['unscored']} unscored: judge unavailable), "
            f"Cohen's kappa = **{jc['kappa']}** (target {jc['target']}), "
            f"raw agreement {jc['agreement']}, human-supported share {jc['human_supported_share']}.",
            "",
            "| Languages | n | kappa | agreement |",
            "|---|---|---|---|",
            *(f"| {k} | {v['n']} | {v['kappa']} | {v['agreement']} |" for k, v in jc["by_language"].items()),
        ]
    else:
        lines += [
            "",
            "Judge calibration: no gold labels yet (`make judge-label-export`, label, `make judge-label-import`).",
        ]
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--n", type=int, default=120)
    i = sub.add_parser("import")
    i.add_argument("file", type=Path)
    i.add_argument("--annotator", required=True)
    i.add_argument("--name", required=True)
    r = sub.add_parser("run")
    r.add_argument("--name", default="baseline")
    r.add_argument("--gold", type=Path, default=None)
    a = p.parse_args()
    if a.cmd == "export":
        export(a.n)
    elif a.cmd == "import":
        import_labels(a.file, a.annotator, a.name)
    else:
        gold = a.gold or next(iter(sorted(GOLD_DIR.glob("gold_*.jsonl"))), None)
        run(a.name, gold)
    return 0


if __name__ == "__main__":
    sys.exit(main())
