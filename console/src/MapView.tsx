import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import type { Snapshot } from "./api";
import { boundsOf, structureFC, taskFC, trackFC, trailFC } from "./geo";
import type { Bounds } from "./geo";

const STYLE_URL = "https://tiles.openfreemap.org/styles/liberty";
const EMPTY = { type: "FeatureCollection" as const, features: [] };

export interface FocusTarget {
  bounds?: Bounds;
  center?: [number, number];
  nonce: number;
}

export function MapView({
  snapshot,
  focus,
  picking = false,
  draft = null,
  onPick,
}: {
  snapshot: Snapshot | null;
  focus: FocusTarget | null;
  picking?: boolean;
  draft?: [number, number][] | null; // [lng, lat] vertices being drawn
  onPick?: (lngLat: [number, number]) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const readyRef = useRef(false);
  const fittedRef = useRef<string | null>(null);
  const onPickRef = useRef(onPick);
  onPickRef.current = onPick;

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: STYLE_URL,
      center: [24.6, 56.95],
      zoom: 6,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("click", (e) => onPickRef.current?.([e.lngLat.lng, e.lngLat.lat]));
    mapRef.current = map;

    map.on("load", () => {
      map.addSource("tk-trails", { type: "geojson", data: EMPTY });
      map.addSource("tk-tracks", { type: "geojson", data: EMPTY });
      map.addSource("tk-tasks", { type: "geojson", data: EMPTY });
      map.addSource("tk-structures", { type: "geojson", data: EMPTY });
      map.addSource("tk-draft-line", { type: "geojson", data: EMPTY });
      map.addSource("tk-draft-pts", { type: "geojson", data: EMPTY });
      map.addLayer({
        id: "tk-trails-line",
        type: "line",
        source: "tk-trails",
        paint: { "line-color": "#3c5a31", "line-width": 3 },
        layout: { "line-cap": "round", "line-join": "round" },
      });
      map.addLayer({
        id: "tk-tracks-line",
        type: "line",
        source: "tk-tracks",
        paint: { "line-color": "#6d4c9c", "line-width": 3, "line-dasharray": [1.5, 1] },
        layout: { "line-cap": "round", "line-join": "round" },
      });
      map.addLayer({
        id: "tk-structures-dot",
        type: "circle",
        source: "tk-structures",
        paint: {
          "circle-radius": 6,
          "circle-color": "#2f6d7a",
          "circle-stroke-width": 2,
          "circle-stroke-color": "#fff",
        },
      });
      map.addLayer({
        id: "tk-tasks-dot",
        type: "circle",
        source: "tk-tasks",
        paint: {
          "circle-radius": 6,
          "circle-color": "#d6a64b",
          "circle-stroke-width": 2,
          "circle-stroke-color": "#fff",
        },
      });
      map.addLayer({
        id: "tk-draft-line",
        type: "line",
        source: "tk-draft-line",
        paint: { "line-color": "#b7791f", "line-width": 3, "line-dasharray": [2, 1.5] },
      });
      map.addLayer({
        id: "tk-draft-pts",
        type: "circle",
        source: "tk-draft-pts",
        paint: {
          "circle-radius": 4,
          "circle-color": "#b7791f",
          "circle-stroke-width": 1.5,
          "circle-stroke-color": "#fff",
        },
      });
      readyRef.current = true;
      pushData();
      pushDraft();
    });

    return () => {
      map.remove();
      mapRef.current = null;
      readyRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function pushData() {
    const map = mapRef.current;
    if (!map || !readyRef.current || !snapshot) return;
    (map.getSource("tk-trails") as maplibregl.GeoJSONSource)?.setData(trailFC(snapshot) as never);
    (map.getSource("tk-tracks") as maplibregl.GeoJSONSource)?.setData(trackFC(snapshot) as never);
    (map.getSource("tk-tasks") as maplibregl.GeoJSONSource)?.setData(taskFC(snapshot) as never);
    (map.getSource("tk-structures") as maplibregl.GeoJSONSource)?.setData(
      structureFC(snapshot) as never,
    );

    if (fittedRef.current !== snapshot.project.id) {
      const b = boundsOf([
        ...snapshot.trails.map((t) => t.geometry),
        ...snapshot.tracks.map((t) => t.geometry),
        ...snapshot.tasks.map((t) => t.geometry),
        ...snapshot.structures.map((s) => s.geometry),
      ]);
      if (b) {
        map.fitBounds(b, { padding: 60, maxZoom: 15, duration: 600 });
        fittedRef.current = snapshot.project.id;
      }
    }
  }

  function pushDraft() {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    const pts = draft ?? [];
    (map.getSource("tk-draft-pts") as maplibregl.GeoJSONSource)?.setData({
      type: "FeatureCollection",
      features: pts.map((c) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: c },
        properties: {},
      })),
    } as never);
    (map.getSource("tk-draft-line") as maplibregl.GeoJSONSource)?.setData(
      (pts.length >= 2
        ? {
            type: "Feature",
            geometry: { type: "LineString", coordinates: pts },
            properties: {},
          }
        : EMPTY) as never,
    );
  }

  useEffect(pushData, [snapshot]);
  useEffect(pushDraft, [draft]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !focus) return;
    if (focus.bounds) map.fitBounds(focus.bounds, { padding: 80, maxZoom: 16, duration: 600 });
    else if (focus.center) map.flyTo({ center: focus.center, zoom: 16, duration: 600 });
  }, [focus]);

  useEffect(() => {
    const map = mapRef.current;
    if (map) map.getCanvas().style.cursor = picking ? "crosshair" : "";
  }, [picking]);

  return <div className="map" ref={containerRef} />;
}
