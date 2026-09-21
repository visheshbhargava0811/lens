# 13 India sources, ratings, and stance rubric

**Rule for Claude Code: do not fill in feed URLs, ownership, ratings, or licensing terms from memory.** Every such field needs an evidence URL. Unknown values stay `TO_VERIFY` or null, and the UI shows "Not rated". If a value cannot be verified, stop and ask the human.

## Source selection criteria (publish these on the methodology page)

Choose sources by **written, published criteria**, not by taste. Suggested criteria:

- Regular original reporting on national or state news
- Identifiable ownership and editorial contact
- Machine-readable access (RSS, sitemap, API) that permits our use, or a license
- Coverage across languages and regions
- **Deliberate spread across stance, ownership types, and scale.** Include national and regional outlets, large groups and independents, legacy and digital-native, and wire services

Record the reason each source was included in the seed file. Review the list on a schedule and publish changes.

## Launch languages

Start with **English and Hindi**, plus **one regional language** chosen after the clustering baseline (decision recorded in `docs/DECISIONS.md`). Candidates to consider: Tamil, Bengali, Marathi, Telugu, Malayalam. Choose by source availability, feed quality, and model quality measured in Phase 2 to 5.

## Candidate outlets to evaluate (not a list of recommendations)

These are names to research against the criteria above. Inclusion and any rating come only from verified evidence.

| Group | Candidates to research |
|---|---|
| English national dailies and digital | The Hindu, Times of India, Hindustan Times, The Indian Express, The Telegraph (India), Deccan Herald, Business Standard, Mint, The Economic Times, Scroll.in, The Wire, ThePrint, Firstpost, The News Minute |
| English and Hindi broadcast and digital | NDTV, India Today, Times Now, Republic, News18, ABP News, Zee News, DD News |
| Hindi press | Dainik Bhaskar, Dainik Jagran, Amar Ujala, Navbharat Times, Hindustan (Hindi), Live Hindustan |
| Regional-language press | Eenadu, Sakshi, Malayala Manorama, Mathrubhumi, Anandabazar Patrika, Lokmat, Sakal, Dinamalar, Dina Thanthi, Gujarat Samachar |
| Wires and agencies | PTI, ANI, IANS, plus Reuters and AP for international context |
| International with India coverage | BBC, Al Jazeera, Reuters, The Guardian |
| Fact-checkers (also a separate ingest) | BOOM, Alt News, Factly, PTI Fact Check, Vishvas News, Newschecker, The Quint WebQoof, India Today Fact Check |

Some of these may block automated access, have no feed, or restrict reuse. Record what you actually find.

## Seed file: `data/sources/sources.seed.yaml`

```yaml
# Every field marked TO_VERIFY must be filled from evidence, with evidence_url.
- slug: example-outlet
  name: Example Outlet
  homepage_url: TO_VERIFY
  language_codes: [en]
  region: national            # national or state code
  is_wire: false
  is_fact_checker: false
  license_mode: snippet_only  # default until a license or terms review says otherwise
  image_policy: none          # default
  robots_ok: TO_VERIFY
  feed_urls:
    - { url: TO_VERIFY, kind: rss, topic: null }
  inclusion_reason: "Which criterion this source satisfies"
  evidence:
    feed_evidence_url: TO_VERIFY
    terms_evidence_url: TO_VERIFY
  ownership:
    - owner_name: TO_VERIFY
      owner_type: TO_VERIFY
      parent_group: TO_VERIFY
      evidence_url: TO_VERIFY
      confidence: low
  ratings: []                 # entries need rater, value, method_url, retrieved_at, confidence
```

A seed loader test rejects any rating or ownership entry without an evidence or method URL.

## Ratings approach

Do not invent ratings. Use a layered approach and show provenance for each layer.

1. **Third-party factuality ratings where they exist** (for example international raters, and any Indian equivalents). Store rater name, value, method URL, retrieval date. Show as "According to {rater}". Where raters disagree, show both.
2. **Ownership** from public records, company filings, and the outlet's own disclosures, each with an evidence URL and confidence. Show "Unknown" honestly.
3. **Internal ratings (later, optional):** only with a published rubric, at least three independent human raters, measured agreement, an appeals process, and a public changelog. Legal review before publishing any rating of a named outlet.
4. **Per-story stance** (article level) is the primary signal on story cards. Outlet-level stance history is secondary, appears only on the source page as a distribution, and always with methodology.

## Stance rubric (goes into `agents/skills/stance_rubric.md`, versioned)

Stance is about **how a specific article frames a specific government or opposition angle**, not about the outlet's reputation and not about whether the article is factually right.

Fields: `stance_target` (`central_govt`, `state_govt`, `opposition`, `none`), `stance` (`critical`, `balanced`, `supportive`, `not_applicable`), `stance_confidence`.

| Label | Definition | Signals |
|---|---|---|
| `critical` | Foregrounds failures, allegations, costs, or opposing accounts about the target | Lead and headline emphasize shortcomings, critics' quotes lead, official claims are questioned or contextualized with counter-evidence |
| `supportive` | Foregrounds achievements or the official account with little scrutiny | Lead and headline emphasize successes, official statements lead and are not tested, critics absent or brief |
| `balanced` | Presents official and critical accounts with attribution and comparable weight | Both sides quoted, neutral verbs, no loaded adjectives |
| `not_applicable` | No government or opposition angle | Sports, weather, most business and entertainment |

Rules for annotators and the model:
- Judge the **article**, not the outlet. Outlet name is masked in prompts and annotation tools.
- **State versus central matters.** Set `stance_target` to the government the coverage is actually about. A story critical of a state government can be supportive of the central government, and the reverse.
- `opposition` target means coverage about opposition parties or leaders. Apply the same definitions symmetrically.
- Reporting an allegation with attribution is not `critical`. Endorsing it in the outlet's own voice is.
- Low confidence is fine and expected. It becomes `unclassified` in stats.
- Wire copy is scored once, as one source.
- Symmetry test: swap the government and opposition in a test article. The label logic must mirror.

Annotation requirements for the stance eval set: 200 to 300 articles, at least 3 annotators, outlet names masked, measured agreement (Cohen's or Fleiss' kappa), adjudicated disagreements, and coverage of English, Hindi, and the launch regional language, with hard cases in both directions.

## Fact-check sources

- Use structured data where available (ClaimReview markup, Google Fact Check Tools API) and the fact-checkers' own feeds where their terms allow.
- Display always attributes the fact-checker, shows their rating and link, and never presents the match as our verdict.
- Normalize ratings into `true | false | misleading | unproven | other` while keeping `rating_original`.

## Legal and licensing notes (not legal advice)

- Wire agencies and many publishers license content. Some have litigated over AI use. Default to headlines, snippets, and links until a license or explicit terms allow more.
- Images: default to text tiles. Hotlinked thumbnails only for sources where terms allow, with attribution, and never re-hosted.
- Republishing translated or summarized content of licensed work needs review.
- Publishing ratings and ownership of named outlets needs legal review and a corrections process.
- Election periods, sub judice matters, communal tension, victims of sexual offences, and minors need special handling (`docs/07`).
