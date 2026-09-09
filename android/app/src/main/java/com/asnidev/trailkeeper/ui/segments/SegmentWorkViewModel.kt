package com.asnidev.trailkeeper.ui.segments

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.asnidev.trailkeeper.data.SyncRepository
import com.asnidev.trailkeeper.data.local.JobTypeEntity
import com.asnidev.trailkeeper.data.local.TrailkeeperDb
import com.asnidev.trailkeeper.network.RollupDto
import com.asnidev.trailkeeper.network.SegmentWorkCreateRequest
import com.google.gson.JsonElement
import com.google.gson.JsonParser
import java.time.Instant
import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

enum class TimerPhase { IDLE, RUNNING, PAUSED, STOPPED }

data class TimerState(
    val phase: TimerPhase = TimerPhase.IDLE,
    val jobTypeId: String? = null,
    val activeSeconds: Long = 0,
)

data class SegmentRecordRow(
    val id: String,
    val jobLabel: String,
    val quantity: Double,
    val unit: String,
    val activeSeconds: Int,
    val crewSize: Int,
    val personHours: Double,
    val rateMinPerUnit: Double?,
    val vsExpectedMinPerUnit: Double?,
    val startedAt: String,
)

/**
 * Drives the on-phone segment timer (start / pause / resume / stop → save) and
 * reads recorded segments + the productivity rollup. The timer's un-paused
 * seconds are the billable "active" time; pause spans are kept so the server
 * has the full picture. Saving is online-only (BLUEPRINT sec 10).
 */
class SegmentWorkViewModel(private val projectId: String) : ViewModel() {
    private val db = TrailkeeperDb.db

    val jobTypes: StateFlow<List<JobTypeEntity>> =
        db.jobTypeDao()
            .observeAll()
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    val records: StateFlow<List<SegmentRecordRow>> =
        combine(
            db.segmentWorkDao().observeForProject(projectId),
            db.jobTypeDao().observeAll(),
        ) { recs, jts ->
            val labels = jts.associate { it.id to it.label }
            recs.map { r ->
                SegmentRecordRow(
                    id = r.id,
                    jobLabel = r.jobTypeId?.let { labels[it] } ?: "(job type)",
                    quantity = r.quantity,
                    unit = r.unit,
                    activeSeconds = r.activeSeconds,
                    crewSize = r.crewSize,
                    personHours = r.personHours,
                    rateMinPerUnit = r.rateMinPerUnit,
                    vsExpectedMinPerUnit = r.vsExpectedMinPerUnit,
                    startedAt = r.startedAt,
                )
            }
        }
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    private val _timer = MutableStateFlow(TimerState())
    val timer: StateFlow<TimerState> = _timer.asStateFlow()

    private val _message = MutableStateFlow<String?>(null)
    val message: StateFlow<String?> = _message.asStateFlow()

    private val _saving = MutableStateFlow(false)
    val saving: StateFlow<Boolean> = _saving.asStateFlow()

    /** A measured geometry captured on the map, and its client-side preview
     * (km for line units, m² for area units). Null = fall back to a manual
     * quantity. Cleared by [discard] / [clearMeasurement]. */
    private val _measuredGeometry = MutableStateFlow<JsonElement?>(null)
    val measuredGeometry: StateFlow<JsonElement?> = _measuredGeometry.asStateFlow()

    private val _measuredPreview = MutableStateFlow<Double?>(null)
    val measuredPreview: StateFlow<Double?> = _measuredPreview.asStateFlow()

    fun setMeasurement(points: List<Pair<Double, Double>>, area: Boolean) {
        if (points.size < 2) {
            clearMeasurement()
            return
        }
        val ring = if (area) points + points.first() else points
        val coords = ring.joinToString(",") { (lat, lon) -> "[$lon,$lat]" }
        val json =
            if (area) """{"type":"Polygon","coordinates":[[$coords]]}"""
            else """{"type":"LineString","coordinates":[$coords]}"""
        _measuredGeometry.value = JsonParser.parseString(json)
        _measuredPreview.value =
            if (area) polygonAreaM2(points) else lineLengthKm(points)
    }

    fun clearMeasurement() {
        _measuredGeometry.value = null
        _measuredPreview.value = null
    }

    val rollup = MutableStateFlow<RollupDto?>(null)
    val rollupGroupBy = MutableStateFlow("job_type")

    private var startEpoch = 0L
    private var pausedAccumMs = 0L
    private var pauseStart = 0L
    private var startedAtIso: String? = null
    private val pauses = mutableListOf<MutableMap<String, String>>()
    private var ticker: Job? = null

