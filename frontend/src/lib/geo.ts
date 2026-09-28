/** Coordinates to an Indian state on the device (Local tab): the raw position never leaves the browser.
 * Boundaries: DataMeet India, States/Admin2 (CC BY 4.0), simplified to 1.5% with mapshaper. */

type Ring = [number, number][];
type Geometry = { type: "Polygon"; coordinates: Ring[] } | { type: "MultiPolygon"; coordinates: Ring[][] };
export type StateShapes = { features: { properties: { slug: string }; geometry: Geometry }[] };

function inRing([x, y]: [number, number], ring: Ring): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function inPolygon(p: [number, number], rings: Ring[]): boolean {
  return inRing(p, rings[0]) && !rings.slice(1).some((hole) => inRing(p, hole));
}

/** State slug for a longitude/latitude, or null outside India (or in a gap left by simplification). */
export function stateAt(lon: number, lat: number, shapes: StateShapes): string | null {
  for (const f of shapes.features) {
    const polys = f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates;
    if (polys.some((rings) => inPolygon([lon, lat], rings))) return f.properties.slug;
  }
  return null;
}
