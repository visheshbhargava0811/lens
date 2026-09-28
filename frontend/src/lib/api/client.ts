import type {
  AskEventName,
  AskEvents,
  Blindspots,
  MemoryView,
  MeState,
  Methodology,
  Page,
  SourceDetail,
  StoryArticles,
  StoryCard,
  StoryChanges,
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
  await (globalThis as { __lensMocksReady?: Promise<unknown> }).__lensMocksReady; // browser fixtures only (MockProvider)
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
  state?: string;
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
/**
 * /me (docs/11, ADR-0041): the anonymous profile lives in an httpOnly cookie, so these run in the browser with
 * credentials. Writes send `X-Lens-Client`, which a cross-site page cannot add (CSRF).
 */
async function me<T>(method: string, path: string, body?: unknown): Promise<T> {
  await (globalThis as { __lensMocksReady?: Promise<unknown> }).__lensMocksReady; // fixtures only (MockProvider)
  const res = await fetch(`${API_BASE}/me${path}`, {
    method,
    credentials: "include",
    cache: "no-store",
    headers: {
      ...(method === "GET" ? {} : { "X-Lens-Client": "web" }),
      ...(body === undefined ? {} : { "content-type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new ApiRequestError(
      res.status,
      "http_error",
      err?.detail ?? res.statusText,
    );
  }
  return (res.status === 204 ? null : res.json()) as Promise<T>;
}

export const getMe = () => me<MeState>("GET", "");
export const giveConsent = () => me<MeState>("POST", "/consent");
export const putPreference = (key: string, value: string | string[]) =>
  me<MeState>("PUT", "/preferences", { key, value });
export const getMemory = () => me<MemoryView>("GET", "/memory");
export const deleteEverything = () => me<null>("DELETE", "/memory");
export const deletePreference = (key: string) =>
  me<null>("DELETE", `/memory/preferences/${key}`);
export const deleteView = (id: string) =>
  me<null>("DELETE", `/memory/views/${id}`);
export const deleteAsk = (id: string) =>
  me<null>("DELETE", `/memory/asks/${id}`);
/** Records a story view; returns what changed since the previous one (null on a first visit). */
export const recordView = (storyId: string) =>
  me<StoryChanges | null>("POST", `/views/${storyId}`);
export const getForYou = () => me<Page<StoryCard>>("GET", "/feed");

export async function askStream(
  body: { query: string; lang?: string; session_id?: string },
  onEvent: (e: AskEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  await (globalThis as { __lensMocksReady?: Promise<unknown> })
    .__lensMocksReady; // fixtures only (MockProvider)
  const res = await fetch(`${API_BASE}/ask`, {
    method: "POST",
    credentials: "include", // the /me cookie: consented readers get their preferences and history (docs/11)
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
