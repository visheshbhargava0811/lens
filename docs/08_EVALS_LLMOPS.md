# 08 Evals and LLM Ops

The loop: **trace, eval, observe, diagnose, gate, release, feedback.** Build the eval datasets before optimizing anything. Without them, fine-tuning or retrieval changes are guesses.

## Loop stages

| Stage | Implementation |
|---|---|
| Trace | One LangSmith trace per Ask and per story pipeline run. Guards are named child runs. Tags: `lang`, `intent`, `topic`, `graph`, `prompt_version`, model versions |
| Eval | Deterministic checks first, LLM judges second, on LangSmith datasets with `evaluate()` |
| Observe | Tokens, latency p50 and p95, cost per query, abstain rate, guard block rate, queue lag, ingest lag |
| Diagnose | Filter failing traces, find the failing stage: clustering, retrieval, rerank, synthesis, or a guard |
| Gate | CI runs eval suites and fails on regression against thresholds |
| Release | Prompt versions, model config, tool changes, and RAG parameters versioned together. Staging, then canary, then prod |
| Feedback | Failed traces and guard blocks go to an annotation queue, then get promoted into datasets |

## Datasets (`data/evals/`, mirrored as LangSmith datasets)

| Dataset | Size target | Contents |
|---|---|---|
| `clustering` | 100+ labeled stories | 30+ cross-lingual, 20+ hard negatives, 10+ developing stories |
| `retrieval` | 150+ queries | EN, HI, Hinglish. Entity-heavy, paraphrase, cross-lingual, false-premise, very recent, no-answer |
| `stance` | 200 to 300 articles | Multiple annotators, masked outlet names, includes `not_applicable` and hard cases from both directions |
| `golden_answers` | 50+ queries | Known-good cited answers or acceptance criteria |
| `adversarial` | 100+ cases | Injection in query and in article text, loaded questions, communal-tension stories, victim-identity, PII, translation drift |
| `factcheck_match` | 100+ claim pairs | same_claim, related, different |
| `judge_calibration` | 100 to 200 items | Human labels for each judged criterion |

File format: JSONL with `id`, `inputs`, `reference_outputs`, `tags` (language, topic, difficulty), `annotator_ids`, `created_at`.

Claude Code builds loaders, the labeling export script, and eval runners. **Humans produce labels.** Bootstrap draft labels with a strong LLM, then have humans correct at least a sample and record agreement.

## Metrics by layer

| Layer | Metrics |
|---|---|
| Chunking | Retrieval metrics per strategy, quote-match rate |
| Retrieval | Recall@k, MRR, nDCG, per-outlet coverage in top-k |
| Retrieval ablation | BM25, dense, sparse, hybrid, hybrid + ColBERT, hybrid + cross-encoder (`docs/05`) |
| Clustering | B-cubed P/R/F1, ARI, V-measure, cross-lingual pair accuracy, verifier call rate |
| Stance | Macro-F1 per language, confusion matrix, **masked-source consistency**, **left-right symmetry of error rates** |
| Generation | Faithfulness, citation precision and recall, **deterministic quote-match rate**, answer relevance |
| News-specific | Attribution correctness, neutrality and tone, false-premise handling, coverage completeness (did the answer include the outlets that reported it) |
| Fact-check matching | Precision and recall of `same_claim` |
| Guardrails | Block rate on the adversarial set, false-positive rate on benign queries |
| System | p50 and p95 latency, cost per query, abstain rate |

## CI gate

Thresholds are **starting values**. Set the real ones after the first baseline, then only ratchet upward. Record them in `config/eval_gates.yaml`.

```yaml
gates:
  quote_match_rate:        { min: 1.00 }        # deterministic, no exceptions
  citation_presence:       { min: 1.00 }
  faithfulness_judge:      { min: 0.95 }
  adversarial_pass_rate:   { min: 0.95 }
  benign_false_block_rate: { max: 0.03 }
  retrieval_recall_at_10:  { min_delta_vs_baseline: -0.02 }
  clustering_bcubed_f1:    { min_delta_vs_baseline: -0.02 }
  stance_masked_consistency: { min: 0.95 }
  p95_ask_latency_s:       { max: 15 }
```

`make eval` runs all suites and writes `reports/eval_<date>.md`. CI fails on any gate violation. Include a test that a deliberately broken prompt fails the gate.

## LLM as a judge

Two uses with different constraints.

| Where | Job | Constraint |
|---|---|---|
| Runtime verifier | Each cited chunk supports its sentence | Fast and cheap. Runs after deterministic checks. Max 2 retries |
| Offline and online evals | Faithfulness, neutrality, premise handling, coverage completeness | Can be slower and stronger |

