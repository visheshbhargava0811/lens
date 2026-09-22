# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Two audiences, served equally (owner decision, 2026-09-22):

- **Everyday reader on a phone.** English or Hindi. Skims the feed, opens a few stories a day, wants to know what happened and who is reporting what.
- **Power reader on desktop.** Students, researchers, journalists. Compares framings and claims across many outlets and languages at once, so density matters.

Also served: regional-language readers ("is my press covering something English media ignores?") and skeptical readers ("has this claim been fact-checked?"). See `docs/01_PRODUCT.md`.

## Product Purpose

One story, many outlets, many languages. Lens clusters coverage of the same event across Indian outlets in English, Hindi and regional languages, shows how each outlet frames it, links claims to Indian fact-checkers, and answers questions with cited, source-balanced answers. Success is a reader who understands the range of coverage and clicks through to the outlets.

## Positioning

The Ground News pattern (story feed, coverage bar, blindspots, per-story source lists), adapted for India:

- The stance axis is the article's stance toward the government in question (critical / balanced / supportive), not left/right.
- Cross-lingual clustering puts Hindi and regional outlets in the same story as English ones.
- Language blindspots: stories covered in one language group but not another.
- Claim-level fact-check links, plus an Ask interface where every sentence is cited.

## Operating Context

- Anonymous browsing; optional login later (Phase 9).
- UI in English and Hindi (next-intl); one regional language after the baseline.
- Content is headlines, snippets and links only. Tiles are text-only by default; thumbnails only for sources with `image_policy=hotlink`.
- Frontend is built against `docs/09_API_SPEC.md` with MSW fixtures. Page specs are in `docs/10_UI_SPEC.md`.

## Capabilities and Constraints

- Stack: Next.js 16 App Router, TypeScript, Tailwind, shadcn/ui (base-ui), TanStack Query, next-intl.
- Coverage bar shown only with at least 4 distinct sources, otherwise "Limited coverage". It always shows the unclassified share, a confidence label and a methodology link.
- No stance, bias or factuality figure without a confidence level and methodology link.
- Unknown outlet facts show as "Not rated". Nothing about outlets is filled in from memory.
- Personalization never changes which outlets appear in a coverage comparison. No political profiling.
- Text is stored and shown in its original script.

## Brand Commitments

- Name: **Lens** (placeholder). A simple typographic wordmark; no invented logo.
- Tone reference: Ground News web UI/UX, kept close in tone and density at the owner's request. Replicate interaction patterns only, never Ground News branding, copy, logos or assets (`docs/01_PRODUCT.md`).

## Evidence on Hand

- Fixture data only: every outlet, owner, rater and event in `frontend/src/mocks/fixtures.ts` is invented (ADR-0007). No real ratings, testimonials, users or press exist. Do not fabricate any.

## Product Principles

1. Show the spread, not a verdict. The product compares coverage; it does not issue opinions.
2. Every number carries its confidence and methodology.
3. Languages are equal citizens. Hindi and regional coverage sit beside English, not below it.
4. Send readers to the outlets. Snippets and links, not a replacement for journalism.
5. Honest about gaps: "Not rated" and "Limited coverage" beat a guess.

## Accessibility & Inclusion

- WCAG AA.
- Low-end Android on slow 4G: initial route under 150 KB gzipped JS, no heavy imagery.
- Devanagari must be as legible as Latin text (proper Noto Devanagari font, generous line-height).
- Light and dark themes.
