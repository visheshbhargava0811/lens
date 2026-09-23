# 07 Guardrails

Principle: **deterministic checks first, small classifiers second, LLM judge last.** Every guard has an ID, returns a `GuardResult`, is traced in LangSmith, is logged to `guard_events`, and has a failing-case test.

Risks this product carries: wrong or unattributed claims, inflammatory output, legal exposure, manipulation through ingested content, and a bias-scoring system that loses credibility if handled carelessly.

Legal items are a checklist to review with a lawyer, not legal advice.

## Guard catalog

### Input (Graph 2 entry)

| ID | Guard | Type | On fail |
|---|---|---|---|
| G-IN-01 | Scope check: off-topic, personal data lookups, propaganda requests, medical or legal advice | Classifier + rules | `block`, friendly redirect |
| G-IN-02 | Prompt-injection screening on user text | Classifier + rules | `block` or sanitize. User text is always data |
| G-IN-03 | Rate limit, per-Ask token budget, live-fetch cap | Deterministic | `block` with retry-after |
| G-IN-04 | Language-ID confidence | Deterministic | Low confidence: answer in English and say so |
| G-IN-05 | Premise neutralization recorded and later addressed | Structured output check | `retry` query understanding |

### Evidence (after retrieval)

| ID | Guard | Type | On fail |
|---|---|---|---|
| G-EV-01 | Indirect injection scrub: strip hidden HTML, zero-width text, instruction-like patterns in article text. Wrap in delimiters | Deterministic + classifier | `redact`, log source for review |
| G-EV-02 | Source allowlist | Deterministic | Drop chunk |
| G-EV-03 | Minimum evidence: fewer than N distinct sources means "limited coverage" wording and no coverage bar | Deterministic | `abstain` or limited-coverage answer |
| G-EV-04 | Freshness: attach timestamps, flag stale or developing stories | Deterministic | Add limitation note |
| G-EV-05 | Syndication dedup: wire copy counts once | Deterministic | Collapse |
| G-EV-06 | License enforcement: no full text of `snippet_only` or `link_only` sources reaches display or storage | Deterministic | Drop or truncate |

### Generation

| ID | Guard | Type | On fail |
|---|---|---|---|
| G-GEN-01 | Schema valid, every sentence has at least one `article_id` | Pydantic | `retry` (max 2) |
| G-GEN-02 | **Quote verification:** every `source_quote` appears verbatim (NFC, whitespace-normalized) in the cited article text | Deterministic | Drop claim, `retry`, or fallback |
| G-GEN-03 | **Citation faithfulness:** each cited chunk supports its sentence | NLI model or LLM judge | `retry` with unsupported sentences (max 2), then fallback |
| G-GEN-04 | Attribution discipline: contested statements attributed, single-outlet assertions not stated as fact | Rules + classifier | `retry` |
| G-GEN-05 | No editorializing, predictions, or value-laden adjectives | Tone classifier + banned-pattern list | `retry` |
| G-GEN-06 | No false balance: fact-checker rated false means show the rating, do not present as "one side's view" | Rules using fact-check matches | `retry` |
| G-GEN-07 | Abstain over guess: weak retrieval returns "not enough reliable coverage" | Deterministic thresholds | `abstain` |

### Output (India-specific)

| ID | Guard | Type | On fail |
|---|---|---|---|
| G-OUT-01 | Hate and incitement, communal amplification (Indic-capable classifier) | Classifier | `block`, `route_to_review` |
| G-OUT-02 | Victim and minor identity: no identifying details of sexual-offence victims or minors in legal cases, even if a source names them | NER + rules | `redact` |
| G-OUT-03 | Defamation caution: allegations against named individuals attributed to source, not stated as fact | Rules + classifier | `retry` |
| G-OUT-04 | Graphic violence descriptions filtered or softened in summaries and audio | Classifier | `redact` |
| G-OUT-05 | PII: Aadhaar, PAN, phone numbers, vehicle plates, emails. Applied to outputs, logs, **and traces** | Presidio + custom regex | `redact` |
| G-OUT-06 | Post-translation check: named entities, numbers, and attribution phrases survive translation | Deterministic + light check | Re-translate or fall back to source language |
| G-OUT-07 | Sensitive-topic routing: communal violence, elections in model-code period, active court matters, health scares go to precomputed and reviewed summaries, not live generation | Topic classifier + config list | `route_to_review` |

