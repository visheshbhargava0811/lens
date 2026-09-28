import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { stateAt, type StateShapes } from "@/lib/geo";

const shapes = JSON.parse(readFileSync("public/geo/india-states.json", "utf8")) as StateShapes;

describe("stateAt", () => {
  it.each([
    [77.21, 28.61, "delhi"], // Connaught Place
    [72.83, 18.94, "maharashtra"], // Mumbai
    [80.27, 13.08, "tamil-nadu"], // Chennai
    [80.95, 26.85, "uttar-pradesh"], // Lucknow
    [77.59, 12.97, "karnataka"], // Bengaluru
    [88.36, 22.57, "west-bengal"], // Kolkata
  ])("%f,%f is %s", (lon, lat, slug) => expect(stateAt(lon, lat, shapes)).toBe(slug));

  it("is null outside India", () => {
    expect(stateAt(-0.13, 51.51, shapes)).toBeNull(); // London
    expect(stateAt(67.0, 24.86, shapes)).toBeNull(); // Karachi
  });

  it("covers all 36 states and union territories", () => expect(shapes.features).toHaveLength(36));
});
