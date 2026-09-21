# 10 UI spec

Goal: a UI that feels familiar to anyone who has used Ground News, adapted for India. Same core patterns: dense story feed, a coverage bar on every story, blindspots, per-story source lists grouped by stance, ownership and factuality context. Different: multilingual first, India stance axis, an Ask interface, and no US left/right framing.

**Replicate patterns, not assets.** Do not copy Ground News's logo, name, copy, icons, illustrations, or exact colors. Check their current app for layout reference, since it changes.

Read `docs/09_API_SPEC.md` for data shapes. Build with MSW fixtures first.

## Design direction

The brief pins the direction: clean, information-dense, light, editorial-neutral. Follow it. Within that:

- **Spend boldness in one place: the coverage bar and story card.** Everything else stays quiet and disciplined.
- Sentence case everywhere. No ALL-CAPS labels, no eyebrow label above every heading, no arrows appended to links, no meta strings joined with middle dots. Meta info is separate labeled elements.
- Structure encodes information. Borders, dividers, and chips appear only where they carry meaning (a stance chip means something, a decorative divider does not).
- Motion only in response to user action (expanding, switching tabs, opening the Ask panel). No entrance animations on page load. Respect `prefers-reduced-motion`.
- Cards are not identical: hero, standard, and compact variants have different hierarchy. Use one radius scale, not one radius everywhere.

## Design tokens

Define as CSS variables in `frontend/src/app/tokens.css`, mapped into Tailwind config. Dark mode tokens mirror them.

### Color (light)

| Token | Value | Use |
|---|---|---|
| `--paper` | `#FFFFFF` | Page background |
| `--surface` | `#F5F6F8` | Panels, inputs, skeletons |
| `--line` | `#E3E5EA` | Dividers where they carry meaning |
| `--ink` | `#16181D` | Primary text, primary buttons |
| `--ink-muted` | `#5B6270` | Secondary text (checked for 4.5:1 on paper) |
| `--link` | `#1D4ED8` | Links, focus ring base |
| `--stance-critical` | `#6A4C9C` | Critical of government |
| `--stance-balanced` | `#8A919E` | Balanced |
| `--stance-supportive` | `#0E7C86` | Supportive of government |
| `--stance-unclassified` | `#D5D8DE` | Unclassified (hatched) |
| `--flag-bg` / `--flag-ink` | `#FFF4D6` / `#6B4A00` | Blindspot and limitation notes |

**Stance colors are deliberately not red, green, saffron, or sky blue.** Those colors are strongly tied to Indian parties. Violet and teal are colorblind-safe with each other and neutral. Every segment also has a **pattern** (critical: diagonal hatch, supportive: dots, balanced: solid, unclassified: light hatch) so color is never the only signal. Keep the palette in tokens so it can be swapped after user testing.

Factuality uses a **single-hue ink scale** (high `#1F2937`, mixed `#6B7280`, low `#D1D5DB`) with text labels, not traffic-light colors.

### Type

- **Family:** Noto Sans (Latin) with matching Noto Sans script families for Devanagari, Bengali, Tamil, Telugu, Gujarati, Kannada, Malayalam, Gurmukhi, Odia, loaded with `next/font` and `unicode-range` subsetting. Reason: consistent metrics across scripts and full Indic coverage.
- Weights: 400 body, 500 UI labels, 700 headlines.
- Scale (px): 12, 14, 16, 18, 20, 24, 30, 40. Body 16.
- Line height: Latin body 1.5, headlines 1.25. **Indic scripts get +0.1** (body 1.6, headlines 1.35) because of taller glyphs and matras.
- Line length: max 68ch for reading text.
- Every element with source-language text carries a correct `lang` attribute (`lang="hi"`, `lang="ta"`, and so on) so fonts, hyphenation, and screen readers behave.
- Headlines of source articles always render in their original script.

### Space, radius, elevation

- 4 px base unit. Spacing scale 4, 8, 12, 16, 24, 32, 48.
- Radius scale: chips and bar 999, inputs and buttons 8, cards 12, modals 16.
- Elevation: none by default. Use borders only where structure demands it. One subtle shadow for the sticky Ask input and popovers.

## Global layout

Grid: 12 columns, max content width 1200 px, gutters 24 px desktop, 16 px mobile. **Mobile first**: most users are on phones, often on limited bandwidth.

### Header (desktop)

```
+---------------------------------------------------------------------------------+
| Lens   Home   For you   Blindspot   Local   Ask        [ Search ]   EN | हिं   Sign in |
+---------------------------------------------------------------------------------+
| Top   Politics   Business   World   Sports   Tech   Health   Science   Entertainment |
+---------------------------------------------------------------------------------+
```

