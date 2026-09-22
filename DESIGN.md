---
name: Lens
description: A comparison desk for Indian news; one story, every outlet, how each frames it.
colors:
  paper: "#ecede6"
  card: "#f8f8f4"
  surface: "#e1e2da"
  line: "#cbccc2"
  ink: "#1d1e1b"
  ink-muted: "#54564e"
  strip: "#1d1e1b"
  strip-ink: "#d8d9d0"
  stance-critical: "#4a3a78"
  stance-critical-ink: "#ffffff"
  stance-balanced: "#fbfbf8"
  stance-balanced-ink: "#1d1e1b"
  stance-supportive: "#0f5c62"
  stance-supportive-ink: "#ffffff"
  stance-unclassified: "#c3c4ba"
  stance-unclassified-ink: "#1d1e1b"
  flag-bg: "#e3d9bd"
  flag-ink: "#4a3c12"
  factuality-high: "#1d1e1b"
  factuality-mixed: "#6e7066"
  factuality-low: "#c3c4ba"
typography:
  display:
    fontFamily: "Noto Sans, Noto Sans Devanagari, ui-sans-serif, system-ui, sans-serif"
    fontSize: "clamp(2.125rem, 5vw, 3rem)"
    fontWeight: 800
    lineHeight: 1.25
    letterSpacing: "-0.015em"
  headline:
    fontFamily: "Noto Sans, Noto Sans Devanagari, ui-sans-serif, system-ui, sans-serif"
    fontSize: "2.75rem"
    fontWeight: 800
    lineHeight: 1.25
    letterSpacing: "-0.015em"
  title:
    fontFamily: "Noto Sans, Noto Sans Devanagari, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 800
    lineHeight: 1.25
    letterSpacing: "-0.015em"
  section:
    fontFamily: "Noto Sans, Noto Sans Devanagari, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 800
    lineHeight: 1.25
    letterSpacing: "-0.015em"
  body:
    fontFamily: "Noto Sans, Noto Sans Devanagari, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  body-lead:
    fontFamily: "Noto Sans, Noto Sans Devanagari, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Noto Sans, Noto Sans Devanagari, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 700
    lineHeight: 1.5
  meta:
    fontFamily: "Noto Sans, Noto Sans Devanagari, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 1.5
  segment-label:
    fontFamily: "Noto Sans, Noto Sans Devanagari, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 700
    fontFeature: "tnum"
rounded:
  bar: "2px"
  chip: "3px"
  control: "3px"
  card: "4px"
spacing:
  gutter-mobile: "16px"
  gutter-desktop: "24px"
  panel: "20px"
  grid-column-gap: "40px"
  rail-gap: "48px"
  container: "1280px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "0 20px"
    height: "40px"
    typography: "{typography.label}"
  search-field:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink-muted}"
    rounded: "{rounded.control}"
    padding: "0 12px"
    height: "40px"
    width: "256px"
  topic-chip:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.chip}"
    padding: "0 10px"
    height: "28px"
    typography: "{typography.label}"
  topic-chip-hover:
    backgroundColor: "{colors.line}"
  topic-chip-active:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
  flag-chip:
    backgroundColor: "{colors.flag-bg}"
    textColor: "{colors.flag-ink}"
    rounded: "{rounded.chip}"
    padding: "2px 8px"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "20px"
  citation-chip:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.bar}"
    height: "20px"
    padding: "0 4px"
  citation-chip-hover:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
  utility-strip:
    backgroundColor: "{colors.strip}"
    textColor: "{colors.strip-ink}"
    height: "40px"
  coverage-bar-sm:
    height: "6px"
    width: "80px"
    rounded: "{rounded.bar}"
  coverage-bar-md:
    height: "24px"
    rounded: "{rounded.bar}"
  coverage-bar-lg:
    height: "28px"
    rounded: "{rounded.bar}"
---

# Design System: Lens

## Overview

**Creative North Star: "The Comparison Desk"**

Lens is a news-comparison desk played straight: the Ground News category pattern (story feed, stance coverage bar, blindspots, per-story source lists) adapted for India, at full craft. That lineage is owner-pinned canon for interaction patterns only; Ground News's logo, copy, icons and exact colors are never borrowed (docs/10). The world is warm grey-green newsprint with near-black ink. Everything reads as print: flat tinted panels instead of cards, thin ink rules instead of borders, heavy sans headlines with tight leading, and a stance bar that behaves like a chart in a paper, not a widget.

Density is high but ruled. The feed is a newspaper front: a lead story with a wide labelled bar, a rail, then a three-column ruled grid. Colour is reserved for data. The only chromatic hues on screen are the stance violet and teal and the ochre flag tint; chrome, links, buttons and selection are ink.

The system is bilingual from the metrics up. Noto Sans and Noto Sans Devanagari share one stack; Indic text gets taller line heights and no negative tracking, and Latin runs inside a Hindi page reset to Latin metrics.

