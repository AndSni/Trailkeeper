package com.asnidev.trailkeeper.ui.segments

import android.annotation.SuppressLint
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.location.LocationComponentActivationOptions
import org.maplibre.android.location.modes.CameraMode
import org.maplibre.android.location.modes.RenderMode
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.Style
import org.maplibre.android.style.layers.CircleLayer
import org.maplibre.android.style.layers.LineLayer
import org.maplibre.android.style.layers.PropertyFactory
import org.maplibre.android.style.sources.GeoJsonSource

private const val STYLE_URL = "https://tiles.openfreemap.org/styles/liberty"
private const val LINE_SRC = "measure-line"
private const val PT_SRC = "measure-pts"

/**
 * Tap the map to trace what was worked - a line for length units, a polygon
 * for area units. On Done the vertices go back to the caller, which sends
 * the GeoJSON with `quantity_source="measured"`; the server does the real
 * `ST_Length` / `ST_Area`. The number shown here is a client-side estimate.
 */
@Composable
fun SegmentMeasureScreen(
    area: Boolean,
    hasLocation: Boolean,
    onDone: (List<Pair<Double, Double>>) -> Unit,
    onCancel: () -> Unit,
) {
    var points by remember { mutableStateOf<List<Pair<Double, Double>>>(emptyList()) }
    val enough = points.size >= (if (area) 3 else 2)
    val preview =
        if (!enough) "" else if (area) "≈ ${roughM2(points).toInt()} m²" else "≈ %.2f km".format(roughKm(points))

    Column(Modifier.fillMaxSize()) {
        Surface(tonalElevation = 2.dp) {
            Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    if (area) "Trace the worked area" else "Trace the worked line",
                    style = MaterialTheme.typography.titleSmall,
                )
                Text(
                    "${points.size} point${if (points.size == 1) "" else "s"}" +
                        if (preview.isNotEmpty()) " · $preview" else "",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(
                        onClick = { points = points.dropLast(1) },
                        enabled = points.isNotEmpty(),
                    ) { Text("Undo") }
                    Button(onClick = { onDone(points) }, enabled = enough) { Text("Done") }
                    OutlinedButton(onClick = onCancel) { Text("Cancel") }
                }
            }
        }
        MeasureMapView(
            points = points,
            area = area,
            hasLocation = hasLocation,
            onAdd = { lat, lon -> points = points + (lat to lon) },
            modifier = Modifier.fillMaxSize(),
        )
    }
}

@Composable
private fun MeasureMapView(
    points: List<Pair<Double, Double>>,
    area: Boolean,
    hasLocation: Boolean,
    onAdd: (Double, Double) -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val styleHolder = remember { arrayOfNulls<Style>(1) }
    val onAddState = remember { arrayOfNulls<(Double, Double) -> Unit>(1) }
    onAddState[0] = onAdd

    val mapView = remember {
        MapView(context).apply {
            onCreate(null)
            getMapAsync { map ->
                map.cameraPosition = CameraPosition.Builder().target(LatLng(56.95, 24.6)).zoom(6.0).build()
                map.setStyle(Style.Builder().fromUri(STYLE_URL)) { style ->
                    styleHolder[0] = style
                    style.addSource(GeoJsonSource(LINE_SRC))
                    style.addSource(GeoJsonSource(PT_SRC))
                    style.addLayer(
                        LineLayer("$LINE_SRC-l", LINE_SRC).withProperties(
                            PropertyFactory.lineColor("#B7791F"),
                            PropertyFactory.lineWidth(3f),
                            PropertyFactory.lineDasharray(arrayOf(2f, 1.5f)),
                        )
                    )
                    style.addLayer(
                        CircleLayer("$PT_SRC-c", PT_SRC).withProperties(
                            PropertyFactory.circleRadius(5f),
                            PropertyFactory.circleColor("#B7791F"),
                            PropertyFactory.circleStrokeWidth(2f),
                            PropertyFactory.circleStrokeColor("#FFFFFF"),
                        )
                    )
                    enableLocation(context, map, style, hasLocation)
                    pushMeasure(style, points, area)
                }
                map.addOnMapClickListener { p ->
                    onAddState[0]?.invoke(p.latitude, p.longitude)
                    true
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
        update = { styleHolder[0]?.let { pushMeasure(it, points, area) } },
    )
}

private fun pushMeasure(style: Style, points: List<Pair<Double, Double>>, area: Boolean) {
    val coords = points.joinToString(",") { (lat, lon) -> "[$lon,$lat]" }
    val lineJson =
        if (points.size < 2) """{"type":"FeatureCollection","features":[]}"""
        else if (area && points.size >= 3) {
            val ring = coords + "," + points.first().let { (lat, lon) -> "[$lon,$lat]" }
            """{"type":"Polygon","coordinates":[[$ring]]}"""
        } else {
            """{"type":"LineString","coordinates":[$coords]}"""
        }
    (style.getSource(LINE_SRC) as? GeoJsonSource)?.setGeoJson(lineJson)
    val ptFeatures =
        points.joinToString(",") { (lat, lon) ->
            """{"type":"Feature","geometry":{"type":"Point","coordinates":[$lon,$lat]},"properties":{}}"""
        }
    (style.getSource(PT_SRC) as? GeoJsonSource)
        ?.setGeoJson("""{"type":"FeatureCollection","features":[$ptFeatures]}""")
}

@SuppressLint("MissingPermission")
private fun enableLocation(
    context: android.content.Context,
    map: org.maplibre.android.maps.MapLibreMap,
    style: Style,
    hasPermission: Boolean,
) {
    if (!hasPermission) return
    val lc = map.locationComponent
    lc.activateLocationComponent(LocationComponentActivationOptions.builder(context, style).build())
    lc.isLocationComponentEnabled = true
    lc.renderMode = RenderMode.NORMAL
    lc.cameraMode = CameraMode.TRACKING
}

private fun roughKm(points: List<Pair<Double, Double>>): Double {
    val r = 6_371_000.0
    var m = 0.0
    for (i in 1 until points.size) {
        val (la1, lo1) = points[i - 1]
        val (la2, lo2) = points[i]
        val dLat = Math.toRadians(la2 - la1)
        val dLon = Math.toRadians(lo2 - lo1)
        val a =
            sin(dLat / 2) * sin(dLat / 2) +
                cos(Math.toRadians(la1)) * cos(Math.toRadians(la2)) * sin(dLon / 2) * sin(dLon / 2)
        m += r * 2 * atan2(sqrt(a), sqrt(1 - a))
    }
    return m / 1000.0
}

private fun roughM2(points: List<Pair<Double, Double>>): Double {
    val lat0 = points.sumOf { it.first } / points.size
    val mLat = 111_320.0
    val mLon = 111_320.0 * cos(Math.toRadians(lat0))
    val xy = points.map { (la, lo) -> lo * mLon to la * mLat }
    var s = 0.0
    for (i in xy.indices) {
        val (x1, y1) = xy[i]
        val (x2, y2) = xy[(i + 1) % xy.size]
        s += x1 * y2 - x2 * y1
    }
    return abs(s) / 2.0
}
