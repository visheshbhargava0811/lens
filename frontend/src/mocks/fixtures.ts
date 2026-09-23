/**
 * MSW fixtures matching docs/09. ALL DATA HERE IS FICTIONAL: outlet names, owners,
 * raters, fact-checkers and events are invented placeholders (CLAUDE.md rule 7).
 * Nothing here describes a real outlet.
 *
 * Coverage numbers are derived from the article rows with the same math the UI uses,
 * so counts, buckets and percentages always agree.
 */
import type {
  AnalysisDepth,
  ArticleRow,
  Blindspot,
  Confidence,
  CitedSentence,
  FactCheck,
  FactualityCounts,
  SourceDetail,
  StoryCard,
  StoryDetail,
  StoryStatus,
} from "@/lib/api/types";
import { buildCoverage } from "@/lib/coverage";

// ------------------------------------------------------------------ sources

interface FixtureSource {
  id: string;
  name: string;
  language: string;
  rating: "High" | "Mixed" | "Low" | null;
  /** Fictional rater wording for outlet bias (ADR-0020). */
  bias: "Left" | "Left-Center" | "Least Biased" | "Right-Center" | "Right" | null;
  owner: string | null;
  wire?: boolean;
}

const S = (id: string, name: string, language: string, rating: FixtureSource["rating"], bias: FixtureSource["bias"], owner: string | null, wire = false): FixtureSource => ({ id, name, language, rating, bias, owner, wire });

export const sources: FixtureSource[] = [
  S("s-example-times", "Example Times", "en", "High", "Left-Center", "Example Group A"),
  S("s-sample-herald", "Sample Herald", "en", "High", "Least Biased", "Example Group A"),
  S("s-demo-daily", "Demo Daily", "en", "Mixed", "Left", "Example Group B"),
  S("s-placeholder-post", "Placeholder Post", "en", null, null, null),
  S("s-mock-mirror", "Mock Mirror", "en", "Low", "Right", "Example Group C"),
  S("s-specimen-express", "Specimen Express", "en", "High", "Right-Center", "Example Group C"),
  S("s-prototype-tribune", "Prototype Tribune", "en", "Mixed", "Least Biased", null),
  S("s-draft-chronicle", "Draft Chronicle", "en", null, null, "Example Group B"),
  S("s-template-today", "Template Today", "en", "High", "Right-Center", null),
  S("s-namuna-samachar", "नमूना समाचार", "hi", "High", "Right-Center", "Example Group B"),
  S("s-udaharan-dainik", "उदाहरण दैनिक", "hi", "Mixed", "Left-Center", null),
  S("s-pariksha-patrika", "परीक्षण पत्रिका", "hi", null, null, null),
  S("s-demo-bharat", "डेमो भारत", "hi", "Mixed", "Right", "Example Group A"),
  S("s-prarup-times", "प्रारूप टाइम्स", "hi", "High", "Least Biased", null),
  S("s-masauda-khabar", "मसौदा ख़बर", "hi", null, null, "Example Group C"),
  S("s-adarsh-samvad", "आदर्श संवाद", "hi", "Mixed", "Right-Center", null),
  S("s-mathiri-seithi", "மாதிரி செய்தி", "ta", null, null, null),
  S("s-namuna-varta", "नमुना वार्ता", "mr", "Mixed", "Left-Center", null),
  S("s-wire-sample", "Wire Sample Agency", "en", "High", null, null, true),
];

const byId = new Map(sources.map((s) => [s.id, s]));
const src = (id: string): FixtureSource => {
  const s = byId.get(id);
  if (!s) throw new Error(`unknown fixture source ${id}`);
  return s;
};

// ------------------------------------------------------------------ helpers

const RATER = "Example Rater";
const RATER_METHOD = "https://example.org/rater-methodology";
const EVIDENCE = "https://example.org/ownership-evidence";

function ago(minutes: number): string {
  return new Date(Date.now() - minutes * 60_000).toISOString();
}

