import type { GeoJson, Snapshot } from "./api";

type Feature = {
  type: "Feature";
  geometry: GeoJson;
  properties: Record<string, unknown>;
};

function fc(features: Feature[]) {
  return { type: "FeatureCollection" as const, features };
}

export function trailFC(snap: Snapshot) {
  return fc(
    snap.trails
      .filter((t) => t.geometry)
      .map((t) => ({
        type: "Feature" as const,
        geometry: t.geometry as GeoJson,
        properties: { id: t.id, kind: "trail", status: t.status },
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

export function structureFC(snap: Snapshot) {
  return fc(
    snap.structures
      .filter((s) => s.geometry)
      .map((s) => ({
        type: "Feature" as const,
        geometry: s.geometry as GeoJson,
        properties: { id: s.id, kind: "structure", status: s.status },
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
