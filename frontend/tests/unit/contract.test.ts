/**
 * G-BIAS-01 contract test (docs/07, docs/09): any bias or factuality figure the API
 * returns carries a confidence level, and a methodology link is reachable from the same response.
 */
import { describe, expect, it } from "vitest";

import { API_BASE } from "@/lib/api/client";
import { stories } from "@/mocks/fixtures";

type Json = null | boolean | number | string | Json[] | { [k: string]: Json };

function violations(node: Json, path = "$", inherited = false): string[] {
  if (Array.isArray(node)) return node.flatMap((n, i) => violations(n, `${path}[${i}]`, inherited));
  if (!node || typeof node !== "object") return [];
  const hasMethod = inherited || typeof node.methodology_url === "string";
  const out: string[] = [];
  for (const key of ["coverage", "factuality", "source_bias", "source_factuality"] as const) {
    const v = node[key];
    if (v && typeof v === "object" && !Array.isArray(v)) {
      if (typeof v.confidence !== "string") out.push(`${path}.${key}: missing confidence`);
      if (typeof v.methodology_url !== "string" && typeof v.method_url !== "string")
        out.push(`${path}.${key}: missing methodology link`);
    }
  }
  for (const [k, v] of Object.entries(node)) out.push(...violations(v, `${path}.${k}`, hasMethod));
  return out;
}

async function getJson(path: string): Promise<Json> {
  const res = await fetch(`${API_BASE}${path}`);
  expect(res.ok).toBe(true);
  return res.json();
}

describe("G-BIAS-01: confidence and methodology on every figure", () => {
  it("feed pages", async () => {
    expect(violations(await getJson("/feed"))).toEqual([]);
    expect(violations(await getJson("/feed?cursor=8"))).toEqual([]);
  });

  it("blindspots", async () => {
    expect(violations(await getJson("/blindspots?type=bias"))).toEqual([]);
    expect(violations(await getJson("/blindspots?type=language"))).toEqual([]);
  });

  it.each(stories.map((s) => [s.slug, s.id]))("story %s and its articles", async (_slug, id) => {
    expect(violations(await getJson(`/stories/${id}`))).toEqual([]);
    expect(violations(await getJson(`/stories/${id}/articles`))).toEqual([]);
  });

  it("detects a violation (the checker itself works)", () => {
    const bad = { items: [{ coverage: { available: true, buckets: [] }, source_bias: { value: "Left" } }] } as Json;
    expect(violations(bad).length).toBeGreaterThanOrEqual(3);
  });
});

describe("fixtures cover the Phase 1B cases (docs/12)", () => {
  it("has normal, limited, bias and language blindspot, Hindi headlines, unrated and syndicated", async () => {
    expect(stories.some((s) => s.coverage.available)).toBe(true);
    expect(stories.some((s) => !s.coverage.available)).toBe(true);
    expect(stories.some((s) => s.blindspot?.type === "bias")).toBe(true);
    expect(stories.some((s) => s.blindspot?.type === "language")).toBe(true);
    expect(stories.some((s) => s.headline_lang === "hi")).toBe(true);
    expect(stories.some((s) => s.factuality.unrated > 0)).toBe(true);
    const rows = (await getJson(`/stories/${stories[0].id}/articles`)) as { items: { is_syndicated: boolean }[] };
    expect(rows.items.some((r) => r.is_syndicated)).toBe(true);
  });

  it("empty and error responses exist", async () => {
    const empty = (await getJson("/feed?topic=entertainment")) as { items: unknown[] };
    expect(empty.items).toEqual([]);
    const err = await fetch(`${API_BASE}/feed?topic=fixture-error`);
    expect(err.status).toBe(500);
    expect(await err.json()).toMatchObject({ error: { code: expect.any(String), message: expect.any(String) } });
  });

  it("feed counts agree with coverage buckets", () => {
    for (const s of stories) {
      if (!s.coverage.available) continue;
      const total = s.coverage.buckets.reduce((a, b) => a + b.sources, 0) + s.coverage.unrated.sources;
      expect(total, s.slug).toBe(s.counts.sources);
    }
  });
});
