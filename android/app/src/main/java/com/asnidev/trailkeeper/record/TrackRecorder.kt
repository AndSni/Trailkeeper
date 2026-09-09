package com.asnidev.trailkeeper.record

import com.asnidev.trailkeeper.data.SyncRepository
import com.asnidev.trailkeeper.network.TrackCreateRequest
import com.asnidev.trailkeeper.network.TrackPointDto
import java.time.Instant
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

enum class RecPhase { IDLE, RECORDING, PAUSED, STOPPED }

data class RecPoint(val lat: Double, val lon: Double, val ele: Double?, val tMillis: Long)

data class RecorderState(
    val phase: RecPhase = RecPhase.IDLE,
    val projectId: String? = null,
    val startedAtMillis: Long = 0L,
    val points: List<RecPoint> = emptyList(),
    val distanceM: Double = 0.0,
    /** Un-paused wall time, updated once a second while RECORDING. */
    val movingMillis: Long = 0L,
    val lastFixMillis: Long = 0L,
) {
    val pointCount get() = points.size
}

/**
 * Holds the live state of a route recording. [TrackRecordingService] owns the
 * GPS client and feeds [onLocation]; the UI observes [state] and calls
 * start / pause / resume / stop / save. A plain object so the service and any
 * screen share one instance (matches Session / SyncRepository).
 */
object TrackRecorder {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    private val _state = MutableStateFlow(RecorderState())
    val state: StateFlow<RecorderState> = _state.asStateFlow()

    private var segmentStartMillis = 0L
    private var accumulatedMillis = 0L
    private var ticker: Job? = null

    val isActive: Boolean
        get() = _state.value.phase in listOf(RecPhase.RECORDING, RecPhase.PAUSED)

    fun start(projectId: String) {
        val now = System.currentTimeMillis()
        segmentStartMillis = now
        accumulatedMillis = 0L
        _state.value =
            RecorderState(
                phase = RecPhase.RECORDING,
                projectId = projectId,
                startedAtMillis = now,
            )
        launchTicker()
    }

    fun pause() {
        if (_state.value.phase != RecPhase.RECORDING) return
        accumulatedMillis += System.currentTimeMillis() - segmentStartMillis
        ticker?.cancel()
        _state.update { it.copy(phase = RecPhase.PAUSED, movingMillis = accumulatedMillis) }
    }

    fun resume() {
        if (_state.value.phase != RecPhase.PAUSED) return
        segmentStartMillis = System.currentTimeMillis()
        _state.update { it.copy(phase = RecPhase.RECORDING) }
        launchTicker()
    }

    fun stop() {
        val phase = _state.value.phase
        if (phase == RecPhase.RECORDING) {
            accumulatedMillis += System.currentTimeMillis() - segmentStartMillis
        } else if (phase != RecPhase.PAUSED) {
            return
        }
        ticker?.cancel()
        _state.update { it.copy(phase = RecPhase.STOPPED, movingMillis = accumulatedMillis) }
    }

    /** Drop the recording without saving (Discard, or after a failed save). */
    fun reset() {
        ticker?.cancel()
        accumulatedMillis = 0L
        _state.value = RecorderState()
    }

    fun onLocation(lat: Double, lon: Double, ele: Double?, accuracyM: Float) {
        if (_state.value.phase != RecPhase.RECORDING) return
        if (accuracyM > 30f) return
        val now = System.currentTimeMillis()
        _state.update { s ->
            val prev = s.points.lastOrNull()
            val step = if (prev == null) 0.0 else haversineM(prev.lat, prev.lon, lat, lon)
            if (prev != null && step < 2.5) {
                s.copy(lastFixMillis = now)
            } else {
                s.copy(
                    points = s.points + RecPoint(lat, lon, ele, now),
                    distanceM = s.distanceM + step,
                    lastFixMillis = now,
                )
            }
        }
    }

    /** POST the recording, then clear. Throws on failure (caller keeps the
     * STOPPED state so the user can retry or discard). */
    suspend fun save(name: String, activity: String) {
        val s = _state.value
        val projectId = s.projectId ?: error("no project")
        SyncRepository.saveTrack(
            TrackCreateRequest(
                projectId = projectId,
                name = name.trim().ifBlank { "Route" },
                activity = activity,
                startedAt = Instant.ofEpochMilli(s.startedAtMillis).toString(),
                endedAt = Instant.ofEpochMilli(s.points.lastOrNull()?.tMillis ?: s.startedAtMillis)
                    .toString(),
                movingSeconds = (s.movingMillis / 1000).toInt(),
                points = s.points.map {
                    TrackPointDto(
                        lat = it.lat,
                        lon = it.lon,
                        ele = it.ele,
                        t = Instant.ofEpochMilli(it.tMillis).toString(),
                    )
                },
            )
        )
        reset()
    }

    private fun launchTicker() {
        ticker?.cancel()
        ticker =
            scope.launch {
                while (true) {
                    _state.update {
                        if (it.phase == RecPhase.RECORDING) {
                            it.copy(
                                movingMillis =
                                    accumulatedMillis + (System.currentTimeMillis() - segmentStartMillis)
                            )
                        } else {
                            it
                        }
                    }
                    delay(1000)
                }
            }
    }

    private fun haversineM(
        lat1: Double,
        lon1: Double,
        lat2: Double,
        lon2: Double,
    ): Double {
        val r = 6_371_000.0
        val dLat = Math.toRadians(lat2 - lat1)
        val dLon = Math.toRadians(lon2 - lon1)
        val a =
            sin(dLat / 2) * sin(dLat / 2) +
                cos(Math.toRadians(lat1)) * cos(Math.toRadians(lat2)) *
                sin(dLon / 2) * sin(dLon / 2)
        return r * 2 * atan2(sqrt(a), sqrt(1 - a))
    }
}
