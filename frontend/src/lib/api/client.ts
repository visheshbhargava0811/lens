import type { Blindspots, Methodology, Page, StoryArticles, StoryCard, StoryDetail, Topic } from "./types";

/** Base URL for the Lens API (docs/09). Paths are prefixed with /api/v1. */
export const API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1`;

export class ApiRequestError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

type Query = Record<string, string | number | undefined | null>;

function url(path: string, query: Query = {}): string {
  const u = new URL(`${API_BASE}${path}`);
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== "") u.searchParams.set(k, String(v));
  }
  return u.toString();
}

async function get<T>(path: string, query?: Query, init?: RequestInit): Promise<T> {
  const res = await fetch(url(path, query), { cache: "no-store", ...init });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiRequestError(res.status, body?.error?.code ?? "http_error", body?.error?.message ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

export function getHealth() {
  return get<{ status: string; version: string; env: string }>("/health");
}

export type FeedParams = { tab?: "home" | "blindspot" | "local"; topic?: string; lang?: string; cursor?: string };

export function getFeed(params: FeedParams = {}) {
  return get<Page<StoryCard>>("/feed", params);
}

/** Accepts the story id or slug. */
export async function getStory(idOrSlug: string, lang?: string): Promise<StoryDetail | null> {
  try {
    return await get<StoryDetail>(`/stories/${encodeURIComponent(idOrSlug)}`, { lang });
  } catch (e) {
    if (e instanceof ApiRequestError && e.status === 404) return null;
    throw e;
  }
}

export function getStoryArticles(id: string, params: { group?: "bias" | "language" | "all" } = {}) {
  return get<StoryArticles>(`/stories/${encodeURIComponent(id)}/articles`, params);
}

export function getBlindspots(type: "bias" | "language", lang?: string) {
  return get<Blindspots>("/blindspots", { type, lang });
}

export function getTopics(lang?: string) {
  return get<{ items: Topic[] }>("/topics", { lang });
}

/** Live methodology parameters and raters. Null when the API is unreachable: the page prose still renders. */
export async function getMethodology(): Promise<Methodology | null> {
  try {
    return await get<Methodology>("/methodology");
  } catch {
    return null;
  }
}