interface ArticleSpec {
  source: string;
  headline: string;
  lang?: string;
  depth?: AnalysisDepth;
  minutesAgo: number;
  /** Source ids that carried this wire copy. Their rows are marked syndicated. */
  carriedBy?: string[];
}

interface StorySpec {
  id: string;
  slug: string;
  headline: string;
  headline_lang: string;
  status: StoryStatus;
  topic: string;
  updatedMinutesAgo: number;
  articles: ArticleSpec[];
  blindspot?: Blindspot;
  summary?: { lang: string; verified: boolean; sentences: [string, number[]][]; agreements?: [string, number[]][]; disagreements?: [string, number[]][] };
  framing?: [string, number[]][];
  factChecks?: FactCheck[];
  preview?: string;
}

/** Fixture copy of config/guardrails.yaml `bias_value_map` (lean-left/right count with their side). */
const BIAS_BUCKET = { Left: "left", "Left-Center": "left", "Least Biased": "center", "Right-Center": "right", Right: "right" } as const;
const bucketOf = (s: FixtureSource) => (s.bias ? BIAS_BUCKET[s.bias] : "unrated");

/** Mirrors lens.stats.coverage.rated_share_confidence: share of outlets that are rated. */
function ratedShareConfidence(rated: number, total: number): Confidence {
  const share = total ? rated / total : 0;
  return share >= 0.8 ? "high" : share >= 0.5 ? "medium" : "low";
}

function articleRows(spec: StorySpec): ArticleRow[] {
  const rows: ArticleRow[] = [];
  spec.articles.forEach((a, i) => {
    const s = src(a.source);
    const base: Omit<ArticleRow, "id" | "source" | "is_syndicated" | "also_carried_by"> = {
      headline: a.headline,
      headline_lang: a.lang ?? s.language,
      published_at: ago(a.minutesAgo),
      url: `https://example.org/${spec.slug}/${i}`,
      analysis_depth: a.depth ?? "snippet",
      bias: "unrated",
      source_bias: null,
      source_factuality: null,
      source_ownership: null,
    };
    const withSource = (sid: string, id: string, syndicated: boolean, also: string[]): ArticleRow => {
      const ss = src(sid);
      return {
        ...base,
        id,
        source: { id: ss.id, name: ss.name, logo_url: null, language: ss.language },
        bias: bucketOf(ss),
        source_bias: ss.bias ? { rater: RATER, value: ss.bias, method_url: RATER_METHOD, confidence: "medium" } : null,
        source_factuality: ss.rating
          ? { rater: RATER, value: ss.rating, method_url: RATER_METHOD, confidence: "medium" }
          : null,
        source_ownership: ss.owner ? { owner: ss.owner, evidence_url: EVIDENCE } : null,
        is_syndicated: syndicated,
        also_carried_by: also,
      };
    };
    const carried = (a.carriedBy ?? []).map((id) => src(id).name);
    rows.push(withSource(s.id, `${spec.id}-a${i + 1}`, false, carried));
    (a.carriedBy ?? []).forEach((sid, j) => {
      rows.push(withSource(sid, `${spec.id}-a${i + 1}-syn${j + 1}`, true, []));
    });
  });
  return rows.sort((x, y) => y.published_at.localeCompare(x.published_at));
}

function cited(pairs: [string, number[]][] | undefined, spec: StorySpec): CitedSentence[] {
  let n = 0;
  return (pairs ?? []).map(([text, idxs]) => ({
    text,
    citations: idxs.map((i) => {
      const a = spec.articles[i];
      n += 1;
      return { n, article_id: `${spec.id}-a${i + 1}`, source_name: src(a.source).name, chunk_id: `${spec.id}-c${i + 1}` };
    }),
  }));
}

/** Numbers citations continuously across summary, agreements, disagreements, framing. */
function renumber(groups: CitedSentence[][]): void {
  let n = 0;
  for (const g of groups) for (const s of g) for (const c of s.citations) c.n = ++n;
}

