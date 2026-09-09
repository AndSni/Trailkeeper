package com.asnidev.trailkeeper.ui.map

import android.annotation.SuppressLint
import android.graphics.PointF
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.asnidev.trailkeeper.data.local.StructureEntity
import com.asnidev.trailkeeper.data.local.TaskEntity
import com.asnidev.trailkeeper.data.local.TrackEntity
import com.asnidev.trailkeeper.data.local.TrailEntity
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.location.LocationComponentActivationOptions
import org.maplibre.android.location.modes.CameraMode
import org.maplibre.android.location.modes.RenderMode
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.Style
import org.maplibre.android.style.layers.CircleLayer
import org.maplibre.android.style.layers.LineLayer
import org.maplibre.android.style.layers.Property
import org.maplibre.android.style.layers.PropertyFactory
import org.maplibre.android.style.sources.GeoJsonSource

private const val STYLE_URL = "https://tiles.openfreemap.org/styles/liberty"
private const val TRAIL_SRC = "tk-trails"
private const val TRACK_SRC = "tk-tracks"
private const val TASK_SRC = "tk-tasks"
private const val STRUCTURE_SRC = "tk-structures"
private val LATVIA = LatLng(56.95, 24.6)

/** (lat, lon, nonce) - bump the nonce to re-trigger a fly-to. */
typealias MapFocus = Triple<Double, Double, Long>

/** Holds the map + style handles once they're ready, plus a one-shot flag so
 * the camera only auto-fits the first time data arrives. */
private class MapHolder {
    var map: MapLibreMap? = null
    var style: Style? = null
    var fittedCamera = false
    var lastFocusNonce = 0L
}

