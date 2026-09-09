package com.asnidev.trailkeeper.ui.map

import com.asnidev.trailkeeper.data.local.StructureEntity
import com.asnidev.trailkeeper.data.local.TaskEntity
import com.asnidev.trailkeeper.data.local.TrackEntity
import com.asnidev.trailkeeper.data.local.TrailEntity
import com.google.gson.JsonArray
import com.google.gson.JsonParser
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.geometry.LatLngBounds

/** Turns the Room rows into GeoJSON the MapLibre `GeoJsonSource`s consume. */
object MapGeo {

    /** Which org-wide assets belong to a project's working area, plus the
     * camera extent to frame it. See [projectScope]. */
    data class ProjectScope(
        val trailIds: Set<String>,
        val structureIds: Set<String>,
        val bounds: LatLngBounds?,
    )

    fun trailFeatures(trails: List<TrailEntity>, dimmed: Set<String> = emptySet()): String =
        featureCollection(
            trails.mapNotNull { t ->
                t.geometryJson?.let { g ->
                    feature(
                        g,
                        """"id":${quote(t.id)},"kind":"trail","status":${quote(t.status)},"dim":${t.id in dimmed}""",
                    )
                }
            }
        )

    fun taskFeatures(tasks: List<TaskEntity>): String =
        featureCollection(
            tasks.mapNotNull { t ->
                t.geometryJson?.let { g ->
                    feature(
                        g,
                        """"id":${quote(t.id)},"kind":"task","priority":${quote(t.priority)},"status":${quote(t.status)}""",
                    )
                }
            }
        )

    fun structureFeatures(
        structures: List<StructureEntity>,
        dimmed: Set<String> = emptySet(),
    ): String =
        featureCollection(
            structures.mapNotNull { s ->
                s.geometryJson?.let { g ->
                    val colorProp = if (s.color.isNotBlank()) ""","color":${quote(s.color)}""" else ""
                    feature(
                        g,
                        """"id":${quote(s.id)},"kind":"structure","type":${quote(s.structureType)},"status":${quote(s.status)},"dim":${s.id in dimmed}$colorProp""",
                    )
                }
            }
        )

    fun trackFeatures(tracks: List<TrackEntity>): String =
        featureCollection(
            tracks.mapNotNull { t ->
                t.geometryJson?.let { g ->
                    feature(g, """"id":${quote(t.id)},"kind":"track","source":${quote(t.source)}""")
                }
            }
        )

    /** Bounds over every trail / track line, task point and structure point. */
    fun bounds(
        trails: List<TrailEntity>,
        tasks: List<TaskEntity>,
        structures: List<StructureEntity> = emptyList(),
        tracks: List<TrackEntity> = emptyList(),
    ): LatLngBounds? {
        val pts = ArrayList<LatLng>()
        (
            trails.mapNotNull { it.geometryJson } +
                tasks.mapNotNull { it.geometryJson } +
                structures.mapNotNull { it.geometryJson } +
                tracks.mapNotNull { it.geometryJson }
        ).forEach { collectPoints(it, pts) }
        if (pts.isEmpty()) return null
        return LatLngBounds.Builder().includes(pts).build()
    }

    /**
     * A project doesn't own trails or structures (they're org-wide, shared
     * between projects), but its map should still be about the place it works.
     * The working area is the extent of the project's own tasks + recorded
     * tracks + the trails its tasks are attached to; a trail or structure
     * counts as "this project's" when it's attached to a task or falls inside
     * that (padded) extent.
     */
    fun projectScope(
        trails: List<TrailEntity>,
        tasks: List<TaskEntity>,
        structures: List<StructureEntity>,
        tracks: List<TrackEntity>,
    ): ProjectScope {
        val attachedTrailIds = tasks.mapNotNull { it.nearestTrailId }.toSet()

        val extentPts = ArrayList<LatLng>()
        (
            tasks.mapNotNull { it.geometryJson } +
                tracks.mapNotNull { it.geometryJson } +
                trails.filter { it.id in attachedTrailIds }.mapNotNull { it.geometryJson }
        ).forEach { collectPoints(it, extentPts) }

        if (extentPts.isEmpty()) {
            // Nothing to focus on yet - treat the whole org layer as in-scope
            // so the map falls back to the org extent and nothing is dimmed.
            return ProjectScope(trails.map { it.id }.toSet(), structures.map { it.id }.toSet(), null)
        }

        val raw = LatLngBounds.Builder().includes(extentPts).build()
        val padded = padBounds(raw, 0.25)

        val trailIds =
            attachedTrailIds +
                trails.filter { it.geometryJson != null && anyPointIn(it.geometryJson, padded) }
                    .map { it.id }
        val structureIds =
            structures.filter { it.geometryJson != null && anyPointIn(it.geometryJson, padded) }
                .map { it.id }
                .toSet()

        return ProjectScope(trailIds, structureIds, padded)
    }

    // --- helpers ------------------------------------------------------------

    private fun feature(geometryJson: String, propsBody: String): String =
        """{"type":"Feature","geometry":$geometryJson,"properties":{$propsBody}}"""

    private fun featureCollection(features: List<String>): String =
        """{"type":"FeatureCollection","features":[${features.joinToString(",")}]}"""

    private fun quote(s: String) = "\"${s.replace("\"", "\\\"")}\""

    private fun padBounds(b: LatLngBounds, frac: Double): LatLngBounds {
        val north = b.latitudeNorth
        val south = b.latitudeSouth
        val east = b.longitudeEast
        val west = b.longitudeWest
        val latPad = (north - south) * frac + 0.0005
        val lonPad = (east - west) * frac + 0.0005
        return LatLngBounds.from(
            (north + latPad).coerceAtMost(90.0),
            east + lonPad,
            (south - latPad).coerceAtLeast(-90.0),
            west - lonPad,
        )
    }

    private fun anyPointIn(geometryJson: String, bounds: LatLngBounds): Boolean {
        val pts = ArrayList<LatLng>()
        collectPoints(geometryJson, pts)
        return pts.any { bounds.contains(it) }
    }

    private fun collectPoints(geometryJson: String, into: MutableList<LatLng>) {
        val geom = runCatching { JsonParser.parseString(geometryJson).asJsonObject }.getOrNull() ?: return
        val coords = geom.get("coordinates") as? JsonArray ?: return
        when (geom.get("type")?.asString) {
            "Point" -> pair(coords)?.let(into::add)
            "LineString" -> coords.forEach { p -> pair(p as? JsonArray)?.let(into::add) }
            "MultiLineString" ->
                coords.forEach { line ->
                    (line as? JsonArray)?.forEach { p -> pair(p as? JsonArray)?.let(into::add) }
                }
        }
    }

    private fun pair(a: JsonArray?): LatLng? {
        if (a == null || a.size() < 2) return null
        return LatLng(a[1].asDouble, a[0].asDouble) // GeoJSON is [lon, lat]
    }
}