function build(spec: StorySpec): { card: StoryCard; detail: StoryDetail; articles: ArticleRow[] } {
  const rows = articleRows(spec);
  // Distinct sources after syndication dedup: syndicated copies do not add a source.
  const originals = spec.articles;
  const distinct = new Map<string, ArticleSpec>();
  for (const a of originals) if (!distinct.has(a.source)) distinct.set(a.source, a);

  const biasCounts = { left: 0, center: 0, right: 0 };
  let unrated = 0;
  for (const sid of distinct.keys()) {
    const b = bucketOf(src(sid));
    if (b === "unrated") unrated += 1;
    else biasCounts[b] += 1;
  }
  const n = distinct.size;
  const coverageConfidence = ratedShareConfidence(n - unrated, n);

  const factuality: FactualityCounts = { high: 0, mixed: 0, low: 0, unrated: 0, confidence: "medium", methodology_url: "/methodology#factuality" };
  const byLanguage: Record<string, number> = {};
  const owners = new Map<string, number>();
  let unknownOwner = 0;
  for (const sid of distinct.keys()) {
    const s = src(sid);
    if (s.rating === "High") factuality.high += 1;
    else if (s.rating === "Mixed") factuality.mixed += 1;
    else if (s.rating === "Low") factuality.low += 1;
    else factuality.unrated += 1;
    byLanguage[s.language] = (byLanguage[s.language] ?? 0) + 1;
    if (s.owner) owners.set(s.owner, (owners.get(s.owner) ?? 0) + 1);
    else unknownOwner += 1;
  }
  factuality.confidence = ratedShareConfidence(n - factuality.unrated, n);

  const card: StoryCard = {
    id: spec.id,
    slug: spec.slug,
    headline: spec.headline,
    headline_lang: spec.headline_lang,
    status: spec.status,
    updated_at: ago(spec.updatedMinutesAgo),
    topic: spec.topic,
    image: null,
    counts: { sources: n, articles: rows.length, by_language: byLanguage },
    coverage: buildCoverage(biasCounts, unrated, coverageConfidence),
    factuality,
    blindspot: spec.blindspot ?? null,
    summary_preview: spec.preview ?? null,
  };

  const sentences = cited(spec.summary?.sentences, spec);
  const agreements = cited(spec.summary?.agreements, spec);
  const disagreements = cited(spec.summary?.disagreements, spec);
  const framing = cited(spec.framing, spec);
  renumber([sentences, agreements, disagreements, framing]);

  const shallow = rows.filter((r) => !r.is_syndicated && r.analysis_depth !== "full_text");
  const shallowSources = new Set(shallow.map((r) => r.source.id)).size;
  const limitations: string[] = [];
  if (shallowSources > 0) limitations.push(`Based on headlines and summaries for ${shallowSources} of ${n} sources.`);

  const detail: StoryDetail = {
    story: card,
    summary: spec.summary
      ? {
          lang: spec.summary.lang,
          version: 3,
          generated_at: ago(spec.updatedMinutesAgo + 5),
          verified: spec.summary.verified,
          sentences,
          agreements,
          disagreements,
        }
      : null,
    framing_differences: framing,
    fact_checks: spec.factChecks ?? [],
    ownership: {
      groups: [...owners.entries()].map(([name, count]) => ({ name, sources: count })).sort((a, b) => b.sources - a.sources),
      unknown: unknownOwner,
      methodology_url: "/methodology#ownership",
    },
    limitations,
  };
  return { card, detail, articles: rows };
}

// ------------------------------------------------------------------ stories

const A = (source: string, minutesAgo: number, headline: string, extra: Partial<ArticleSpec> = {}): ArticleSpec => ({ source, minutesAgo, headline, ...extra });