    fun selectJobType(id: String) {
        if (_timer.value.phase == TimerPhase.IDLE) _timer.update { it.copy(jobTypeId = id) }
    }

    fun jobType(id: String?): JobTypeEntity? = id?.let { j -> jobTypes.value.firstOrNull { it.id == j } }

    fun start() {
        val jt = _timer.value.jobTypeId ?: return
        startEpoch = System.currentTimeMillis()
        pausedAccumMs = 0
        startedAtIso = Instant.now().toString()
        pauses.clear()
        _timer.value = TimerState(TimerPhase.RUNNING, jt, 0)
        launchTicker()
    }

    fun pause() {
        if (_timer.value.phase != TimerPhase.RUNNING) return
        ticker?.cancel()
        pauseStart = System.currentTimeMillis()
        pauses.add(mutableMapOf("from" to Instant.now().toString()))
        _timer.update { it.copy(phase = TimerPhase.PAUSED, activeSeconds = computeActive()) }
    }

    fun resume() {
        if (_timer.value.phase != TimerPhase.PAUSED) return
        pausedAccumMs += System.currentTimeMillis() - pauseStart
        pauses.lastOrNull()?.put("to", Instant.now().toString())
        _timer.update { it.copy(phase = TimerPhase.RUNNING) }
        launchTicker()
    }

    fun stop() {
        when (_timer.value.phase) {
            TimerPhase.RUNNING -> ticker?.cancel()
            TimerPhase.PAUSED -> {
                pausedAccumMs += System.currentTimeMillis() - pauseStart
                pauses.lastOrNull()?.putIfAbsent("to", Instant.now().toString())
            }
            else -> return
        }
        _timer.update { it.copy(phase = TimerPhase.STOPPED, activeSeconds = computeActive()) }
    }

    fun discard() {
        ticker?.cancel()
        clearMeasurement()
        _timer.value = TimerState()
    }

    fun save(
        quantity: Double?,
        crewSize: Int,
        equipment: List<String>,
        notes: String,
        trailId: String?,
    ) {
        val st = _timer.value
        val jt = st.jobTypeId ?: return
        val startIso = startedAtIso ?: return
        val geometry = _measuredGeometry.value
        _saving.value = true
        viewModelScope.launch {
            runCatching {
                SyncRepository.logSegmentWork(
                    SegmentWorkCreateRequest(
                        projectId = projectId,
                        jobTypeId = jt,
                        trailId = trailId,
                        geometry = geometry,
                        quantity = if (geometry != null) null else quantity,
                        quantitySource = if (geometry != null) "measured" else "manual",
                        startedAt = startIso,
                        endedAt = Instant.now().toString(),
                        activeSeconds = st.activeSeconds.toInt(),
                        pauses = pauses.filter { it["from"] != null && it["to"] != null },
                        crewSize = crewSize,
                        equipment = equipment,
                        notes = notes,
                    )
                )
            }
                .onSuccess { discard() }
                .onFailure { e -> _message.value = e.message ?: "Couldn't save the record" }
            _saving.value = false
        }
    }

    fun loadRollup(groupBy: String = rollupGroupBy.value) {
        rollupGroupBy.value = groupBy
        viewModelScope.launch {
            runCatching { SyncRepository.segmentRollup(projectId, groupBy) }
                .onSuccess { rollup.value = it }
                .onFailure { e -> _message.value = e.message ?: "Couldn't load insights" }
        }
    }

    fun clearMessage() {
        _message.value = null
    }

    private fun computeActive(): Long =
        ((System.currentTimeMillis() - startEpoch - pausedAccumMs) / 1000).coerceAtLeast(0)

    private fun lineLengthKm(points: List<Pair<Double, Double>>): Double {
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

    private fun polygonAreaM2(points: List<Pair<Double, Double>>): Double {
        // Shoelace on a local equirectangular projection about the centroid.
        val lat0 = points.sumOf { it.first } / points.size
        val mPerDegLat = 111_320.0
        val mPerDegLon = 111_320.0 * cos(Math.toRadians(lat0))
        val xy = points.map { (la, lo) -> lo * mPerDegLon to la * mPerDegLat }
        var s = 0.0
        for (i in xy.indices) {
            val (x1, y1) = xy[i]
            val (x2, y2) = xy[(i + 1) % xy.size]
            s += x1 * y2 - x2 * y1
        }
        return abs(s) / 2.0
    }

    private fun launchTicker() {
        ticker?.cancel()
        ticker =
            viewModelScope.launch {
                while (true) {
                    _timer.update { it.copy(activeSeconds = computeActive()) }
                    delay(1000)
                }
            }
    }
}
