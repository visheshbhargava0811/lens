import { http, HttpResponse } from "msw";

import { API_BASE } from "@/lib/api/client";
import type {
  AskEventName,
  AskEvents,
  Blindspots,
  Methodology,
  Page,
  StoryArticles,
  StoryCard,
  Topic,
} from "@/lib/api/types";

import {
  articlesByStory,
  details,
  ERROR_STORY_SLUG,
  ERROR_TOPIC,
  LOCAL_STATE,
  FEED_PAGE_SIZE,
  slugToId,
  sourceDetail,
  stories,
  topics,
} from "./fixtures";

const serverError = () =>
  HttpResponse.json(
    {
      error: {
        code: "fixture_error",
        message: "This fixture always fails, to test error states.",
      },
    },
    { status: 500 },
  );

const notFound = (what: string) =>
  HttpResponse.json(
    { error: { code: "not_found", message: `No ${what} with that id.` } },
    { status: 404 },
  );

function resolveStoryId(idOrSlug: string): string | undefined {
  if (details.has(idOrSlug)) return idOrSlug;
  return slugToId.get(idOrSlug);
}

// ---- /ask (docs/09 SSE). The query picks the flow: "rigging" (loaded premise), "cricket" (no
// coverage), "slogan" (out of scope), "riot" (sensitive, under review), "too fast" (429).
type AskFixture = { [K in AskEventName]: [K, AskEvents[K]] }[AskEventName];