@Composable
fun ProjectMap(
    trails: List<TrailEntity>,
    tasks: List<TaskEntity>,
    structures: List<StructureEntity>,
    tracks: List<TrackEntity>,
    hasLocationPermission: Boolean,
    modifier: Modifier = Modifier,
    focus: MapFocus? = null,
    onFeatureTap: (kind: String, id: String) -> Unit = { _, _ -> },
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val holder = remember { MapHolder() }
    val onTapHolder = remember { arrayOfNulls<(String, String) -> Unit>(1) }
    onTapHolder[0] = onFeatureTap

    val mapView = remember {
        MapView(context).apply {
            onCreate(null)
            getMapAsync { map ->
                holder.map = map
                map.cameraPosition = CameraPosition.Builder().target(LATVIA).zoom(6.0).build()
                map.addOnMapClickListener { latLng ->
                    val pt: PointF = map.projection.toScreenLocation(latLng)
                    val hit =
                        map.queryRenderedFeatures(
                            pt,
                            "$TASK_SRC-dot",
                            "$STRUCTURE_SRC-dot",
                            "$TRACK_SRC-line",
                            "$TRAIL_SRC-line",
                        ).firstOrNull { it.hasProperty("id") && it.hasProperty("kind") }
                    if (hit != null) {
                        onTapHolder[0]?.invoke(
                            hit.getStringProperty("kind"),
                            hit.getStringProperty("id"),
                        )
                        true
                    } else {
                        false
                    }
                }
                map.setStyle(Style.Builder().fromUri(STYLE_URL)) { style ->
                    holder.style = style
                    style.addSource(GeoJsonSource(TRAIL_SRC))
                    style.addSource(GeoJsonSource(TRACK_SRC))
                    style.addSource(GeoJsonSource(TASK_SRC))
                    style.addSource(GeoJsonSource(STRUCTURE_SRC))
                    style.addLayer(
                        LineLayer("$TRAIL_SRC-line", TRAIL_SRC).withProperties(
                            PropertyFactory.lineColor("#3C5A31"),
                            PropertyFactory.lineWidth(3f),
                            PropertyFactory.lineCap(Property.LINE_CAP_ROUND),
                            PropertyFactory.lineJoin(Property.LINE_JOIN_ROUND),
                        )
                    )
                    style.addLayer(
                        LineLayer("$TRACK_SRC-line", TRACK_SRC).withProperties(
                            PropertyFactory.lineColor("#6D4C9C"),
                            PropertyFactory.lineWidth(3f),
                            PropertyFactory.lineDasharray(arrayOf(1.5f, 1f)),
                            PropertyFactory.lineCap(Property.LINE_CAP_ROUND),
                            PropertyFactory.lineJoin(Property.LINE_JOIN_ROUND),
                        )
                    )
                    style.addLayer(
                        CircleLayer("$TASK_SRC-dot", TASK_SRC).withProperties(
                            PropertyFactory.circleRadius(6f),
                            PropertyFactory.circleColor("#D6A64B"),
                            PropertyFactory.circleStrokeWidth(2f),
                            PropertyFactory.circleStrokeColor("#FFFFFF"),
                        )
                    )
                    style.addLayer(
                        CircleLayer("$STRUCTURE_SRC-dot", STRUCTURE_SRC).withProperties(
                            PropertyFactory.circleRadius(6f),
                            PropertyFactory.circleColor("#2F6D7A"),
                            PropertyFactory.circleStrokeWidth(2f),
                            PropertyFactory.circleStrokeColor("#FFFFFF"),
                        )
                    )
                    enableLocation(context, map, style, hasLocationPermission)
                    pushData(holder, trails, tasks, structures, tracks)
                }
            }
        }
    }

    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_START -> mapView.onStart()
                Lifecycle.Event.ON_RESUME -> mapView.onResume()
                Lifecycle.Event.ON_PAUSE -> mapView.onPause()
                Lifecycle.Event.ON_STOP -> mapView.onStop()
                Lifecycle.Event.ON_DESTROY -> mapView.onDestroy()
                else -> Unit
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            mapView.onStop()
            mapView.onDestroy()
        }
    }

    AndroidView(
        factory = { mapView },
        modifier = modifier,
        update = {
            pushData(holder, trails, tasks, structures, tracks)
            if (focus != null && focus.third != holder.lastFocusNonce) {
                holder.lastFocusNonce = focus.third
                holder.map?.easeCamera(
                    CameraUpdateFactory.newLatLngZoom(LatLng(focus.first, focus.second), 16.0),
                    600,
                )
            }
        },
    )
}

private fun pushData(
    holder: MapHolder,
    trails: List<TrailEntity>,
    tasks: List<TaskEntity>,
    structures: List<StructureEntity>,
    tracks: List<TrackEntity>,
) {
    val style = holder.style ?: return
    (style.getSource(TRAIL_SRC) as? GeoJsonSource)?.setGeoJson(MapGeo.trailFeatures(trails))
    (style.getSource(TRACK_SRC) as? GeoJsonSource)?.setGeoJson(MapGeo.trackFeatures(tracks))
    (style.getSource(TASK_SRC) as? GeoJsonSource)?.setGeoJson(MapGeo.taskFeatures(tasks))
    (style.getSource(STRUCTURE_SRC) as? GeoJsonSource)
        ?.setGeoJson(MapGeo.structureFeatures(structures))

    if (!holder.fittedCamera) {
        val bounds = MapGeo.bounds(trails, tasks, structures, tracks)
        if (bounds != null) {
            holder.map?.easeCamera(CameraUpdateFactory.newLatLngBounds(bounds, 72), 500)
            holder.fittedCamera = true
        }
    }
}

@SuppressLint("MissingPermission")
private fun enableLocation(
    context: android.content.Context,
    map: MapLibreMap,
    style: Style,
    hasPermission: Boolean,
) {
    if (!hasPermission) return
    val lc = map.locationComponent
    lc.activateLocationComponent(
        LocationComponentActivationOptions.builder(context, style).build()
    )
    lc.isLocationComponentEnabled = true
    lc.renderMode = RenderMode.COMPASS
    lc.cameraMode = CameraMode.NONE
}