- Sticky header. Topic chips scroll horizontally, active chip is filled with `--ink`.
- Language switcher changes UI language and summary language, not source article language.
- Mobile: header collapses to logo, search icon, language icon. **Bottom tab bar** with Home, Blindspot, Ask, Local, Profile.

## Pages

### 1. Home feed (`/`)

```
+------------------------------------------------------------+---------------------+
| HERO STORY                                                 | Blindspot           |
| [image or text tile]                                       |  - compact card     |
| Headline (30 px, 700)                                      |  - compact card     |
| [coverage bar, 12 px]  legend                              |  - compact card     |
| 42 sources   Updated 2 h ago   Hindi 18  English 20  Other 4 |                     |
| Two-line summary preview                                   | Fact-checks today   |
+---------------------------+--------------------------------+  - item             |
| Standard card             | Standard card                  |  - item             |
+---------------------------+--------------------------------+---------------------+
| Standard card             | Standard card                  |  Topics to follow   |
+---------------------------+--------------------------------+---------------------+
```

- Hero: highest-ranked developing story. Others in a 2-column grid on desktop, single column on mobile.
- Right rail (desktop only): blindspots, fact-checks today, topics. Moves below the feed on mobile as horizontally scrolling sections.
- Infinite scroll with cursor pagination and a visible "Load more" fallback.
- Ranking is coverage breadth plus recency. Personalization may re-rank by followed topics but **must not filter stances or outlets**.

### 2. Story page (`/story/[slug]`)

```
+------------------------------------------------------------+---------------------+
| Headline (30 px)                                           | Coverage            |
| Updated 2 h ago   Developing                               | [bar 14 px]         |
|                                                            | Critical 43%        |
| Summary (verified)                                         | Balanced 29%        |
|  Sentence one [1][2]                                       | Supportive 21%      |
|  Sentence two [3]                                          | Unclassified 7%     |
|                                                            | Confidence: medium  |
| Where outlets agree          | Where they differ           | How we calculate this |
|  - sentence [n]              |  - sentence [n]             |                     |
|                                                            | Factuality          |
| Fact-checks                                                |  High 30 Mixed 8 ...|
|  Claim, fact-checker, rating, link                         |                     |
|                                                            | Ownership           |
| Sources                                                    |  Group A: 3 sources |
|  [All] [Critical] [Balanced] [Supportive] [Unclassified]   |  Unknown: 12        |
|  Language: [All] [English] [हिन्दी] [தமிழ்] ...             |                     |
|  ArticleRow                                                | Ask about this story|
|  ArticleRow                                                | [ input ]           |
|  ...                                                       |                     |
| Timeline                                                   |                     |
+------------------------------------------------------------+---------------------+
```

- Left column reading order: headline, summary, agreements and differences, fact-checks, sources, timeline.
- Right rail on desktop is sticky. On mobile it becomes: coverage card directly under the headline, then the rest in order, with Ask as a floating button.
- Citation chips `[n]` are focusable buttons. Activating one scrolls to and highlights the matching ArticleRow and shows the cited passage in a popover (only if `license_mode` allows displaying the text, else show headline and link).
- Show `limitations` in a flag-styled note (for example "Based on headlines and summaries for 14 of 42 sources").
- When coverage is limited (fewer than `min_sources`), replace the bar with "Limited coverage: only 2 sources so far" and still list them.

### 3. Blindspot (`/blindspot`)

Two tabs: **By stance** and **By language**.

- Each card is a StoryCard with a stronger bar and a flag chip in plain language, for example "Mostly covered by outlets critical of the government" or "Covered in Hindi, little in English".
- Copy is neutral. No implication that either group is wrong for covering or not covering.
- Explain the feature in one sentence at the top and link to the methodology.

### 4. Ask (`/ask` and the in-story panel)

```
+-------------------------------------------------------------+
| [ Ask about any story, in English, Hindi, or Hinglish ]  [>] |
+-------------------------------------------------------------+
| status: Searching coverage...                                |
|                                                              |
| Answer card                                                  |
|  Summary sentences with [n] chips                            |
|  Coverage: mini bar + counts (from data, not the model)      |
|  Where outlets agree / differ                                |
|  Premises addressed: "No source reports that ..."            |
|  Fact-checks                                                 |
|  Limitations                                                 |
|  Sources used: list with language and stance                 |
|  Follow-up suggestions (max 3)                               |
+-------------------------------------------------------------+
```

