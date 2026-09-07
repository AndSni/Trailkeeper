package com.asnidev.trailkeeper.ui.map

import android.annotation.SuppressLint
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.asnidev.trailkeeper.data.local.TaskEntity
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
private const val TASK_SRC = "tk-tasks"
private val LATVIA = LatLng(56.95, 24.6)

/** Holds the map + style handles once they're ready, plus a one-shot flag so
 * the camera only auto-fits the first time data arrives. */
private class MapHolder {
    var map: MapLibreMap? = null
    var style: Style? = null
    var fittedCamera = false
}

@Composable
fun ProjectMap(
    trails: List<TrailEntity>,
    tasks: List<TaskEntity>,
    hasLocationPermission: Boolean,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val holder = remember { MapHolder() }

    val mapView = remember {
        MapView(context).apply {
            onCreate(null)
            getMapAsync { map ->
                holder.map = map
                map.cameraPosition = CameraPosition.Builder().target(LATVIA).zoom(6.0).build()
                map.setStyle(Style.Builder().fromUri(STYLE_URL)) { style ->
                    holder.style = style
                    style.addSource(GeoJsonSource(TRAIL_SRC))
                    style.addSource(GeoJsonSource(TASK_SRC))
                    style.addLayer(
                        LineLayer("$TRAIL_SRC-line", TRAIL_SRC).withProperties(
                            PropertyFactory.lineColor("#3C5A31"),
                            PropertyFactory.lineWidth(3f),
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
                    enableLocation(context, map, style, hasLocationPermission)
                    pushData(holder, trails, tasks)
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
        update = { pushData(holder, trails, tasks) },
    )
}

private fun pushData(holder: MapHolder, trails: List<TrailEntity>, tasks: List<TaskEntity>) {
    val style = holder.style ?: return
    (style.getSource(TRAIL_SRC) as? GeoJsonSource)?.setGeoJson(MapGeo.trailFeatures(trails))
    (style.getSource(TASK_SRC) as? GeoJsonSource)?.setGeoJson(MapGeo.taskFeatures(tasks))

    if (!holder.fittedCamera) {
        val bounds = MapGeo.bounds(trails, tasks)
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
