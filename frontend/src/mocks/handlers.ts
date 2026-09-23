import { http, HttpResponse } from "msw";

import { API_BASE } from "@/lib/api/client";
import type { Blindspots, Methodology, Page, StoryArticles, StoryCard, Topic } from "@/lib/api/types";

import {
  articlesByStory,
  details,
  ERROR_STORY_SLUG,
  ERROR_TOPIC,
  FEED_PAGE_SIZE,
  slugToId,
  stories,
  topics,
} from "./fixtures";

const serverError = () =>
  HttpResponse.json(
    { error: { code: "fixture_error", message: "This fixture always fails, to test error states." } },
    { status: 500 },
  );

const notFound = (what: string) =>
  HttpResponse.json({ error: { code: "not_found", message: `No ${what} with that id.` } }, { status: 404 });

function resolveStoryId(idOrSlug: string): string | undefined {
  if (details.has(idOrSlug)) return idOrSlug;
  return slugToId.get(idOrSlug);
}

// Fixtures must match docs/09_API_SPEC.md exactly.
export const handlers = [
  http.get(`${API_BASE}/health`, () => HttpResponse.json({ status: "ok", version: "mock", env: "mock" })),

  http.get(`${API_BASE}/feed`, ({ request }) => {
    const q = new URL(request.url).searchParams;
    const topic = q.get("topic");
    if (topic === ERROR_TOPIC) return serverError();
    const filtered = !topic || topic === "top" ? stories : stories.filter((s) => s.topic === topic);
    const start = Number(q.get("cursor") ?? 0) || 0;
    const items = filtered.slice(start, start + FEED_PAGE_SIZE);
    const next = start + FEED_PAGE_SIZE < filtered.length ? String(start + FEED_PAGE_SIZE) : null;
    return HttpResponse.json<Page<StoryCard>>(
      { items, next_cursor: next },
      { headers: { "Cache-Control": "public, max-age=30, stale-while-revalidate=60" } },
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
    const type = new URL(request.url).searchParams.get("type") === "language" ? "language" : "stance";
    return HttpResponse.json<Blindspots>({
      type,
      items: stories.filter((s) => s.blindspot?.type === type),
      methodology_url: "/methodology#blindspots",
    });
  }),

  http.get(`${API_BASE}/methodology`, () =>
    HttpResponse.json<Methodology>({
      min_sources_for_bar: 4,
      min_sources_for_blindspot: 6,
      blindspot_stance_share: 0.7,
      blindspot_language_share: 0.9,
      feed_min_sources: 2,
      raters: [{ rater: "Example Rater", dimension: "factuality", method_url: "https://rater.example/method", sources_rated: 3 }],
    }),
  ),

  http.get(`${API_BASE}/topics`, ({ request }) => {
    const lang = new URL(request.url).searchParams.get("lang") === "hi" ? "hi" : "en";
    return HttpResponse.json<{ items: Topic[] }>({
      items: topics.map((t) => ({ slug: t.slug, name: t.name[lang] })),
    });
  }),
];