- Show `status` events as a single updating line, not a chat of intermediate messages.
- If the question contained a loaded premise, show a small note above the answer: "We searched for a neutral version of your question" with the neutral query visible and editable.
- Abstain state: plain explanation, closest stories as cards, no fluent guess.
- Sensitive-topic state (`sensitive_topic_under_review`): show the reviewed summary if one exists, else say it is under review.
- Answers are not persisted in the UI feed. A session history list is available only when the user is signed in and has consented (Phase 9).

### 5. Source page (`/source/[slug]`)

Name, language, region, ownership (with evidence link), third-party ratings each showing rater, value, method link, date. Recent stories from this source with their per-story stance chips. **No single permanent bias label.** If stance history is shown, present it as a distribution over stories with the methodology link.

### 6. Topic and search pages

Same feed layout filtered by topic or query. Search returns stories first, then sources. Empty results show what to try (fewer words, another language) and a link to Ask.

### 7. Methodology (`/methodology`)

Anchored sections: coverage bar, stance, factuality, ownership, blindspots, how summaries are verified, languages, limits, corrections. Includes rater list, rubric, validation results, changelog, and the feedback form. Every bar and rating in the app links here.

### 8. Preferences (`/me`) (Phase 9)

Language, followed topics and regions, summary length, audio. A "What we store" view listing every stored fact with edit and delete, plus "Delete everything". No political preference field exists.

## Components

| Component | Behavior |
|---|---|
| `CoverageBar` | Props: `buckets`, `unclassified`, `size` (`sm` 8 px feed, `md` 12 px hero, `lg` 14 px story), `confidence`. Segments proportional by distinct sources. Patterns plus colors. Hover or focus shows tooltip "18 sources, 43%, critical of the government". Renders `role="img"` with a full text alternative ("Coverage by 42 sources: 43 percent critical of the government, 29 percent balanced, 21 percent supportive, 7 percent unclassified. Confidence medium."). Below `min_sources`, renders the Limited coverage state instead. Always followed by a "How this is calculated" link |
| `StanceLegend` | Swatch plus pattern plus label plus count. Labels: "Critical of the government", "Balanced", "Supportive of the government", "Unclassified". For `stance_target` other than central government, the label names the target (for example "state government") |
| `StoryCard` | Variants `hero`, `standard`, `compact`. Contains headline (original language), optional image or text tile, CoverageBar, counts, updated time, language mix, optional flag chip. Whole card is one link. Only the bar and flag chip are interactive inside |
| `SourceCount` | "42 sources" with a hover breakdown by language |
| `FlagChip` | Blindspot and limitation notes in `--flag` colors, with icon and text |
| `FactualityMeter` | Three-segment ink-scale bar plus labels and counts. Shows "Not rated" count. Tooltip names the rater |
| `OwnershipTags` | Grouped by parent owner with evidence link, "Unknown" bucket shown honestly |
| `ArticleRow` | Source name and language tag, original-language headline, time, stance chip for this article, source factuality chip, ownership chip, "Depth" note if `analysis_depth` is not full, external "Read at {source}" link opening in a new tab with `rel="noopener noreferrer"`. Syndicated rows show "Also carried by N outlets" |
| `CitationChip` | `[n]` button. Opens popover with source, headline, cited passage if displayable, and link |
| `SummaryBlock` | Renders cited sentences. Shows "Verified against sources" indicator only when `verified` is true |
| `Timeline` | Vertical list of coverage events (first report, major updates, fact-check published). Collapsible on mobile |
| `AskBox` | Single input, language auto-detect, submit on Enter, disabled while running with a Stop button |
| `AnswerCard` | See Ask page. Sections collapse on mobile except summary |
| `LanguageSwitcher` | UI language and summary language. Persisted locally, and to preferences when signed in |
| `MethodologyLink` | Always present near any bar or rating |
| `EmptyState`, `ErrorState`, `AbstainState` | See copy below |
| `Skeleton` | Shape-matched skeletons for cards, bars, and answer cards |

## Copy guidelines

Write from the reader's perspective, in plain words. Active voice. Sentence case. A button says exactly what it does, and the toast that follows uses the same word.