### Bias scoring

| ID | Guard | Type | On fail |
|---|---|---|---|
| G-BIAS-01 | Any bias or factuality figure shown with confidence label and methodology link | UI and API contract test | Block release |
| G-BIAS-02 | Masked-source audit: stance output must not change when outlet name, language, or region is masked | Eval | Fail CI |
| G-BIAS-03 | Symmetry audit: same prompts and thresholds for government-critical and government-supportive coverage. Compare error rates | Eval | Fail CI |

### Operations

| ID | Guard | Type | On fail |
|---|---|---|---|
| G-OPS-01 | Loop caps (2 verifier retries, 2 retrieval retries) and per-node timeouts | Graph config | Fallback |
| G-OPS-02 | Circuit breaker: LLM API failure falls back to precomputed summary or lower tier | Deterministic | Fallback |
| G-OPS-03 | Kill switch per story, per topic, and global for generation | Flag in DB | Serve precomputed only |
| G-OPS-04 | Audit trail: query, evidence ids, prompt and model versions, verifier result, guard events | Logging | Block release if missing |

## `GuardResult` and tracing

```python
from functools import wraps
from langsmith import Client, traceable
from langsmith.run_helpers import get_current_run_tree

ls = Client()

def traced_guard(guard_id: str, stage: str):
    def deco(fn):
        @traceable(name=f"guard:{guard_id}", run_type="chain", tags=["guardrail", guard_id, stage])
        @wraps(fn)
        def wrapped(state):
            res: GuardResult = fn(state)
            rt = get_current_run_tree()
            rt.add_metadata({"guard": guard_id, "passed": res.passed,
                             "action": res.action, "reason": res.reason})
            ls.create_feedback(rt.id, key=f"guard.{guard_id}",
                               score=1.0 if res.passed else 0.0, comment=res.reason)
            persist_guard_event(rt.id, guard_id, stage, res)   # -> guard_events table
            return res
        return wrapped
    return deco
```

Verify current LangSmith APIs before relying on this snippet. Tag traces with `lang`, `intent`, and `topic` so failures can be sliced (for example "Hinglish + fact_check").

## Indirect prompt injection (the biggest security risk)

Article text is untrusted. Defenses, all required:
- Delimiters and an explicit system-prompt rule (`docs/06`)
- Strip hidden text and zero-width characters
- Synthesis has **no tools**, so an injection has nothing to trigger
- Never follow URLs found in articles
- Evaluate with injection-laden fixtures in the adversarial set

## Sensitive-topic list (`config/guardrails.yaml`)

```yaml
sensitive_topics:
  - communal_violence
  - election_model_code_period
  - sub_judice_court_matter
  - sexual_offence_case
  - minor_involved
  - health_scare
  - terror_incident
route_to_review_for: all above     # precomputed + reviewed summaries only
min_sources_for_bar: 4
min_sources_for_blindspot: 6
```

## Bias-scoring practices

- Never show a bare number or label. Always confidence and methodology link.
- Prefer per-story framing over permanent outlet labels.
- Outlet-level ratings come from cited third-party raters, plus internal ratings only with multiple human raters, a published rubric, and evidence URLs.
- Provide a corrections channel and a visible changelog.
- Re-validate on a schedule. Track inter-rater agreement.

## Test requirements

- Each guard has at least one passing and one failing unit test.
- `data/evals/adversarial/` holds: loaded questions, false premises, injection-laden articles, communal-tension stories, Hinglish edge cases, PII-laden inputs, victim-identity cases, and translation-drift cases.
- Run the adversarial set on every change to prompts, models, or guards.