Rules:
- **Different model family than the generator.**
- **Narrow, mostly binary rubric.** "Is this sentence supported by the cited text, yes or no", not a 1 to 10 quality score.
- **Reasoning before verdict** in the schema.
- **Calibrate against humans.** Measure agreement (Cohen's kappa) on `judge_calibration`. Only trust the judge for criteria where agreement is high. Starting target: kappa at or above 0.6.
- **Report agreement per language** (English, Hindi, regional). Judges weaken on lower-resource Indic languages.
- **Mask outlet names** when judging stance or neutrality.
- **Pairwise comparisons swap positions** to cancel order bias.

```python
class FaithfulnessVerdict(BaseModel):
    reasoning: str
    unsupported_sentences: list[str]
    verdict: Literal["pass", "fail"]
```

## LangSmith setup

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=...
export LANGSMITH_PROJECT=lens-dev
```

- Wrap retriever internals (hybrid search, rerank, balancing) in `@traceable` so each stage's output is inspectable.
- Guards are tagged runs with feedback scores (`docs/07`).
- Separate projects for `dev`, `staging`, `prod`.
- **Mask PII before it reaches traces** (`G-OUT-05`) and set a retention policy. This applies to datasets too.

Experiment pattern:

```python
from langsmith import evaluate

def quote_match_rate(outputs: dict, reference_outputs: dict) -> dict:
    ok = sum(q in outputs["article_texts"][a] for q, a in outputs["quotes"])
    return {"key": "quote_match", "score": ok / max(1, len(outputs["quotes"]))}

def faithfulness(outputs: dict) -> dict:
    v = judge.with_structured_output(FaithfulnessVerdict).invoke(build_prompt(outputs))
    return {"key": "faithfulness", "score": v.verdict == "pass", "comment": v.reasoning}

evaluate(
    lambda inputs: run_query_graph(inputs["query"]),
    data="golden-queries-v1",
    evaluators=[quote_match_rate, faithfulness],
    experiment_prefix="hybrid-colbert-semantic",
)
```

Verify evaluator signatures against current LangSmith docs before use.

## Online evals and review loop

- Attach online evaluators to a **sample** of production traces (faithfulness, neutrality, premise handling). Alert on drops.
- Every guard failure and low-scoring trace goes to an **annotation queue**.
- Reviewed failures are promoted into datasets so the eval set grows from real problems.
- Weekly review: top failing guards, abstain reasons, slowest stages, cost outliers.

## Release process

1. Change a prompt, model, or retrieval parameter on a branch.
2. `make eval` compares against the last baseline. Attach the report to the PR.
3. CI gate must pass.
4. Deploy to staging, run the adversarial set against staging.
5. Canary a small share of traffic. Watch online evals and guard rates.
6. Promote. Tag the versions (prompt, model tier map, retrieval config) together.
7. Rollback = re-pin previous versions. Must be one command.

## Fine-tuning policy (only after evals show a gap)

Order of candidates:
1. Cross-lingual embedding fine-tune (contrastive pairs from verified clusters)
2. Stance classifier (MuRIL, IndicBERT, or XLM-R, on labeled Indian news)
3. Distilled small models for triage and claim extraction (LoRA, labels from a strong model, human-corrected sample)
4. Hinglish query understanding, only if the baseline fails

Never fine-tune the synthesis model. Never use fine-tuning to fix hallucination. That is a retrieval and verification problem.

## Implementation status (Phase 7, ADR-0039)

| Piece | Where | Command |
|---|---|---|
| Suite runner, dated report | `lens.evals.run_all`, `reports/eval/*.json`, `reports/eval_<date>.md` | `make eval [SUITES=a,b] [FORCE=1]` |
| Gate (CI step) | `lens.ops.gate`, `config/eval_gates.yaml` | `make eval-gate` |
| Baseline for delta gates | `reports/eval/baseline.json` | `make eval-baseline` |
| What a report measured | `lens.ops.fingerprint.DEPS` | |
| LangSmith datasets | `lens.ops.datasets` (`lens-<suite>-<file>`) | `make eval-sync` |
| Annotation queue | `lens.ops.annotation` (`lens-guard-failures`), swept by the pipeline worker | `make eval-promote` |
| Online evaluators | `lens.ops.online_eval`, `eval_gates.yaml: online_eval` | pipeline worker, every pass |
| Release and rollback | `lens.ops.release`, `releases/`, tags `release/<name>` | `make release NAME=`, `make rollback TO=`, `make releases` |

Pending: `faithfulness_judge` (needs the owner-labeled `golden_answers` set), `stance_masked_consistency` (no stance model, ADR-0020), staging and canary traffic (Phase 10).