**Key Characteristics:**
- Newsprint ground (paper), ink text, flat surface-tinted panels with no borders or shadows at rest.
- Squared corners (2-4px) everywhere.
- Heavy 800 headlines, tight leading, slight negative tracking in Latin only.
- Links are ink with a faint underline, never blue.
- Stance is violet / paper-light / teal / grey, each patterned; colour is never the only signal.
- Every bar or rating carries a confidence line and a methodology link.

## Colors

A near-monochrome newsprint palette where colour is spent only on data: stance, factuality and blindspot flags.

### Primary
- **Newsprint Ink** (ink): All text, primary buttons, the active topic chip, text selection, focus rings, the 3px section rule, and the active-nav underline. Links use it too (`--link` equals ink).

### Secondary
- **Critical Violet** (stance-critical): Coverage-bar segment for sources critical of the government, always with a white diagonal hatch and white label text (stance-critical-ink).
- **Supportive Teal** (stance-supportive): Coverage-bar segment for supportive sources, always with a white dot pattern and white label text.

### Tertiary
- **Ochre Flag** (flag-bg / flag-ink): Blindspot chips and the story "limitations" panel. Neutral in tone: it marks a gap, not an error.

### Neutral
- **Newsprint Paper** (paper): Page ground and the sticky header.
- **Card White** (card): Raised-within-panel fills: the search field, fact-check rating chips, the active tab in a tab strip, popovers.
- **Tint Panel** (surface): Every panel (Blindspot rail, Coverage details, error/empty states), idle chips, citation chips.
- **Hairline** (line): Header bottom border, chip hover, scrollbar track. In-content dividers use ink at 10-15% alpha instead.
- **Muted Ink** (ink-muted): Metadata, intro lines, confidence text, list markers.
- **Night Strip** (strip / strip-ink): The date/language strip above the header and the footer.
- **Balanced Paper** (stance-balanced): The middle stance segment, a lighter-than-paper fill with ink label text; the bar's 1px ink/15 ring keeps it legible against the page.
- **Unclassified Grey** (stance-unclassified): Sources not yet classified, with a faint ink hatch.
- **Factuality Ink Scale** (factuality-high / -mixed / -low): A three-step ink ramp for the factuality meter; no hue, so it never competes with stance.

Dark mode (prefers-color-scheme, unless `.light` is set) swaps every token in `tokens.css`: paper #161714, card #1d1e1a, surface #23241f, ink #e9eae2, critical #6552a3, supportive #1a747a, balanced #dcddd4, flag #3b3420 / #eadcae.

### Named Rules
**The No Party Colors Rule.** Stance hues never use red, green, saffron or sky blue; in India those read as party colors. Any new stance or data hue is checked against that list first.

**The Pattern Always Rule.** Every stance segment carries both a colour and a pattern (hatch, none on the light middle, dots, light hatch). Colour alone never encodes stance.

**The Ink Links Rule.** Links are ink with a 1px underline at ink/40, rising to full ink on hover. There is no link blue.

## Typography

**Display Font:** Noto Sans (with Noto Sans Devanagari, ui-sans-serif, system-ui)
**Body Font:** Noto Sans (same stack)

**Character:** One family doing everything, carried by weight: 800 for every heading, 700 for labels and controls, 500 for meta, 400 for reading. It reads like a newspaper sans set heavy.

### Hierarchy
- **Display** (800, 34px mobile to 48px desktop, headline leading): Story page H1, max 26ch, balanced wrap.
- **Headline** (800, 32px mobile to 44px desktop): The home lead story.
- **Section** (800, 24px): Section heads ("More stories", Summary, Fact checks, Blindspot rail).
- **Title** (800, 20px): Standard story cards in the grid, panel titles. Compact rail cards drop to 16px at 700.
- **Body** (400, 16px, leading 1.5): Default text. Summary bullets and the lead dek run at 18px, max 62-68ch.
- **Label** (700, 13-14px): Chips, buttons, nav (nav is 15px at 500).
- **Meta** (500, 12px): Confidence lines, methodology links, small-bar summaries.
- **Segment label** (700, 11px, tabular figures): Text set inside coverage-bar segments.

Type scale in px: 12 14 16 18 20 24 30 44 48.

### Named Rules
**The Script Metrics Rule.** Latin body 1.5 / headlines 1.25 with -0.015em headline tracking; Indic (hi, mr, bn, ta, te, gu, kn, ml, pa, or) body 1.6 / headlines 1.35 with zero tracking. `:lang(en)` resets Latin metrics inside Hindi pages. Line heights come from `--leading-*` variables, never hard-coded per component.

**The Weight Carries It Rule.** Hierarchy comes from weight and size, not from a second family, uppercase or letter-spacing.

## Layout

A 1280px centred container with 16px gutters on mobile and 24px from `md`. Above it sits a 40px night strip (Indian-format date, language edition switch); below that a sticky 64px header (wordmark, primary nav, search, Sign in) with a topic chip rail attached under a hairline.

