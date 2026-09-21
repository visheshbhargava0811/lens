# 11 Memory (Phase 9, build last)

The product works without memory. It cannot work without retrieval, citations, and evals. Build memory only after Phases 0 to 8 pass.

This follows the harness / loop / memory layers / LLM Ops pattern from the reference diagram, with changes required by a news comparison product.

## Mapping from the reference diagram

| Diagram block | Here |
|---|---|
| Harness (LangGraph, LangChain, Pydantic) | Same |
| Working memory (prompt, chat history, system prompt) | LangGraph state, short session history, summarized when long |
| Loop (LLM + tools) | Bounded: retrieval retry and verifier retry only |
| End-loop guardrails | Output guards, plus input, evidence, and post-translation guards (`docs/07`) |
| Procedural memory (`skill.md`) | Versioned prompt and skill files (`docs/06`). Read-only to the agent |
| Semantic memory (durable facts, profile) | **User preferences only**, strict schema |
| Episodic memory (dated events, past chats) | Story views and Ask history per user |
| Summarizer agent (cheap model, after N chats) | Consolidation job with a fixed output schema |
| LLM Ops | `docs/08` |

## Hard rules

1. **News facts never go into memory.** They go stale and lose their citations. News knowledge lives in the article and story index and is retrieved fresh.
2. **Semantic memory stores explicit preferences only**, from the fixed enum `UserFactKey` (`docs/06`): output language, UI language, followed topics, followed regions, summary length, audio preference.
3. **Never infer or store political leaning**, stance preference, or which outlets a user tends to read. It is sensitive, it builds a filter bubble (the opposite of this product's purpose), and it is a DPDP risk.
4. **Personalization must not change which outlets or stances appear** in a coverage comparison or answer. Memory may affect output language, format, length, and feed ordering by followed topic only.
5. **Consent first.** No memory is written until the user has consented (`users.consent_at`).
6. **User control.** `/me` shows every stored fact and history item with edit and delete, plus "Delete everything". Deletion is real and cascades.
7. **Retention.** Ask history and story views expire by default after 30 days (configurable). A purge job runs nightly.
8. **The consolidation model cannot write freeform.** Its output schema is a list of `UserFact` with a fixed key enum. Anything else is discarded and logged.

## Episodic memory feature: "What changed since you last looked"

- Record `story_views(user_id, story_id, viewed_at, story_version_seen)`.
- When a user reopens a story or asks about it again, compare `story_version_seen` to the current summary version and surface a short, cited "What's new" section (new sources, new claims, new fact-checks).
- This is the concrete reason for episodic memory. It uses the same pattern as the diagram's SQL for recency plus retrieval for relevance.

## Consolidation job

- Trigger: after N new sessions for a user (start at 5), or nightly, whichever comes first.
- Model tier: `triage` (cheap).
- Input: the user's explicit settings changes and explicit statements ("reply in Hindi from now on"), not their news-reading behavior.
- Output: `list[UserFact]`. Validate, upsert into `user_preferences`, log to LangSmith.
- Never summarize what news the user read into a profile.

## Working memory

- Keep the last few turns of the session in state for follow-ups ("what did the opposition say?").
- Follow-up questions are re-neutralized and re-retrieved. Never answer a follow-up from a previous answer's text without fresh citations.
- Summarize older turns with the cheap model when the context grows. Summaries hold the question topics, not news claims.

## Tests

- Preference written without consent is rejected
- Attempt to store an out-of-enum key is rejected and logged
- Attempt to store political leaning (adversarial prompt in consolidation input) is rejected
- Two users with different stored topics get **identical** outlet sets and stance splits for the same query
- Delete-everything removes rows from `user_preferences`, `story_views`, and unlinks `ask_turns`
- Retention purge removes expired rows
- "What changed" section cites only articles newer than `story_version_seen`
