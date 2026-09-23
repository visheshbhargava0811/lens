import { describe, expect, it } from "vitest";

import { getHealth } from "@/lib/api/client";

describe("API client (MSW fixtures)", () => {
  it("reads /health from the mock server", async () => {
    await expect(getHealth()).resolves.toMatchObject({ status: "ok" });
  });
});

describe("/ask SSE", () => {
  it("parses event blocks and skips keep-alive comments", async () => {
    const { parseSseBlock } = await import("@/lib/api/client");
    expect(parseSseBlock(": ping")).toBeNull();
    expect(parseSseBlock('event: status\ndata: {"step":"searching","message":"m"}')).toEqual({
      event: "status",
      data: { step: "searching", message: "m" },
    });
    expect(parseSseBlock('event: unknown\ndata: {}')).toBeNull();
  });

  it("streams a verified answer from the fixture, and a 429 as an error with retry-after", async () => {
    const { ApiRequestError, askStream } = await import("@/lib/api/client");
    const events: string[] = [];
    await askStream({ query: "what happened" }, (e) => events.push(e.event));
    expect(events[0]).toBe("status");
    expect(events.at(-1)).toBe("answer_final");
    const err = await askStream({ query: "too fast" }, () => {}).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiRequestError);
    expect((err as InstanceType<typeof ApiRequestError>).retryAfterS).toBe(12);
  });
});