function sse(events: AskFixture[]): HttpResponse<ReadableStream> {
  const enc = new TextEncoder();
  const body = new ReadableStream({
    async start(controller) {
      for (const [event, data] of events) {
        controller.enqueue(
          enc.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`),
        );
        await new Promise((r) => setTimeout(r, 40));
      }
      controller.close();
    },
  });
  return new HttpResponse(body, {
    headers: {
      "content-type": "text/event-stream",
      "cache-control": "no-store",
    },
  });
}

function askAnswer(loaded: boolean): AskFixture[] {
  const story = stories[0];
  const detail = details.get(story.id)!;
  const rows = articlesByStory.get(story.id)!;
  const sentences = detail.summary?.sentences ?? [];
  const cited = new Set(
    sentences.flatMap((s) => s.citations.map((c) => c.article_id)),
  );
  const premise = "the government is hiding the numbers";
  return [
    [
      "status",
      { step: "understanding", message: "Understanding the question" },
    ],
    [
      "understanding",
      {
        neutral_query: loaded
          ? "What has been reported about the numbers?"
          : story.headline,
        removed_premises: loaded ? [premise] : [],
        language: "en",
        intent: "story_lookup",
      },
    ],
    ["status", { step: "searching", message: "Searching coverage" }],
    [
      "evidence",
      {
        story_ids: [story.id],
        sources: rows.map((a) => ({
          source_id: a.source.id,
          name: a.source.name,
          language: a.source.language,
          bias: a.bias,
        })),
        stale: false,
        newest_article_at: story.updated_at,
        methodology_url: "/methodology#bias",
      },
    ],
    ["status", { step: "writing", message: "Writing a cited answer" }],
    [
      "status",
      {
        step: "verifying",
        message: "Checking every sentence against its sources",
      },
    ],
    [
      "answer_final",
      {
        basis: "live",
        lang: "en",
        tldr: sentences.slice(0, 1),
        what_happened: sentences.slice(1),
        agreements: detail.summary?.agreements ?? [],
        disagreements: detail.summary?.disagreements ?? [],
        premises_addressed: [],
        limitations: [
          ...(loaded
            ? [`None of the retrieved articles report that ${premise}.`]
            : []),
          "Based on headlines and short feed summaries, not full articles.",
        ],
        follow_up_questions: [
          "What did officials say?",
          "How did coverage differ by language?",
        ],
        coverage: story.coverage,
        fact_checks: [],
        story_ids: [story.id],
        articles: rows
          .filter((a) => cited.has(a.id))
          .map((a) => ({
            id: a.id,
            headline: a.headline,
            headline_lang: a.headline_lang,
            url: a.url,
            source_name: a.source.name,
            source_language: a.source.language,
          })),
        verified: true,
      },
    ],
  ];
}

function askAbstain(
  reason: AskEvents["abstain"]["reason"],
  closest: StoryCard[] = [],
): AskFixture[] {
  return [
    [
      "status",
      { step: "understanding", message: "Understanding the question" },
    ],
    ["abstain", { reason, message: reason, closest_stories: closest }],
  ];
}

// /me mock (docs/11, ADR-0041): in-memory, same closed keys and values as config/memory.yaml.
const ALLOWED: Record<string, string[]> = {
  output_language: ["en", "hi", "mr"],
  ui_language: ["en", "hi"],
  summary_length: ["short", "standard"],
  audio_preference: ["off", "on"],
  followed_topics: [
    "politics",
    "business",
    "world",
    "sports",
    "tech",
    "health",
    "science",
    "entertainment",
  ],
  followed_regions: ["delhi", "maharashtra", "tamil-nadu"],
};
const memoryState: { preferences: Record<string, string | string[]> } = {
  preferences: {},
};
/** Google sign-in is a full-page redirect the mocks cannot follow; tests start signed in with
 * `window.__lensMockSignedIn = true` (an init script), and sign-out clears it. */
const signedIn = () =>
  !!(globalThis as { __lensMockSignedIn?: boolean }).__lensMockSignedIn;
const meState = () => ({
  consented: signedIn(), // preferences need sign-in (ADR-0044)
  signed_in_with: signedIn() ? "google" : null,
  sign_in_providers: ["google"],
  preferences: memoryState.preferences,
  allowed: ALLOWED,
});

// Fixtures must match docs/09_API_SPEC.md exactly.
export const handlers = [
  http.get(`${API_BASE}/me`, () => HttpResponse.json(meState())),
  http.post(`${API_BASE}/auth/sign-out`, () => {
    (globalThis as { __lensMockSignedIn?: boolean }).__lensMockSignedIn = false;
    return new HttpResponse(null, { status: 204 });
  }),
  http.put(`${API_BASE}/me/preferences`, async ({ request }) => {
    if (!signedIn())
      return HttpResponse.json({ detail: "memory is off" }, { status: 401 });
    const { key, value } = (await request.json()) as {
      key: string;
      value: string | string[];
    };
    if (!(key in ALLOWED))
      return HttpResponse.json(
        { detail: "not a storable preference" },
        { status: 422 },
      );
    memoryState.preferences[key] = value;
    return HttpResponse.json(meState());
  }),
  http.get(`${API_BASE}/me/memory`, () =>
    signedIn()
      ? HttpResponse.json({
          preferences: memoryState.preferences,
          story_views: [],
          ask_history: [],
          retention_days: 30,
        })
      : HttpResponse.json({ detail: "memory is off" }, { status: 401 }),
  ),
  http.delete(`${API_BASE}/me/memory`, () => {
    (globalThis as { __lensMockSignedIn?: boolean }).__lensMockSignedIn = false; // the account is gone
    memoryState.preferences = {};
    return new HttpResponse(null, { status: 204 });
  }),
  http.delete(`${API_BASE}/me/memory/preferences/:key`, ({ params }) => {
    delete memoryState.preferences[String(params.key)];
    return new HttpResponse(null, { status: 204 });
  }),
  http.post(`${API_BASE}/me/views/:id`, () =>
    signedIn()
      ? HttpResponse.json(null)
      : HttpResponse.json({ detail: "memory is off" }, { status: 401 }),
  ),
  http.get(`${API_BASE}/me/feed`, () =>
    HttpResponse.json({ items: stories.slice(0, 3), next_cursor: null }),
  ),
  http.get(`${API_BASE}/health`, () =>
    HttpResponse.json({ status: "ok", version: "mock", env: "mock" }),
  ),

  http.get(`${API_BASE}/feed`, ({ request }) => {
    const q = new URL(request.url).searchParams;
    const topic = q.get("topic");
    if (topic === ERROR_TOPIC) return serverError();
    const filtered =
      q.get("tab") === "local"
        ? q.get("state") === LOCAL_STATE
          ? stories.slice(0, 3)
          : []
        : !topic || topic === "top"
          ? stories
          : stories.filter((s) => s.topic === topic);
    const start = Number(q.get("cursor") ?? 0) || 0;
    const items = filtered.slice(start, start + FEED_PAGE_SIZE);
    const next =
      start + FEED_PAGE_SIZE < filtered.length
        ? String(start + FEED_PAGE_SIZE)
        : null;
    return HttpResponse.json<Page<StoryCard>>(
      { items, next_cursor: next },
      {
        headers: {
          "Cache-Control": "public, max-age=30, stale-while-revalidate=60",
        },
      },
    );
  }),

  http.get(`${API_BASE}/stories/:id`, ({ params }) => {
    if (params.id === ERROR_STORY_SLUG) return serverError();
    const id = resolveStoryId(String(params.id));
    return id ? HttpResponse.json(details.get(id)) : notFound("story");
  }),

  http.get(`${API_BASE}/stories/:id/articles`, ({ params }) => {
    const id = resolveStoryId(String(params.id));
    if (!id) return notFound("story");
    return HttpResponse.json<StoryArticles>({
      items: articlesByStory.get(id) ?? [],
      methodology_url: "/methodology#stance",
    });
  }),

  http.get(`${API_BASE}/blindspots`, ({ request }) => {
    const type =
      new URL(request.url).searchParams.get("type") === "language"
        ? "language"
        : "bias";
    return HttpResponse.json<Blindspots>({
      type,
      items: stories.filter((s) => s.blindspot?.type === type),
      methodology_url: "/methodology#blindspots",
    });
  }),

  http.get(`${API_BASE}/sources/:id`, ({ params }) => {
    const detail = sourceDetail(String(params.id));
    return detail ? HttpResponse.json(detail) : notFound("source");
  }),

  http.get(`${API_BASE}/methodology`, () =>
    HttpResponse.json<Methodology>({
      min_sources_for_bar: 4,
      min_sources_for_blindspot: 6,
      blindspot_bias_share: 0.7,
      blindspot_language_share: 0.9,
      feed_min_sources: 2,
      raters: [
        {
          rater: "Example Rater",
          dimension: "factuality",
          method_url: "https://rater.example/method",
          sources_rated: 3,
        },
      ],
    }),
  ),

  http.get(`${API_BASE}/topics`, ({ request }) => {
    const lang =
      new URL(request.url).searchParams.get("lang") === "hi" ? "hi" : "en";
    return HttpResponse.json<{ items: Topic[] }>({
      items: topics.map((t) => ({ slug: t.slug, name: t.name[lang] })),
    });
  }),
  http.post(`${API_BASE}/ask`, async ({ request }) => {
    const { query } = (await request.json()) as { query: string };
    const q = query.toLowerCase();
    if (q.includes("too fast")) {
      return HttpResponse.json(
        {
          error: {
            code: "rate_limited",
            message: "Too many questions.",
            retry_after_s: 12,
          },
        },
        { status: 429, headers: { "retry-after": "12" } },
      );
    }
    if (q.includes("slogan")) return sse(askAbstain("out_of_scope"));
    if (q.includes("riot"))
      return sse(
        askAbstain("sensitive_topic_under_review", stories.slice(1, 2)),
      );
    if (q.includes("cricket"))
      return sse(askAbstain("insufficient_coverage", stories.slice(0, 2)));
    return sse(askAnswer(q.includes("rigging")));
  }),
];
