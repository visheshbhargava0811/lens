import { describe, expect, it } from "vitest";

import en from "../../messages/en.json";
import hi from "../../messages/hi.json";

function keys(obj: object, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === "object" ? keys(v, `${prefix}${k}.`) : [`${prefix}${k}`],
  );
}

describe("UI strings", () => {
  it("Hindi has exactly the same keys as English", () => {
    expect(keys(hi).sort()).toEqual(keys(en).sort());
  });

  it("Hindi strings are not left in English", () => {
    const flat = (o: object): string[] =>
      Object.values(o).flatMap((v) => (typeof v === "object" ? flat(v) : [String(v)]));
    const untranslated = flat(hi.nav).filter((s) => /^[\x00-\x7F]+$/.test(s));
    expect(untranslated).toEqual([]);
  });
});
