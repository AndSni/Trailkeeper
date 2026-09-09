package com.asnidev.trailkeeper.ui.record

import android.annotation.SuppressLint
import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import com.asnidev.trailkeeper.data.SyncRepository
import com.asnidev.trailkeeper.data.local.TrackEntity
import com.asnidev.trailkeeper.data.local.TrailkeeperDb
import com.asnidev.trailkeeper.record.RecPhase
import com.asnidev.trailkeeper.record.TrackRecorder
import com.asnidev.trailkeeper.record.TrackRecordingService
import com.google.android.gms.location.LocationServices
import kotlin.coroutines.resume
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine

private val PRIORITIES = listOf("low", "medium", "high", "urgent")

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun RouteTab(projectId: String, activity: String, hasLocation: Boolean) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val rec by TrackRecorder.state.collectAsState()
    val tracks by remember(projectId) {
        TrailkeeperDb.db.trackDao().observeForProject(projectId)
    }.collectAsState(initial = emptyList())

    var message by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    var showMark by remember { mutableStateOf(false) }
    var name by remember { mutableStateOf("") }

    Column(Modifier.fillMaxSize()) {
        message?.let {
            Surface(color = MaterialTheme.colorScheme.errorContainer, modifier = Modifier.fillMaxWidth()) {
                Row(Modifier.padding(horizontal = 16.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(it, Modifier.weight(1f), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onErrorContainer)
                    TextButton(onClick = { message = null }) { Text("Dismiss") }
                }
            }
        }

        LazyColumn(
            Modifier.fillMaxSize(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        when (rec.phase) {
                            RecPhase.IDLE ->
                                Button(
                                    onClick = { TrackRecordingService.start(context, projectId) },
                                    enabled = hasLocation,
                                    modifier = Modifier.fillMaxWidth(),
                                ) { Text(if (hasLocation) "Start recording" else "Location permission needed") }

                            RecPhase.RECORDING, RecPhase.PAUSED -> {
                                Text(
                                    fmtDuration(rec.movingMillis),
                                    style = MaterialTheme.typography.displaySmall,
                                    fontFamily = FontFamily.Monospace,
                                )
                                Text(
                                    "${fmtKm(rec.distanceM)} · ${rec.pointCount} points" +
                                        if (rec.phase == RecPhase.PAUSED) " · paused" else "",
                                    style = MaterialTheme.typography.labelMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    if (rec.phase == RecPhase.RECORDING) {
                                        OutlinedButton(onClick = { TrackRecordingService.pause(context) }) { Text("Pause") }
                                    } else {
                                        Button(onClick = { TrackRecordingService.resume(context) }) { Text("Resume") }
                                    }
                                    OutlinedButton(onClick = { TrackRecordingService.stop(context) }) { Text("Stop") }
                                    OutlinedButton(onClick = { showMark = true }) { Text("Mark spot") }
                                }
                            }

                            RecPhase.STOPPED -> {
                                Text("Recorded route", style = MaterialTheme.typography.titleSmall)
                                Text(
                                    "${fmtKm(rec.distanceM)} · ${fmtDuration(rec.movingMillis)} · ${rec.pointCount} points",
                                    style = MaterialTheme.typography.labelMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                                OutlinedTextField(
                                    value = name,
                                    onValueChange = { name = it },
                                    label = { Text("Name") },
                                    singleLine = true,
                                    modifier = Modifier.fillMaxWidth(),
                                )
                                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Button(
                                        enabled = !saving && rec.pointCount >= 2,
                                        onClick = {
                                            saving = true
                                            scope.launch {
                                                runCatching { TrackRecorder.save(name, activity) }
                                                    .onFailure { e -> message = e.message ?: "Couldn't save the route" }
                                                name = ""
                                                saving = false
                                            }
                                        },
                                    ) {
                                        if (saving) CircularProgressIndicator(Modifier.size(16.dp)) else Text("Save route")
                                    }
                                    OutlinedButton(enabled = !saving, onClick = { TrackRecorder.reset(); name = "" }) {
                                        Text("Discard")
                                    }
                                }
                                if (rec.pointCount < 2) {
                                    Text(
                                        "Too few GPS points to save.",
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.error,
                                    )
                                }
                            }
                        }
                    }
                }
            }

            item { HorizontalDivider() }

            if (tracks.isEmpty()) {
                item {
                    Text(
                        "No routes recorded for this project yet.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            } else {
                item { Text("Routes (${tracks.size})", style = MaterialTheme.typography.titleSmall) }
                items(tracks, key = { it.id }) { TrackCard(it) }
            }
        }
    }

    if (showMark) {
        MarkSpotDialog(
            onDismiss = { showMark = false },
            onMark = { title, priority ->
                showMark = false
                scope.launch {
                    val loc = lastLocation(context)
                    if (loc == null) {
                        message = "No GPS fix yet — try again in a moment."
                    } else {
                        runCatching {
                            SyncRepository.createTaskAt(projectId, title, priority, loc.latitude, loc.longitude)
                        }.onFailure { e -> message = e.message ?: "Couldn't create the task" }
                    }
                }
            },
        )
    }
}

@Composable
private fun TrackCard(t: TrackEntity) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SourceTag(t.source)
                Text(t.name, style = MaterialTheme.typography.titleMedium)
            }
            Text(
                "${fmtKm(t.lengthM)} · ${t.pointCount} points" +
                    (t.startedAt?.let { " · ${it.take(10)}" } ?: ""),
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun MarkSpotDialog(onDismiss: () -> Unit, onMark: (String, String) -> Unit) {
    var title by remember { mutableStateOf("") }
    var priority by remember { mutableStateOf("medium") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Mark spot as task") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(
                    "Creates a task at your current location.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                OutlinedTextField(value = title, onValueChange = { title = it }, label = { Text("Title") }, singleLine = true)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    PRIORITIES.forEach { p ->
                        FilterChip(selected = priority == p, onClick = { priority = p }, label = { Text(p) })
                    }
                }
            }
        },
        confirmButton = {
            TextButton(enabled = title.isNotBlank(), onClick = { onMark(title.trim(), priority) }) { Text("Mark") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun SourceTag(source: String) {
    val color = if (source == "imported") Color(0xFF2F6D7A) else Color(0xFF4C6B3C)
    Surface(color = color, shape = RoundedCornerShape(4.dp)) {
        Text(
            source.uppercase(),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onPrimary,
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
        )
    }
}

private fun fmtDuration(ms: Long): String {
    val s = ms / 1000
    val h = s / 3600
    val m = (s % 3600) / 60
    val sec = s % 60
    return if (h > 0) "%d:%02d:%02d".format(h, m, sec) else "%02d:%02d".format(m, sec)
}

private fun fmtKm(m: Double): String =
    if (m < 1000) "${m.toInt()} m" else "%.2f km".format(m / 1000.0)

@SuppressLint("MissingPermission")
private suspend fun lastLocation(context: Context): android.location.Location? =
    suspendCancellableCoroutine { cont ->
        LocationServices.getFusedLocationProviderClient(context).lastLocation
            .addOnSuccessListener { cont.resume(it) }
            .addOnFailureListener { cont.resume(null) }
    }
