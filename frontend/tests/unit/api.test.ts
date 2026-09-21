import { describe, expect, it } from "vitest";

import { getHealth } from "@/lib/api/client";

describe("API client (MSW fixtures)", () => {
  it("reads /health from the mock server", async () => {
    await expect(getHealth()).resolves.toMatchObject({ status: "ok" });
  });
});