const specs: StorySpec[] = [
  {
    id: "st-ride-hailing-rules",
    slug: "central-government-proposes-rules-for-ride-hailing-apps",
    headline: "Central government proposes new rules for ride-hailing apps",
    headline_lang: "en",
    status: "developing",
    topic: "business",
    updatedMinutesAgo: 120,
    preview: "The draft sets a cap on surge pricing and requires driver insurance. Outlets differ on whether it helps drivers or adds compliance costs.",
    articles: [
      A("s-example-times", 125, "Draft rules cap surge pricing for ride-hailing apps", { depth: "full_text" }),
      A("s-sample-herald", 140, "New ride-hailing rules to protect commuters, says ministry"),
      A("s-demo-daily", 150, "Drivers' groups say ride-hailing draft ignores their pay"),
      A("s-placeholder-post", 170, "Ride-hailing draft: what it leaves out"),
      A("s-mock-mirror", 200, "Government moves to rein in app-based cab pricing"),
      A("s-specimen-express", 210, "Explained: the proposed rules for cab aggregators", { depth: "full_text" }),
      A("s-prototype-tribune", 230, "Startups warn ride-hailing rules raise compliance costs"),
      A("s-namuna-samachar", 190, "ऐप आधारित टैक्सी सेवाओं के लिए नए नियमों का मसौदा जारी"),
      A("s-udaharan-dainik", 215, "कैब ड्राइवरों ने कहा, नए नियमों में कमाई का ज़िक्र नहीं"),
      A("s-demo-bharat", 240, "यात्रियों को राहत: सर्ज प्राइसिंग पर लगेगी सीमा"),
      A("s-pariksha-patrika", 260, "कैब कंपनियों के लिए नए नियम"),
      A("s-mathiri-seithi", 280, "வாடகை கார் செயலிகளுக்கு புதிய விதிமுறைகள் முன்மொழிவு"),
      A("s-wire-sample", 130, "Government releases draft rules for app-based cab services", {
        carriedBy: ["s-template-today", "s-draft-chronicle"],
      }),
    ],
    summary: {
      lang: "en",
      verified: true,
      sentences: [
        ["The central government released draft rules for app-based cab services that cap surge pricing.", [0, 12]],
        ["The draft also requires aggregators to provide insurance for drivers.", [5]],
        ["Drivers' groups said the draft does not address how drivers are paid.", [2, 8]],
      ],
      agreements: [["Outlets agree the draft caps surge pricing and is open for public comment.", [0, 7]]],
      disagreements: [["Outlets differ on whether the rules mainly help commuters or add costs for companies.", [1, 6]]],
    },
    framing: [["Some headlines lead with commuter relief, others with driver pay and startup costs.", [9, 3]]],
    factChecks: [
      {
        claim: "A viral post says the draft bans surge pricing entirely.",
        fact_checker: "Example Fact-checker",
        rating: "misleading",
        url: "https://example.org/fact-check/surge-pricing",
        published_at: ago(300),
      },
    ],
  },
  {
    id: "st-metro-budget",
    slug: "state-approves-budget-for-new-metro-line",
    headline: "राज्य सरकार ने नई मेट्रो लाइन के लिए बजट मंज़ूर किया",
    headline_lang: "hi",
    status: "developing",
    topic: "politics",
    updatedMinutesAgo: 45,
    preview: "राज्य मंत्रिमंडल ने नई मेट्रो लाइन के पहले चरण के लिए बजट को मंज़ूरी दी।",
    articles: [
      A("s-namuna-samachar", 50, "राज्य सरकार ने नई मेट्रो लाइन के लिए बजट मंज़ूर किया"),
      A("s-demo-bharat", 60, "मेट्रो विस्तार से लाखों यात्रियों को फ़ायदा: राज्य सरकार"),
      A("s-udaharan-dainik", 75, "मेट्रो बजट पर विपक्ष ने उठाए सवाल"),
      A("s-prarup-times", 80, "नई मेट्रो लाइन: किन इलाक़ों से गुज़रेगी"),
      A("s-example-times", 90, "State cabinet clears funds for first phase of new metro line"),
      A("s-demo-daily", 110, "Metro line budget approved without cost audit, say critics"),
      A("s-namuna-varta", 130, "नव्या मेट्रो मार्गासाठी राज्य सरकारकडून निधी मंजूर"),
    ],
    summary: {
      lang: "hi",
      verified: true,
      sentences: [
        ["राज्य मंत्रिमंडल ने नई मेट्रो लाइन के पहले चरण के लिए बजट को मंज़ूरी दी।", [0, 4]],
        ["विपक्ष ने लागत के ऑडिट की माँग की है।", [2, 5]],
      ],
      agreements: [["सभी स्रोत बताते हैं कि यह मंज़ूरी पहले चरण के लिए है।", [0, 3]]],
      disagreements: [["कुछ स्रोत यात्रियों के फ़ायदे पर ज़ोर देते हैं, कुछ लागत पर।", [1, 5]]],
    },
  },
  {
    id: "st-rural-roads",
    slug: "government-highlights-rural-road-completion-figures",
    headline: "Government highlights rural road completion figures",
    headline_lang: "en",
    status: "stable",
    topic: "politics",
    updatedMinutesAgo: 60 * 9,
    blindspot: { type: "bias", skew: "right", score: 0.83 },
    preview: "The ministry said a rural roads programme met its annual target. Few outlets examined the figures independently.",
    articles: [
      A("s-sample-herald", 60 * 9, "Rural road programme meets annual target, ministry says"),
      A("s-mock-mirror", 60 * 9 + 20, "Record year for village road connectivity"),
      A("s-demo-bharat", 60 * 10, "ग्रामीण सड़क योजना ने लक्ष्य पूरा किया"),
      A("s-specimen-express", 60 * 10 + 30, "Rural roads target achieved ahead of schedule"),
      A("s-prarup-times", 60 * 11, "गाँवों तक पक्की सड़क: सरकार के आँकड़े"),
      A("s-template-today", 60 * 11 + 15, "Ministry releases rural road completion data"),
      A("s-example-times", 60 * 12, "Rural roads: what the completion numbers include"),
      A("s-masauda-khabar", 60 * 12 + 40, "ग्रामीण सड़कों का काम तय समय से पहले"),
    ],
  },
  {
    id: "st-crop-insurance",
    slug: "farmers-protest-crop-insurance-payment-delays",
    headline: "किसानों ने फ़सल बीमा भुगतान में देरी पर विरोध जताया",
    headline_lang: "hi",
    status: "developing",
    topic: "politics",
    updatedMinutesAgo: 30,
    blindspot: { type: "language", skew: "hi", score: 0.77 },
    preview: "कई ज़िलों में किसानों ने बीमा दावों के भुगतान में देरी को लेकर प्रदर्शन किया।",
    articles: [
      A("s-namuna-samachar", 35, "फ़सल बीमा भुगतान में देरी पर किसानों का प्रदर्शन"),
      A("s-udaharan-dainik", 50, "बीमा दावे महीनों से अटके, किसान नाराज़"),
      A("s-pariksha-patrika", 65, "फ़सल बीमा: प्रशासन ने कहा, जल्द होगा भुगतान"),
      A("s-demo-bharat", 80, "किसानों की माँगों पर बैठक बुलाई गई"),
      A("s-prarup-times", 95, "ज़िला मुख्यालय पर किसानों का धरना"),
      A("s-masauda-khabar", 100, "बीमा कंपनी के ख़िलाफ़ किसानों का ज्ञापन"),
      A("s-adarsh-samvad", 120, "फ़सल बीमा दावों की स्थिति पर रिपोर्ट"),
      A("s-namuna-varta", 140, "पीक विमा भरपाईला उशीर, शेतकरी आक्रमक"),
      A("s-draft-chronicle", 150, "Farmers seek faster crop insurance payouts"),
    ],
    summary: {
      lang: "hi",
      verified: false,
      sentences: [["कई ज़िलों में किसानों ने बीमा दावों के भुगतान में देरी को लेकर प्रदर्शन किया।", [0, 4]]],
    },
  },
  {
    id: "st-flood-warning",
    slug: "researchers-report-results-from-coastal-flood-warning-pilot",
    headline: "Researchers report early results from coastal flood-warning pilot",
    headline_lang: "en",
    status: "developing",
    topic: "science",
    updatedMinutesAgo: 200,
    articles: [
      A("s-template-today", 200, "Coastal flood-warning pilot shows early promise"),
      A("s-mathiri-seithi", 230, "கடலோர வெள்ள எச்சரிக்கை சோதனை: ஆரம்ப முடிவுகள்"),
    ],
  },
  {
    id: "st-dengue",
    slug: "hospitals-report-rise-in-dengue-cases",
    headline: "Hospitals in several districts report rise in dengue cases",
    headline_lang: "en",
    status: "developing",
    topic: "health",
    updatedMinutesAgo: 75,
    preview: "District hospitals reported more dengue admissions this week. Coverage focuses on bed availability.",
    articles: [
      A("s-example-times", 80, "Dengue admissions rise in district hospitals"),
      A("s-demo-daily", 95, "Hospitals short of beds as dengue cases climb"),
      A("s-namuna-samachar", 100, "डेंगू के मामलों में बढ़ोतरी, अस्पतालों में भीड़"),
      A("s-placeholder-post", 120, "Dengue: health department issues advisory"),
      A("s-pariksha-patrika", 150, "डेंगू से बचाव के उपाय"),
      A("s-adarsh-samvad", 170, "डेंगू: फ़ॉगिंग अभियान में देरी का आरोप"),
    ],
  },
  {
    id: "st-digital-payments",
    slug: "government-portal-launches-digital-payment-feature",
    headline: "सरकारी पोर्टल पर नया डिजिटल भुगतान फ़ीचर शुरू",
    headline_lang: "hi",
    status: "stable",
    topic: "tech",
    updatedMinutesAgo: 60 * 5,
    articles: [
      A("s-demo-bharat", 60 * 5, "सरकारी पोर्टल पर अब सीधे भुगतान की सुविधा"),
      A("s-prarup-times", 60 * 5 + 30, "नया भुगतान फ़ीचर: कैसे करें इस्तेमाल"),
      A("s-specimen-express", 60 * 6, "Government portal adds direct payment option"),
      A("s-prototype-tribune", 60 * 6 + 20, "Portal's new payment feature raises data questions"),
      A("s-udaharan-dainik", 60 * 7, "डिजिटल भुगतान फ़ीचर शुरू, पहले दिन तकनीकी दिक़्क़तें"),
    ],
  },
  {
    id: "st-hockey",
    slug: "womens-hockey-team-qualifies-for-continental-final",
    headline: "National women's hockey team qualifies for continental final",
    headline_lang: "en",
    status: "developing",
    topic: "sports",
    updatedMinutesAgo: 90,
    articles: [
      A("s-sample-herald", 90, "Women's hockey team storms into continental final"),
      A("s-mock-mirror", 95, "Hockey: late goal seals final spot"),
      A("s-namuna-samachar", 100, "महिला हॉकी टीम फ़ाइनल में पहुँची"),
      A("s-mathiri-seithi", 110, "மகளிர் ஹாக்கி அணி இறுதிப் போட்டிக்கு தகுதி"),
    ],
  },
  // Page 2 of the feed
  {
    id: "st-river-data",
    slug: "neighbouring-countries-sign-river-data-sharing-pact",
    headline: "Neighbouring countries sign river-water data sharing pact",
    headline_lang: "en",
    status: "stable",
    topic: "world",
    updatedMinutesAgo: 60 * 20,
    articles: [
      A("s-example-times", 60 * 20, "River data pact signed after two years of talks"),
      A("s-specimen-express", 60 * 20 + 30, "Pact on river data a diplomatic win, officials say"),
      A("s-namuna-samachar", 60 * 21, "नदी जल आँकड़े साझा करने पर समझौता"),
      A("s-demo-daily", 60 * 22, "River data pact silent on dam releases, experts note"),
    ],
  },
  {
    id: "st-chennai-bus",
    slug: "new-bus-routes-introduced-in-chennai",
    headline: "சென்னையில் புதிய பேருந்து வழித்தடங்கள் அறிமுகம்",
    headline_lang: "ta",
    status: "stable",
    topic: "top",
    updatedMinutesAgo: 60 * 26,
    articles: [
      A("s-mathiri-seithi", 60 * 26, "சென்னையில் புதிய பேருந்து வழித்தடங்கள் அறிமுகம்"),
      A("s-template-today", 60 * 27, "New bus routes announced for city suburbs"),
      A("s-example-times", 60 * 28, "City transport adds routes to suburbs"),
      A("s-prototype-tribune", 60 * 29, "Commuters ask why new routes skip industrial belt"),
    ],
  },
];

