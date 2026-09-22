---
version: 1
slug: "frontend-src-app"
primary_target: "frontend/src/app"
related_targets: []
---

# Surface: Lens web app (all routes)

Scope: header/nav, Home feed, Story, Blindspot, Topic, Methodology, loading/error/empty states. Light + dark. Mode: Operate (scan feed, compare coverage) with Read on Story and Methodology.

Audience and job: from PRODUCT.md. Everyday phone reader and desktop power reader, equally.

Constraints: docs/10 bans Ground News's logo, copy, icons, exact colors; stance colors never red/green/saffron/sky blue; every bar segment patterned; Noto Sans + Noto Sans Devanagari; text-only tiles by default; 150 KB JS budget.

## Direction contract

THESIS: A Ground-News-toned comparison desk for Indian news. Owner-pinned canon: the category standard played straight at full craft. Refuses the stock shadcn look (white ground, rounded bordered cards, pill chips, blue links, soft shadows) the current build shipped.

OWN-WORLD: Warm grey-green newsprint ground, near-black ink, flat tinted panels with no borders or shadows, squared 2px corners. Heavy Noto Sans 800 headlines, tight leading. Stance bar: flat squared segments, percentage labels set inside; critical = deep violet with hatch, balanced = paper-light middle, supportive = deep teal with dots, unclassified = grey hatch. Ink-black primary buttons, outlined secondary. Underlined ink links, not blue. Dark utility strip on top.

STORY: Reader sees at a glance which stories exist, how widely and in which languages each is covered, and how the coverage splits by stance; opens a story, compares sources by stance and language, clicks out to outlets.

FIRST VIEWPORT: Dark strip (date in Indian format, language edition switch). Header: wordmark, primary nav with underline active state, search, Sign in. Topic chip rail with "+" follow affordance. Home: lead story at left with large 800 headline and wide labelled bar; right rail "Blindspot" panel on tint. Below: dense 3-column story grid, each with small labelled bar and "N sources" line.

FORM: Canon (owner took the standing exit: Ground News named as the bar). Concept roll not run: brief-pinned direction beats the roll. Seed key: none (pinned canon).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
