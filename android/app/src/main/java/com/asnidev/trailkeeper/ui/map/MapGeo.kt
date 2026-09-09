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

    fun trailFeatures(trails: List<TrailEntity>): String =
        featureCollection(
            trails.mapNotNull { t ->
                t.geometryJson?.let { g ->
                    feature(g, """"id":${quote(t.id)},"kind":"trail","status":${quote(t.status)}""")
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

    fun structureFeatures(structures: List<StructureEntity>): String =
        featureCollection(
            structures.mapNotNull { s ->
                s.geometryJson?.let { g ->
                    val colorProp = if (s.color.isNotBlank()) ""","color":${quote(s.color)}""" else ""
                    feature(
                        g,
                        """"id":${quote(s.id)},"kind":"structure","type":${quote(s.structureType)},"status":${quote(s.status)}$colorProp""",
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

    // --- helpers ------------------------------------------------------------

    private fun feature(geometryJson: String, propsBody: String): String =
        """{"type":"Feature","geometry":$geometryJson,"properties":{$propsBody}}"""

    private fun featureCollection(features: List<String>): String =
        """{"type":"FeatureCollection","features":[${features.joinToString(",")}]}"""

    private fun quote(s: String) = "\"${s.replace("\"", "\\\"")}\""

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