// ------------------------------------------------------------------ indexes

const built = specs.map(build);

export const stories = built.map((b) => b.card);
export const details = new Map(built.map((b) => [b.card.id, b.detail]));
export const articlesByStory = new Map(built.map((b) => [b.card.id, b.articles]));
export const slugToId = new Map(built.map((b) => [b.card.slug, b.card.id]));

/** Source page fixture (docs/09 SourceDetail), derived from the fictional sources and stories above. */
export function sourceDetail(id: string): SourceDetail | undefined {
  const s = byId.get(id);
  if (!s) return undefined;
  const checked = ago(60 * 24);
  const ratings: SourceDetail["ratings"] = [];
  if (s.bias) ratings.push({ dimension: "bias", rater: RATER, value: s.bias, method_url: RATER_METHOD, evidence_url: null, retrieved_at: checked, confidence: "medium" });
  if (s.rating) ratings.push({ dimension: "factuality", rater: RATER, value: s.rating, method_url: RATER_METHOD, evidence_url: null, retrieved_at: checked, confidence: "medium" });
  return {
    source: { id: s.id, slug: s.id, name: s.name, homepage_url: `https://example.org/${s.id}`, languages: [s.language], region: "national", is_wire: !!s.wire, license_mode: "snippet_only" },
    ownership: s.owner ? [{ owner_name: s.owner, owner_type: null, parent_group: s.owner, evidence_url: EVIDENCE, retrieved_at: checked, confidence: "medium" }] : [],
    ratings,
    recent_stories: stories.filter((c) => (articlesByStory.get(c.id) ?? []).some((a) => a.source.id === id)).slice(0, 6),
    methodology_url: "/methodology#sources",
  };
}

export const FEED_PAGE_SIZE = 8;

/** Stories that trigger error responses, for error-state tests. */
export const ERROR_TOPIC = "fixture-error";
export const ERROR_STORY_SLUG = "fixture-error";

export const topics: { slug: string; name: { en: string; hi: string } }[] = [
  { slug: "top", name: { en: "Top", hi: "प्रमुख" } },
  { slug: "politics", name: { en: "Politics", hi: "राजनीति" } },
  { slug: "business", name: { en: "Business", hi: "व्यापार" } },
  { slug: "world", name: { en: "World", hi: "दुनिया" } },
  { slug: "sports", name: { en: "Sports", hi: "खेल" } },
  { slug: "tech", name: { en: "Tech", hi: "टेक" } },
  { slug: "health", name: { en: "Health", hi: "स्वास्थ्य" } },
  { slug: "science", name: { en: "Science", hi: "विज्ञान" } },
  { slug: "entertainment", name: { en: "Entertainment", hi: "मनोरंजन" } },
];
