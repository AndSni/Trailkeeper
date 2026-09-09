package com.asnidev.trailkeeper.ui.segments

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
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
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.text.KeyboardOptions
import com.asnidev.trailkeeper.data.local.TrailEntity
import com.asnidev.trailkeeper.network.RollupGroupDto

private val GROUP_BYS = listOf("job_type" to "Job type", "trail" to "Trail", "member" to "Member", "week" to "Week")

@Composable
fun SegmentWorkTab(vm: SegmentWorkViewModel, trails: List<TrailEntity>, hasLocation: Boolean) {
    val jobTypes by vm.jobTypes.collectAsState()
    val timer by vm.timer.collectAsState()
    val records by vm.records.collectAsState()
    val rollup by vm.rollup.collectAsState()
    val groupBy by vm.rollupGroupBy.collectAsState()
    val saving by vm.saving.collectAsState()
    val message by vm.message.collectAsState()
    var measuring by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) { vm.loadRollup() }

    if (measuring) {
        val unit = jobTypes.firstOrNull { it.id == timer.jobTypeId }?.unit ?: ""
        SegmentMeasureScreen(
            area = unit == "m2",
            hasLocation = hasLocation,
            onDone = { pts ->
                vm.setMeasurement(pts, area = unit == "m2")
                measuring = false
            },
            onCancel = { measuring = false },
        )
        return
    }

    Column(Modifier.fillMaxSize()) {
        message?.let {
            Surface(color = MaterialTheme.colorScheme.errorContainer, modifier = Modifier.fillMaxWidth()) {
                Row(
                    Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        it,
                        Modifier.weight(1f),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onErrorContainer,
                    )
                    TextButton(onClick = vm::clearMessage) { Text("Dismiss") }
                }
            }
        }

        if (jobTypes.isEmpty()) {
            Box(Modifier.fillMaxSize().padding(32.dp), contentAlignment = Alignment.Center) {
                Text(
                    "No job types yet. An org admin defines them (8 are seeded on registration).",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            return
        }

        LazyColumn(
            Modifier.fillMaxSize(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item { TimerCard(vm, timer, jobTypes, trails, saving, onMeasure = { measuring = true }) }
            item { HorizontalDivider() }
            item { InsightsSection(rollup?.groups ?: emptyList(), groupBy, onGroupBy = vm::loadRollup) }
            if (records.isNotEmpty()) {
                item {
                    Text(
                        "Recorded work (${records.size})",
                        style = MaterialTheme.typography.titleSmall,
                    )
                }
                items(records, key = { it.id }) { RecordCard(it) }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun TimerCard(
    vm: SegmentWorkViewModel,
    timer: TimerState,
    jobTypes: List<com.asnidev.trailkeeper.data.local.JobTypeEntity>,
    trails: List<TrailEntity>,
    saving: Boolean,
    onMeasure: () -> Unit,
) {
    val selected = jobTypes.firstOrNull { it.id == timer.jobTypeId }
    var menuOpen by remember { mutableStateOf(false) }

    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Box {
                OutlinedButton(
                    onClick = { menuOpen = true },
                    enabled = timer.phase == TimerPhase.IDLE,
                ) {
                    Text(selected?.let { "${it.label} · ${it.unit}" } ?: "Pick a job type")
                }
                DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                    jobTypes.forEach { jt ->
                        DropdownMenuItem(
                            text = { Text("${jt.label} · ${jt.unit}") },
                            onClick = {
                                vm.selectJobType(jt.id)
                                menuOpen = false
                            },
                        )
                    }
                }
            }

            Text(
                fmtDuration(timer.activeSeconds),
                style = MaterialTheme.typography.displaySmall,
                fontFamily = FontFamily.Monospace,
            )

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                when (timer.phase) {
                    TimerPhase.IDLE ->
                        Button(onClick = vm::start, enabled = timer.jobTypeId != null) { Text("Start") }
                    TimerPhase.RUNNING -> {
                        OutlinedButton(onClick = vm::pause) { Text("Pause") }
                        Button(onClick = vm::stop) { Text("Stop") }
                    }
                    TimerPhase.PAUSED -> {
                        Button(onClick = vm::resume) { Text("Resume") }
                        OutlinedButton(onClick = vm::stop) { Text("Stop") }
                    }
                    TimerPhase.STOPPED -> {}
                }
            }

            if (timer.phase == TimerPhase.STOPPED) {
                SaveForm(vm, selected, trails, timer.activeSeconds, saving, onMeasure)
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun SaveForm(
    vm: SegmentWorkViewModel,
    jobType: com.asnidev.trailkeeper.data.local.JobTypeEntity?,
    trails: List<TrailEntity>,
    activeSeconds: Long,
    saving: Boolean,
    onMeasure: () -> Unit,
) {
    val unit = jobType?.unit ?: ""
    val canMeasure = unit == "km" || unit == "m" || unit == "m2"
    val measuredPreview by vm.measuredPreview.collectAsState()
    val measured = measuredPreview != null
    var qty by remember {
        mutableStateOf(
            if (unit == "hours") ((activeSeconds / 360).toInt() / 10.0).toString() else ""
        )
    }
    var crew by remember { mutableStateOf((jobType?.defaultCrew ?: 1).toString()) }
    var equipment by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    var trailId by remember { mutableStateOf<String?>(null) }
    var trailMenu by remember { mutableStateOf(false) }

    HorizontalDivider()
    Text("Stopped · log the work", style = MaterialTheme.typography.titleSmall)

    if (canMeasure) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = onMeasure) {
                Text(if (measured) "Re-measure on map" else "Measure on map")
            }
            if (measured) {
                Text(
                    if (unit == "m2") "≈ ${measuredPreview!!.toInt()} m² (server confirms)"
                    else "≈ %.2f km (server confirms)".format(measuredPreview),
                    style = MaterialTheme.typography.bodySmall,
                )
                TextButton(onClick = vm::clearMeasurement) { Text("Clear") }
            }
        }
    }

    if (!measured) {
        OutlinedTextField(
            value = qty,
            onValueChange = { qty = it },
            label = { Text(if (unit.isBlank()) "Quantity" else "Quantity ($unit)") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
            modifier = Modifier.fillMaxWidth(),
        )
    }
    OutlinedTextField(
        value = crew,
        onValueChange = { crew = it.filter(Char::isDigit) },
        label = { Text("Crew size") },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        modifier = Modifier.fillMaxWidth(),
    )
    OutlinedTextField(
        value = equipment,
        onValueChange = { equipment = it },
        label = { Text("Equipment (comma separated)") },
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
    )
    OutlinedTextField(
        value = notes,
        onValueChange = { notes = it },
        label = { Text("Notes") },
        maxLines = 3,
        modifier = Modifier.fillMaxWidth(),
    )
    if (trails.isNotEmpty()) {
        Box {
            OutlinedButton(onClick = { trailMenu = true }) {
                Text(trails.firstOrNull { it.id == trailId }?.name ?: "Trail (optional)")
            }
            DropdownMenu(expanded = trailMenu, onDismissRequest = { trailMenu = false }) {
                DropdownMenuItem(
                    text = { Text("(none)") },
                    onClick = {
                        trailId = null
                        trailMenu = false
                    },
                )
                trails.forEach { tr ->
                    DropdownMenuItem(
                        text = { Text(tr.name) },
                        onClick = {
                            trailId = tr.id
                            trailMenu = false
                        },
                    )
                }
            }
        }
    }

    val qtyValue = qty.toDoubleOrNull()
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Button(
            onClick = {
                vm.save(
                    quantity = qtyValue,
                    crewSize = crew.toIntOrNull()?.coerceAtLeast(1) ?: 1,
                    equipment = equipment.split(",").map(String::trim).filter(String::isNotEmpty),
                    notes = notes.trim(),
                    trailId = trailId,
                )
            },
            enabled = !saving && (measured || (qtyValue != null && qtyValue > 0)),
        ) {
            if (saving) CircularProgressIndicator(Modifier.size(16.dp)) else Text("Save")
        }
        OutlinedButton(onClick = vm::discard, enabled = !saving) { Text("Discard") }
    }
}

@Composable
private fun RecordCard(r: SegmentRecordRow) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(r.jobLabel, style = MaterialTheme.typography.titleMedium)
            Text(
                "${trimNum(r.quantity)} ${r.unit} · ${fmtDuration(r.activeSeconds.toLong())} · " +
                    "${r.crewSize}p · ${trimNum(r.personHours)} person-h",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                r.rateMinPerUnit?.let {
                    Text("${trimNum(it)} min/${r.unit}", style = MaterialTheme.typography.bodySmall)
                }
                r.vsExpectedMinPerUnit?.let { DeltaTag(it) }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun InsightsSection(
    groups: List<RollupGroupDto>,
    groupBy: String,
    onGroupBy: (String) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Productivity", style = MaterialTheme.typography.titleSmall)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            GROUP_BYS.forEach { (key, label) ->
                FilterChip(
                    selected = groupBy == key,
                    onClick = { onGroupBy(key) },
                    label = { Text(label) },
                )
            }
        }
        if (groups.isEmpty()) {
            Text(
                "No segments recorded yet.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        } else {
            groups.forEach { g ->
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(g.groupLabel, style = MaterialTheme.typography.titleSmall)
                        Text(
                            "${trimNum(g.totalQuantity)} ${g.unit} · " +
                                "${trimNum(g.totalPersonHours)} person-h · ${g.recordCount} rec",
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            g.meanRateMinPerUnit?.let {
                                Text("${trimNum(it)} min/${g.unit}", style = MaterialTheme.typography.bodySmall)
                            }
                            g.deltaMinPerUnit?.let { DeltaTag(it) }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun DeltaTag(delta: Double) {
    val slower = delta > 0
    val color = if (slower) MaterialTheme.colorScheme.error else Color(0xFF2E7D32)
    Surface(color = color, shape = RoundedCornerShape(4.dp)) {
        Text(
            "${if (slower) "+" else ""}${trimNum(delta)} vs target",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onPrimary,
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
        )
    }
}

private fun fmtDuration(s: Long): String {
    val h = s / 3600
    val m = (s % 3600) / 60
    val sec = s % 60
    return if (h > 0) "%d:%02d:%02d".format(h, m, sec) else "%02d:%02d".format(m, sec)
}

private fun trimNum(d: Double): String =
    if (d == d.toLong().toDouble()) d.toLong().toString() else "%.2f".format(d)