| Situation | Copy |
|---|---|
| Limited coverage | "Limited coverage: only 2 sources so far. A coverage split needs at least 4." |
| Unrated source | "Not rated" |
| Abstain | "There isn't enough reliable coverage to answer this yet. Here are the closest stories we found." |
| Out of scope | "Lens covers news reporting. Try asking what outlets have reported about a story." |
| Under review | "This topic is sensitive, so we only show reviewed summaries. This one is still being reviewed." |
| Load error | "Couldn't load this story. Check your connection and try again." with a "Try again" button |
| Rate limit | "You've asked a lot of questions quickly. Try again in 12 seconds." |
| Stale data | "Latest report we found is from 3 hours ago." |
| Depth note | "Based on headline and summary." |
| Premise note | "We searched for a neutral version of your question." |
| Feedback button | "Report a problem" then toast "Report sent" |

Errors never apologize and never stay vague: say what happened and what to do.

## States checklist

Every data-driven component has: loading (skeleton), empty, error, limited-data, and stale states, each tested.

## Responsive behavior

| Breakpoint | Layout |
|---|---|
| under 640 px | Single column, bottom tab bar, coverage card under headline, Ask as floating button |
| 640 to 1024 px | Single column feed with 2-column grid for standard cards, right rail below content |
| over 1024 px | Full layout with sticky right rail |

## Performance (low-bandwidth users matter)

- Server-render feed and story pages, ISR with revalidate on story update
- No images by default (text tiles). Where thumbnails are allowed, use `next/image` with lazy loading and a fixed aspect ratio, and never mirror or re-host images
- Language-subsetted fonts, `font-display: swap`, load only scripts present on the page
- JavaScript budget: initial route under 150 KB gzipped (starting target), CoverageBar is pure SVG or CSS with no chart library
- Optional "Low data mode" toggle that hides images and defers the right rail
- Lighthouse mobile performance at or above 85 on Home and Story (starting target)

## Accessibility

- WCAG 2.2 AA. Contrast checked for all tokens in light and dark
- Bar segments carry patterns, not only color
- Full keyboard support. Visible focus ring using `--link`, 2 px with offset
- Semantic headings, landmarks, skip link
- Citation chips, tooltips, and popovers are keyboard and screen-reader operable
- `lang` on all mixed-language content
- `prefers-reduced-motion` respected. `prefers-color-scheme` supported with a manual override
- Test with axe in Playwright, no serious or critical violations

## Internationalization

- `next-intl`. UI strings in English and Hindi at launch, structure ready for more languages
- Never hard-code strings. Number and date formatting via `Intl` with the active locale. Consider Indian digit grouping (lakh, crore) for numbers in copy
- Right-to-left is out of scope for now, but avoid layout choices that block it later (use logical CSS properties)
- Translated summaries are labeled "Translated from {language}" and pass `G-OUT-06`

## Analytics and privacy

- Minimal, privacy-respecting events: story opened, source clicked, Ask submitted (no query text), abstain shown, feedback sent
- No third-party trackers in MVP
- Cookie and consent handling per DPDP requirements before any non-essential storage

## Frontend structure

```
frontend/src/
├── app/
│   ├── (feed)/page.tsx
│   ├── story/[slug]/page.tsx
│   ├── blindspot/page.tsx
│   ├── ask/page.tsx
│   ├── source/[slug]/page.tsx
│   ├── topic/[slug]/page.tsx
│   ├── search/page.tsx
│   ├── methodology/page.tsx
│   ├── me/page.tsx
│   ├── tokens.css
│   └── layout.tsx
├── components/
│   ├── coverage/CoverageBar.tsx
│   ├── coverage/StanceLegend.tsx
│   ├── story/StoryCard.tsx
│   ├── story/ArticleRow.tsx
│   ├── story/SummaryBlock.tsx
│   ├── ask/AskBox.tsx
│   ├── ask/AnswerCard.tsx
│   └── ui/                   # shadcn primitives, restyled to tokens
├── lib/
│   ├── api/                  # generated client
│   ├── i18n/
│   └── format.ts
├── mocks/                    # MSW handlers and fixtures from docs/09
└── messages/{en,hi}.json
```

## UI acceptance checklist

- [ ] Home, Story, Blindspot, Ask, Source, Methodology render from fixtures at 375, 768, and 1280 px widths
- [ ] CoverageBar passes unit tests for rounding, unclassified share, and limited-coverage state, and has a screen-reader alternative
- [ ] Hindi headlines render correctly with proper line height and `lang`
- [ ] No stance figure appears without confidence and a methodology link (contract test)
- [ ] Citation chips resolve to the right ArticleRow and popover
- [ ] All states (loading, empty, error, limited, stale, abstain) implemented
- [ ] axe clean, keyboard-only walkthrough passes, reduced motion respected
- [ ] Lighthouse mobile targets met
- [ ] Visual review against the wireframes above, with a short note on any deviation
