import type {
  AskEventName,
  AskEvents,
  Blindspots,
  Methodology,
  Page,
  SourceDetail,
  StoryArticles,
  StoryCard,
  StoryDetail,
  Topic,
} from "./types";

/** Base URL for the Lens API (docs/09). Paths are prefixed with /api/v1. */
export const API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1`;

export class ApiRequestError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly retryAfterS: number | null = null,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

type Query = Record<string, string | number | undefined | null>;

function url(path: string, query: Query = {}): string {
  const u = new URL(`${API_BASE}${path}`);
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== "")
      u.searchParams.set(k, String(v));
  }
  return u.toString();
}

async function get<T>(
  path: string,
  query?: Query,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(url(path, query), { cache: "no-store", ...init });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiRequestError(
      res.status,
      body?.error?.code ?? "http_error",
      body?.error?.message ?? res.statusText,
    );
  }
  return res.json() as Promise<T>;
}

export function getHealth() {
  return get<{ status: string; version: string; env: string }>("/health");
}

export type FeedParams = {
  tab?: "home" | "blindspot" | "local";
  topic?: string;
  lang?: string;
  cursor?: string;
};

export function getFeed(params: FeedParams = {}) {
  return get<Page<StoryCard>>("/feed", params);
}

/** Accepts the story id or slug. */
export async function getStory(
  idOrSlug: string,
  lang?: string,
): Promise<StoryDetail | null> {
  try {
    return await get<StoryDetail>(`/stories/${encodeURIComponent(idOrSlug)}`, {
      lang,
    });
  } catch (e) {
    if (e instanceof ApiRequestError && e.status === 404) return null;
    throw e;
  }
}

export function getStoryArticles(
  id: string,
  params: { group?: "bias" | "language" | "all" } = {},
) {
  return get<StoryArticles>(
    `/stories/${encodeURIComponent(id)}/articles`,
    params,
  );
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

/** Accepts the source id or slug. */
export async function getSource(
  idOrSlug: string,
): Promise<SourceDetail | null> {
  try {
    return await get<SourceDetail>(`/sources/${encodeURIComponent(idOrSlug)}`);
  } catch (e) {
    if (e instanceof ApiRequestError && e.status === 404) return null;
    throw e;
  }
}

export type AskEvent = {
  [K in AskEventName]: { event: K; data: AskEvents[K] };
}[AskEventName];

/** Parses one SSE block ("event: x" / "data: y" lines). Comments (keep-alives) and unknown events are skipped. */
export function parseSseBlock(block: string): AskEvent | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith(":")) continue;
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:"))
      data.push(line.slice(5).replace(/^ /, ""));
  }
  if (
    !data.length ||
    ![
      "status",
      "understanding",
      "evidence",
      "answer_final",
      "abstain",
      "error",
    ].includes(event)
  ) {
    return null;
  }
  return { event, data: JSON.parse(data.join("\n")) } as AskEvent;
}

/**
 * POST /ask and stream its events (docs/09). EventSource cannot POST, so the body is read and split
 * on blank lines. A 429 or other non-stream error throws ApiRequestError before any event.
 */
export async function askStream(
  body: { query: string; lang?: string },
  onEvent: (e: AskEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  await (globalThis as { __lensMocksReady?: Promise<unknown> })
    .__lensMocksReady; // fixtures only (MockProvider)
  const res = await fetch(`${API_BASE}/ask`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      accept: "text/event-stream",
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => null);
    throw new ApiRequestError(
      res.status,
      err?.error?.code ?? "http_error",
      err?.error?.message ?? res.statusText,
      err?.error?.retry_after_s ?? null,
    );
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += value.replace(/\r\n/g, "\n");
    let i: number;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const e = parseSseBlock(buf.slice(0, i));
      buf = buf.slice(i + 2);
      if (e) onEvent(e);
    }
  }
}