Home: from `lg`, a two-column grid, content `minmax(0,1fr)` beside a 340px rail with a 48px gap. The lead story and a "Browse topics" block sit left; the Blindspot panel is the rail. Below, a full-width section opened by the 3px ink rule holds the story grid: 1 column, 2 from `sm`, 3 from `lg`, 40px column gap, each cell ruled at the bottom (ink/15) with 20px vertical padding. On mobile the rail follows the lead and its cards scroll horizontally with snap.

Story: headline and meta first, then content beside a 360px rail holding Coverage details. Below `lg` the Coverage details panel moves directly under the headline.

Mobile: a fixed 56px bottom tab bar (icon + 11px bold label) replaces the header nav.

### Named Rules
**The Ruled Section Rule.** Major sections (More stories, Sources, Fact checks) open with a 3px ink rule above the heading, not a box.

## Elevation & Depth

Flat. Depth comes from tone: paper ground, surface-tinted panels, card-white fills inside panels. Nothing rests on a shadow. The one shadow token, `--shadow-float`, is for things that genuinely float over content: the coverage-bar breakdown tooltip and popovers.

### Shadow Vocabulary
- **Float** (`box-shadow: 0 6px 20px rgb(29 30 27 / 0.14), 0 1px 3px rgb(29 30 27 / 0.1)`): Tooltips and popovers only. Dark mode deepens it.

### Named Rules
**The Tone Not Shadow Rule.** Panels separate by tint, never by border or shadow. Shadows are reserved for transient overlays.

## Shapes

Squared. Bars and citation chips 2px, chips and controls 3px, panels 4px. No pills, no large radii. Borders are rare: the header hairline, the search field's ink/25 stroke, and in-content ink/10-15 dividers. The coverage bar has a 2px gap between segments and a 1px ink/15 ring.

## Components

### Buttons
- **Shape:** Squared (3px).
- **Primary:** Ink fill, paper text, 700 at 14px, 40px tall, 20px side padding (Sign in, Retry).
- **Hover / Focus:** Fill drops to ink/85; focus is a 2px ink outline at 2px offset.
- **Text actions:** Bold ink text with the ink/40 underline ("See all blindspots", "How we calculate this").

### Chips
- **Topic chips:** Surface fill, 700 at 13px, 28px tall, 3px corners; hover to line; active is ink with paper text. The rail scrolls horizontally with no scrollbar.
- **Browse-topic chips:** Same, 32px tall at 14px.
- **Flag chip:** Ochre fill, flag-ink 700 at 12px, eye-off icon, 3px corners. Sits above the card's stretched link.
- **Citation chip:** 20px `[n]` on surface with 2px corners; hover and open states turn ink. Opens a popover with source, headline and "Read at" link.

### Cards / Containers
- **Story cards** have no container: a headline link that stretches over the whole card, then the bar, then meta. The headline underlines (2px) on card hover.
- **Panels:** 4px corners, surface fill, 20px padding, no border, no shadow (Blindspot rail, Coverage details, error and empty states).
- **Limitations:** Ochre flag panel, 500 weight.

### Inputs / Fields
- **Search:** 40px, card fill, ink/25 stroke rising to ink/60 on hover, 3px corners, 256px at `lg`, icon-only below.

### Navigation
- **Primary nav:** 15px at 500, ink/75, 24px apart; the active item gets a 3px ink underline flush to the header bottom.
- **Tab strip (Blindspot):** Segmented control on surface with 4px inset; active tab on card fill.
- **Bottom tab bar (mobile):** Fixed, paper fill, ink/20 top border, five equal cells.

### Coverage Bar (signature)
Pure CSS, segments proportional to distinct sources, 2px gaps, 2px corners.
- **sm** (6px tall, 80px wide): Feed cards, inline with a 12px summary ("56% critical of the government").
- **md / lg** (24px / 28px, full width): The lead story, blindspot cards and the story page, with labels set inside each segment. Every segment is its own container query: label and percentage show at 7.5rem or wider, percentage alone at 2.25rem or wider, nothing below that.
- Hover or focus reveals an ink tooltip with per-bucket counts. Screen readers get a full text alternative.
- Always followed by a confidence line and a methodology link. If there are too few sources, a surface panel says so instead.

### Factuality Meter
A 10px three-segment ink-scale bar, then a two-column count list with 12px swatches, a "Not rated" outline swatch, and the same confidence and methodology line.

## Do's and Don'ts

### Do:
- **Do** follow every stance, bias or factuality figure with a confidence level and a methodology link.
- **Do** pattern every stance segment: hatch on critical, dots on supportive, light hatch on unclassified.
- **Do** separate panels by tint (surface on paper) and open major sections with the 3px ink rule.
- **Do** set `lang` on every headline and summary so the Indic line heights apply.
- **Do** keep all interactive chrome in ink: buttons, active chips, focus rings, selection.

### Don't:
- **Don't** use red, green, saffron or sky blue for any stance or data encoding.
- **Don't** copy Ground News's logo, copy, icons or exact colors; borrow its patterns only.
- **Don't** use blue links, pill chips, rounded bordered cards or resting shadows.
- **Don't** use negative tracking on Indic scripts or hard-code line heights that bypass `--leading-*`.
- **Don't** show a bar or rating without its methodology link.
