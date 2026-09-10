import type { GeoJson, Snapshot } from "./api";

type Feature = {
  type: "Feature";
  geometry: GeoJson;
  properties: Record<string, unknown>;
};

function fc(features: Feature[]) {
  return { type: "FeatureCollection" as const, features };
}

export function trailFC(snap: Snapshot, dimmed?: Set<string>) {
  return fc(
    snap.trails
      .filter((t) => t.geometry)
      .map((t) => ({
        type: "Feature" as const,
        geometry: t.geometry as GeoJson,
        properties: {
          id: t.id,
          kind: "trail",
          status: t.status,
          dim: dimmed?.has(t.id) ?? false,
        },
      })),
  );
}

export function taskFC(snap: Snapshot) {
  return fc(
    snap.tasks
      .filter((t) => t.geometry)
      .map((t) => ({
        type: "Feature" as const,
        geometry: t.geometry as GeoJson,
        properties: { id: t.id, kind: "task", status: t.status, priority: t.priority },
      })),
  );
}

export function structureFC(snap: Snapshot, dimmed?: Set<string>) {
  return fc(
    snap.structures
      .filter((s) => s.geometry)
      .map((s) => ({
        type: "Feature" as const,
        geometry: s.geometry as GeoJson,
        properties: {
          id: s.id,
          kind: "structure",
          status: s.status,
          color: s.color || "",
          dim: dimmed?.has(s.id) ?? false,
        },
      })),
  );
}

export function trackFC(snap: Snapshot) {
  return fc(
    snap.tracks
      .filter((t) => t.geometry)
      .map((t) => ({
        type: "Feature" as const,
        geometry: t.geometry as GeoJson,
        properties: { id: t.id, kind: "track", source: t.source },
      })),
  );
}

function eachCoord(geom: GeoJson, cb: (lng: number, lat: number) => void) {
  const c = geom.coordinates as number[] | number[][] | number[][][];
  if (geom.type === "Point") cb((c as number[])[0], (c as number[])[1]);
  else if (geom.type === "LineString")
    (c as number[][]).forEach((p) => cb(p[0], p[1]));
  else if (geom.type === "MultiLineString" || geom.type === "Polygon")
    (c as number[][][]).forEach((line) => line.forEach((p) => cb(p[0], p[1])));
}

export type Bounds = [[number, number], [number, number]];

export function boundsOf(geoms: (GeoJson | null)[]): Bounds | null {
  let minLng = Infinity,
    minLat = Infinity,
    maxLng = -Infinity,
    maxLat = -Infinity;
  let any = false;
  for (const g of geoms) {
    if (!g) continue;
    eachCoord(g, (lng, lat) => {
      any = true;
      minLng = Math.min(minLng, lng);
      minLat = Math.min(minLat, lat);
      maxLng = Math.max(maxLng, lng);
      maxLat = Math.max(maxLat, lat);
    });
  }
  return any ? [[minLng, minLat], [maxLng, maxLat]] : null;
}

export function centerOf(geom: GeoJson): [number, number] | null {
  const b = boundsOf([geom]);
  if (!b) return null;
  return [(b[0][0] + b[1][0]) / 2, (b[0][1] + b[1][1]) / 2];
}

export interface ProjectScope {
  trailIds: Set<string>;
  structureIds: Set<string>;
  bounds: Bounds | null;
}

function padBounds(b: Bounds, frac: number): Bounds {
  const [[minLng, minLat], [maxLng, maxLat]] = b;
  const lngPad = (maxLng - minLng) * frac + 0.0005;
  const latPad = (maxLat - minLat) * frac + 0.0005;
  return [
    [minLng - lngPad, minLat - latPad],
    [maxLng + lngPad, maxLat + latPad],
  ];
}

function anyCoordIn(geom: GeoJson | null, b: Bounds): boolean {
  if (!geom) return false;
  let inside = false;
  eachCoord(geom, (lng, lat) => {
    if (lng >= b[0][0] && lng <= b[1][0] && lat >= b[0][1] && lat <= b[1][1]) inside = true;
  });
  return inside;
}

/**
 * Trails and structures are org-wide (shared between projects), but a project's
 * map should be about the place it works. The working area is the extent of the
 * project's tasks + recorded tracks + the trails its tasks attach to; a trail or
 * structure is "in scope" when it's attached to a task or falls inside that
 * padded extent. A project with nothing placed yet scopes everything (so the
 * map falls back to the org extent and nothing is dimmed).
 */
export function projectScope(snap: Snapshot): ProjectScope {
  const attached = new Set(
    snap.tasks.map((t) => t.nearest_trail_id).filter((x): x is string => !!x),
  );
  const raw = boundsOf([
    ...snap.tasks.map((t) => t.geometry),
    ...snap.tracks.map((t) => t.geometry),
    ...snap.trails.filter((t) => attached.has(t.id)).map((t) => t.geometry),
  ]);
  if (!raw) {
    return {
      trailIds: new Set(snap.trails.map((t) => t.id)),
      structureIds: new Set(snap.structures.map((s) => s.id)),
      bounds: null,
    };
  }
  const padded = padBounds(raw, 0.25);
  const trailIds = new Set<string>(attached);
  for (const t of snap.trails) if (anyCoordIn(t.geometry, padded)) trailIds.add(t.id);
  const structureIds = new Set<string>();
  for (const s of snap.structures) if (anyCoordIn(s.geometry, padded)) structureIds.add(s.id);
  return { trailIds, structureIds, bounds: padded };
}
