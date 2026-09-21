# 01 Product

## Vision

A news product for India where a reader can see **one story, many outlets, many languages** in one place. Ground News proved the pattern: cluster coverage of the same event, show who covered it and how. This product keeps that pattern and adds what Ground News does not serve well for Indian users:

- Cross-lingual coverage (Hindi and regional-language press next to English outlets)
- A stance axis that fits India (stance toward the government in question, not US-style left/right)
- Claim-level links to Indian fact-checkers
- A conversational interface that answers "tell me about X" with cited, source-balanced answers

## Users and jobs to be done

| User | Job |
|---|---|
| Curious reader | "What actually happened, and who is reporting what?" |
| Regional-language reader | "Is my regional press covering something English media ignores, or the reverse?" |
| Student, researcher, journalist | "Show me the range of framings and the claims each outlet makes, with sources." |
| Skeptical reader | "Has this claim been fact-checked?" |

## Feature list

| ID | Feature | Priority | Notes |
|---|---|---|---|
| F-01 | Story feed of clustered stories | MVP | Home, topic pages, search |
| F-02 | Coverage bar per story | MVP | Article-level stance buckets, see below |
| F-03 | Story page: cited summary, sources grouped by stance, timeline | MVP | |
| F-04 | Source metadata: ownership, third-party factuality ratings | MVP | Provenance required (CLAUDE.md rule 7) |
| F-05 | Blindspot feed | P1 | Two kinds: stance blindspot and language blindspot |
| F-06 | Ask: chat with cited, source-balanced answers | MVP | Phase 6 |
| F-07 | Claim-level fact-check matches | P1 | Phase 8 |
| F-08 | Multilingual UI and summaries | MVP for English + Hindi | Add one regional language after baseline |
| F-09 | Audio summaries | P2 | Regional-language TTS |
| F-10 | "What changed since you last looked" | P2 | Needs episodic memory, Phase 9 |
| F-11 | Preferences: language, topics, summary length | P1 | Explicit only, never inferred |
| F-12 | Methodology page and corrections channel | MVP | Trust feature, not optional |
| F-13 | Follow topics and sources | P1 | |
| F-14 | Admin review queue and kill switch | P1 | Needed before public launch |
| F-15 | Local tab (state and city news) | P1 | State selector |

## Where this differs from Ground News

| Area | Ground News pattern | This product |
|---|---|---|
| Bias axis | Left / center / right | **Stance toward the government in question**: critical, balanced, supportive. Computed per article, per story |
| Language | English-first | Cross-lingual clustering, Hindi and regional outlets in the same story |
| Blindspot | One side barely covers a story | Also **language blindspot**: covered by regional-language press but not English national outlets, or the reverse |
| Fact-checks | Outlet-level factuality | Claim-level matches to Indian fact-checkers, plus outlet-level third-party ratings |
| Interface | Browse feed | Feed **plus** Ask: cited conversational answers |
| Ownership | Shown | Shown, with evidence URLs. India context matters because of conglomerate ownership |

Ground News's product changes over time. Check the current app before treating this table as final. **Replicate the interaction patterns, not the branding, copy, logos, or assets.**

## India adaptation details

### Stance model
Each article gets:
- `stance_target`: `central_govt` | `state_govt` | `opposition` | `none`. Which government or actor the coverage is about.
- `stance`: `critical` | `balanced` | `supportive` | `not_applicable` | `unclassified`, relative to that target.
- `stance_confidence`: `low` | `medium` | `high`.

The coverage bar aggregates **distinct sources** (after syndication dedup) by article-level stance for that story. Outlet-level history appears on the source page as secondary context, never as a permanent label on story cards.

Articles with low confidence count as `unclassified` and are shown as such.

### Blindspot types
- **Stance blindspot:** at least 70% of classified sources fall in one stance bucket and at least N sources total (starting values, tune in Phase 3).
- **Language blindspot:** a story with substantial coverage in one language group and near-zero in another (for example Hindi vs English).

### Coverage bar display rules
- Show the bar only if the story has at least `MIN_SOURCES_FOR_BAR` distinct sources (start at 4). Otherwise show "Limited coverage".
- Always show the unclassified share.
- Always show a confidence label and link to the methodology page.

## Non-goals (for now)

- Producing original journalism or editorial opinions
- Real-time breaking news alerts
- Video or podcast ingestion
- Serving as a fact-checker (we link to fact-checkers, we do not issue verdicts)
- Pretraining or full fine-tuning of large models

## MVP definition

A user on mobile can:
1. Open the feed and see clustered stories from about 15 sources in English and Hindi
2. Open a story and see a cited summary, the coverage bar, and sources grouped by stance
3. Open the methodology page and understand how the bar is computed
4. Ask a question in English or Hinglish and get a cited answer, or an honest "not enough coverage"

## Success metrics

| Metric | Why |
|---|---|
| Clustering B-cubed F1 and cross-lingual pair accuracy | Product foundation |
| Citation faithfulness and quote-match rate | Trust |
| Abstain rate on adversarial queries | Honesty |
| p95 Ask latency and cost per Ask | Viability in a price-sensitive market |
| Story page to source click-through | Are we sending readers to outlets |
| Correction requests resolved within SLA | Credibility |

## Open decisions (defaults in bold, record answers in `docs/DECISIONS.md`)

| Decision | Default |
|---|---|
| Product name | Lens (placeholder) |
| Launch languages | **English, Hindi**, then one regional language chosen after baseline |
| Positioning | Portfolio project first, real product if traction. Licensing scope follows |
| Content licensing | **Headlines, snippets, links only**. Full text only with a license |
| Images | **Text-only tiles by default**. Thumbnail hotlink only for sources with `image_policy=hotlink` |
| Auth | Anonymous browsing. Optional login for preferences (Phase 9) |
| Business model | Undecided. Do not build payments in the MVP |

## Legal and risk notes (not legal advice, review with a lawyer before public launch)

- Wire services and major outlets license content. Some Indian publishers have litigated over AI use of their content. Stay with snippets and links until licensed.
- Publishing ratings of named outlets carries reputational and legal risk. Use published methodology, multiple raters, evidence URLs, and a corrections channel.
- Content about communal tension, elections (model code of conduct), victims of sexual offences, minors, and matters before courts needs extra care. See `docs/07_GUARDRAILS.md`.
- User accounts and preference storage fall under India's DPDP Act 2023: consent, purpose limitation, deletion on request.
