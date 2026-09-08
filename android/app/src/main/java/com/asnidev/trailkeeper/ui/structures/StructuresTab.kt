package com.asnidev.trailkeeper.ui.structures

import android.annotation.SuppressLint
import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.text.KeyboardOptions
import com.asnidev.trailkeeper.data.local.InspectionEntity
import com.asnidev.trailkeeper.data.local.InspectionFormEntity
import com.asnidev.trailkeeper.data.local.StructureEntity
import com.google.android.gms.location.LocationServices
import kotlin.coroutines.resume
import kotlinx.coroutines.suspendCancellableCoroutine

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StructuresTab(vm: StructuresViewModel, hasLocation: Boolean) {
    val structures by vm.structures.collectAsState()
    val forms by vm.forms.collectAsState()
    val inspections by vm.inspections.collectAsState()
    val saving by vm.saving.collectAsState()
    val message by vm.message.collectAsState()

    var openId by rememberSaveable { mutableStateOf<String?>(null) }
    var showAdd by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize()) {
        message?.let {
            MessageBar(it, onDismiss = vm::clearMessage)
        }

        val open = structures.firstOrNull { it.id == openId }
        if (open != null) {
            StructureDetail(
                structure = open,
                inspections = inspections.filter { it.structureId == open.id },
                forms = forms,
                saving = saving,
                onBack = { openId = null },
                onLog = { formId, answers, risk, condition, notes ->
                    vm.logInspection(open.id, formId, answers, risk, condition, notes, onDone = {})
                },
            )
        } else {
            LazyColumn(
                Modifier.fillMaxSize(),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                item {
                    Button(onClick = { showAdd = true }, modifier = Modifier.fillMaxWidth()) {
                        Text("Add structure")
                    }
                }
                if (structures.isEmpty()) {
                    item {
                        Text(
                            "No structures yet. Add culverts, bridges, signs and more here.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                items(structures, key = { it.id }) { s ->
                    val n = inspections.count { it.structureId == s.id }
                    Card(onClick = { openId = s.id }, modifier = Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                StatusTag(s.status)
                                Text(
                                    s.name,
                                    style = MaterialTheme.typography.titleMedium,
                                    modifier = Modifier.padding(start = 8.dp),
                                )
                            }
                            Text(
                                buildString {
                                    append(s.structureType.replace('_', ' '))
                                    if (s.material.isNotBlank()) append(" · ${s.material}")
                                    append(" · $n inspection${if (n == 1) "" else "s"}")
                                },
                                style = MaterialTheme.typography.labelMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
        }
    }

    if (showAdd) {
        AddStructureDialog(
            hasLocation = hasLocation,
            saving = saving,
            onDismiss = { showAdd = false },
            onCreate = { name, type, material, notes, lat, lon ->
                vm.addStructure(name, type, material, notes, lat, lon)
                showAdd = false
            },
        )
    }
}

@Composable
private fun MessageBar(text: String, onDismiss: () -> Unit) {
    androidx.compose.material3.Surface(
        color = MaterialTheme.colorScheme.errorContainer,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text,
                Modifier.weight(1f),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onErrorContainer,
            )
            TextButton(onClick = onDismiss) { Text("Dismiss") }
        }
    }
}

@Composable
private fun StructureDetail(
    structure: StructureEntity,
    inspections: List<InspectionEntity>,
    forms: List<InspectionFormEntity>,
    saving: Boolean,
    onBack: () -> Unit,
    onLog: (String?, Map<String, Any?>, String?, String?, String) -> Unit,
) {
    var showForm by remember { mutableStateOf(false) }

    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = onBack) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                }
                Text(structure.name, style = MaterialTheme.typography.titleLarge)
            }
        }
        item {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        StatusTag(structure.status)
                        Text(
                            structure.structureType.replace('_', ' '),
                            style = MaterialTheme.typography.bodyMedium,
                            modifier = Modifier.padding(start = 8.dp),
                        )
                    }
                    if (structure.material.isNotBlank()) {
                        Text("Material: ${structure.material}", style = MaterialTheme.typography.bodySmall)
                    }
                    if (structure.notes.isNotBlank()) {
                        Text(structure.notes, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }
        item {
            Button(onClick = { showForm = true }, modifier = Modifier.fillMaxWidth()) {
                Text("Log inspection")
            }
        }
        item {
            Text(
                "Inspections (${inspections.size})",
                style = MaterialTheme.typography.titleSmall,
            )
        }
        if (inspections.isEmpty()) {
            item {
                Text(
                    "No inspections recorded for this structure.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        items(inspections, key = { it.id }) { i -> InspectionCard(i) }
    }

    if (showForm) {
        InspectionSheet(
            forms = forms,
            saving = saving,
            onDismiss = { showForm = false },
            onSubmit = { formId, answers, risk, condition, notes ->
                onLog(formId, answers, risk, condition, notes)
                showForm = false
            },
        )
    }
}

@Composable
private fun InspectionCard(i: InspectionEntity) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(i.inspectedOn, style = MaterialTheme.typography.titleSmall)
                i.risk?.let { RiskTag(it) }
            }
            i.condition?.let {
                Text("Set condition: ${it.replace('_', ' ')}", style = MaterialTheme.typography.labelMedium)
            }
            if (i.notes.isNotBlank()) {
                Text(i.notes, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun AddStructureDialog(
    hasLocation: Boolean,
    saving: Boolean,
    onDismiss: () -> Unit,
    onCreate: (String, String, String, String, Double?, Double?) -> Unit,
) {
    val context = LocalContext.current
    var name by remember { mutableStateOf("") }
    var type by remember { mutableStateOf("culvert") }
    var typeMenu by remember { mutableStateOf(false) }
    var material by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    var useLoc by remember { mutableStateOf(hasLocation) }
    var loc by remember { mutableStateOf<android.location.Location?>(null) }

    LaunchedEffect(hasLocation) {
        if (hasLocation) loc = lastLocation(context)
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("New structure") },
        text = {
            Column(
                Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Box {
                    OutlinedButton(onClick = { typeMenu = true }) {
                        Text(type.replace('_', ' '))
                    }
                    DropdownMenu(expanded = typeMenu, onDismissRequest = { typeMenu = false }) {
                        STRUCTURE_TYPES.forEach { t ->
                            DropdownMenuItem(
                                text = { Text(t.replace('_', ' ')) },
                                onClick = {
                                    type = t
                                    typeMenu = false
                                },
                            )
                        }
                    }
                }
                OutlinedTextField(
                    value = material,
                    onValueChange = { material = it },
                    label = { Text("Material (optional)") },
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
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Switch(
                        checked = useLoc && hasLocation,
                        onCheckedChange = { useLoc = it },
                        enabled = hasLocation,
                    )
                    Spacer(Modifier.size(8.dp))
                    Text(
                        when {
                            !hasLocation -> "Location permission off"
                            loc != null -> "Attach current location"
                            else -> "Attach location (waiting for a fix…)"
                        },
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
        },
        confirmButton = {
            TextButton(
                enabled = name.isNotBlank() && !saving,
                onClick = {
                    val use = useLoc && hasLocation && loc != null
                    onCreate(
                        name,
                        type,
                        material,
                        notes,
                        if (use) loc!!.latitude else null,
                        if (use) loc!!.longitude else null,
                    )
                },
            ) {
                Text("Create")
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun InspectionSheet(
    forms: List<InspectionFormEntity>,
    saving: Boolean,
    onDismiss: () -> Unit,
    onSubmit: (String?, Map<String, Any?>, String?, String?, String) -> Unit,
) {
    var formId by remember { mutableStateOf<String?>(null) }
    var formMenu by remember { mutableStateOf(false) }
    val answers = remember { mutableStateMapOf<String, Any?>() }
    var risk by remember { mutableStateOf<String?>(null) }
    var condition by remember { mutableStateOf<String?>(null) }
    var notes by remember { mutableStateOf("") }

    val selectedForm = forms.firstOrNull { it.id == formId }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Log inspection") },
        text = {
            Column(
                Modifier.verticalScroll(rememberScrollState()).heightIn(max = 480.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Box {
                    OutlinedButton(onClick = { formMenu = true }) {
                        Text(selectedForm?.name ?: "Freeform (no form)")
                    }
                    DropdownMenu(expanded = formMenu, onDismissRequest = { formMenu = false }) {
                        DropdownMenuItem(
                            text = { Text("Freeform (no form)") },
                            onClick = {
                                formId = null
                                answers.clear()
                                formMenu = false
                            },
                        )
                        forms.forEach { f ->
                            DropdownMenuItem(
                                text = { Text("${f.name} · v${f.version}") },
                                onClick = {
                                    formId = f.id
                                    answers.clear()
                                    formMenu = false
                                },
                            )
                        }
                    }
                }

                selectedForm?.let { form ->
                    formFields(form).forEach { field ->
                        FormField(
                            key = field.key,
                            label = field.label ?: field.key,
                            type = field.type,
                            choices = field.choices,
                            value = answers[field.key],
                            onValue = { answers[field.key] = it },
                        )
                    }
                }

                HorizontalDivider()
                Text("Risk", style = MaterialTheme.typography.labelLarge)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    FilterChip(selected = risk == null, onClick = { risk = null }, label = { Text("—") })
                    INSPECTION_RISKS.forEach { r ->
                        FilterChip(
                            selected = risk == r,
                            onClick = { risk = r },
                            label = { Text(r) },
                        )
                    }
                }

                Text("Set structure condition (optional)", style = MaterialTheme.typography.labelLarge)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    FilterChip(
                        selected = condition == null,
                        onClick = { condition = null },
                        label = { Text("—") },
                    )
                    STRUCTURE_STATUSES.forEach { c ->
                        FilterChip(
                            selected = condition == c,
                            onClick = { condition = c },
                            label = { Text(c.replace('_', ' ')) },
                        )
                    }
                }

                OutlinedTextField(
                    value = notes,
                    onValueChange = { notes = it },
                    label = { Text("Notes") },
                    maxLines = 4,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            TextButton(
                enabled = !saving,
                onClick = { onSubmit(formId, answers.toMap(), risk, condition, notes) },
            ) {
                if (saving) CircularProgressIndicator(Modifier.size(16.dp)) else Text("Save")
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun FormField(
    key: String,
    label: String,
    type: String,
    choices: List<String>,
    value: Any?,
    onValue: (Any?) -> Unit,
) {
    when (type) {
        "section" -> Text(label, style = MaterialTheme.typography.titleSmall)
        "bool" ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(label, Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
                Switch(checked = value == true, onCheckedChange = { onValue(it) })
            }
        "number" ->
            OutlinedTextField(
                value = (value as? String) ?: "",
                onValueChange = { onValue(it) },
                label = { Text(label) },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                modifier = Modifier.fillMaxWidth(),
            )
        "choice" ->
            Column {
                Text(label, style = MaterialTheme.typography.bodyMedium)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    choices.forEach { c ->
                        FilterChip(
                            selected = value == c,
                            onClick = { onValue(c) },
                            label = { Text(c) },
                        )
                    }
                }
            }
        else ->
            OutlinedTextField(
                value = (value as? String) ?: "",
                onValueChange = { onValue(it) },
                label = { Text(label) },
                maxLines = 3,
                modifier = Modifier.fillMaxWidth(),
            )
    }
}

@Composable
private fun StatusTag(status: String) {
    val color = when (status) {
        "failed" -> MaterialTheme.colorScheme.error
        "needs_repair" -> Color(0xFFD6A64B)
        "monitor" -> Color(0xFF2F6D7A)
        "decommissioned" -> MaterialTheme.colorScheme.onSurfaceVariant
        else -> Color(0xFF2E7D32)
    }
    Tag(status.replace('_', ' ').uppercase(), color)
}

@Composable
private fun RiskTag(risk: String) {
    val color = when (risk) {
        "critical" -> MaterialTheme.colorScheme.error
        "high" -> Color(0xFFD6A64B)
        "medium" -> Color(0xFF2F6D7A)
        else -> Color(0xFF2E7D32)
    }
    Tag("RISK ${risk.uppercase()}", color)
}

@Composable
private fun Tag(text: String, color: Color) {
    androidx.compose.material3.Surface(color = color, shape = RoundedCornerShape(4.dp)) {
        Text(
            text,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onPrimary,
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
        )
    }
}

@SuppressLint("MissingPermission")
private suspend fun lastLocation(context: Context): android.location.Location? =
    suspendCancellableCoroutine { cont ->
        LocationServices.getFusedLocationProviderClient(context).lastLocation
            .addOnSuccessListener { cont.resume(it) }
            .addOnFailureListener { cont.resume(null) }
    }
