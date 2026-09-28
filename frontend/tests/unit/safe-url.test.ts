import { describe, expect, it } from "vitest";

import { safeUrl } from "@/lib/safe-url";

describe("safeUrl (XSS: only http(s) and our own paths are rendered)", () => {
  it("keeps web links and internal paths", () => {
    expect(safeUrl("https://www.thehindu.com/a?b=1")).toBe(
      "https://www.thehindu.com/a?b=1",
    );
    expect(safeUrl("http://example.org/x")).toBe("http://example.org/x");
    expect(safeUrl("/methodology#bias")).toBe("/methodology#bias");
  });
  it("drops script, data and protocol-relative URLs", () => {
    for (const bad of [
      "javascript:alert(1)",
      "JaVaScRiPt:alert(1)",
      " javascript:alert(1)",
      "data:text/html,<script>x</script>",
      "vbscript:x",
      "//evil.example/x",
      "",
      null,
      undefined,
    ]) {
      expect(safeUrl(bad)).toBeUndefined();
    }
  });
});
