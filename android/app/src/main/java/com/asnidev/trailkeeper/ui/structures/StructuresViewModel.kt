package com.asnidev.trailkeeper.ui.structures

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.asnidev.trailkeeper.data.Session
import com.asnidev.trailkeeper.data.SyncRepository
import com.asnidev.trailkeeper.data.local.InspectionEntity
import com.asnidev.trailkeeper.data.local.InspectionFormEntity
import com.asnidev.trailkeeper.data.local.StructureEntity
import com.asnidev.trailkeeper.data.local.TrailkeeperDb
import com.asnidev.trailkeeper.network.InspectionCreateRequest
import com.asnidev.trailkeeper.network.InspectionFieldDto
import com.asnidev.trailkeeper.network.StructureCreateRequest
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

val STRUCTURE_TYPES = listOf(
    "culvert", "bridge", "boardwalk", "ford", "steps", "retaining_wall",
    "drain", "waterbar", "sign", "gate", "bench", "kiosk", "other",
)
val STRUCTURE_STATUSES = listOf("good", "monitor", "needs_repair", "failed", "decommissioned")
val INSPECTION_RISKS = listOf("low", "medium", "high", "critical")

private val gson = Gson()
private val FIELD_LIST = object : TypeToken<List<InspectionFieldDto>>() {}.type

fun formFields(form: InspectionFormEntity): List<InspectionFieldDto> =
    runCatching { gson.fromJson<List<InspectionFieldDto>>(form.fieldsJson, FIELD_LIST) }
        .getOrDefault(emptyList())

/**
 * Structure inventory + inspection capture for one project (BLUEPRINT sec 3).
 * Structures and forms are org-wide Room flows; inspections are per-project.
 * Creating a structure or an inspection is online-only for now.
 */
class StructuresViewModel(private val projectId: String) : ViewModel() {
    private val db = TrailkeeperDb.db
    private val orgId = Session.currentOrgId()

    val structures: StateFlow<List<StructureEntity>> =
        (if (orgId != null) db.structureDao().observeForOrg(orgId) else flowOf(emptyList()))
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    val forms: StateFlow<List<InspectionFormEntity>> =
        db.inspectionFormDao()
            .observeAll()
            .map { list -> list.filter { it.isActive } }
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    val inspections: StateFlow<List<InspectionEntity>> =
        db.inspectionDao()
            .observeForProject(projectId)
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    private val _message = MutableStateFlow<String?>(null)
    val message: StateFlow<String?> = _message.asStateFlow()

    private val _saving = MutableStateFlow(false)
    val saving: StateFlow<Boolean> = _saving.asStateFlow()

    fun addStructure(
        name: String,
        type: String,
        material: String,
        notes: String,
        lat: Double?,
        lon: Double?,
    ) {
        _saving.value = true
        viewModelScope.launch {
            runCatching {
                SyncRepository.createStructure(
                    StructureCreateRequest(
                        name = name.trim(),
                        structureType = type,
                        material = material.trim(),
                        notes = notes.trim(),
                        lat = lat,
                        lon = lon,
                    )
                )
            }
                .onFailure { e -> _message.value = e.message ?: "Couldn't create the structure" }
            _saving.value = false
        }
    }

    fun logInspection(
        structureId: String,
        formId: String?,
        answers: Map<String, Any?>,
        risk: String?,
        condition: String?,
        notes: String,
        onDone: () -> Unit,
    ) {
        _saving.value = true
        viewModelScope.launch {
            runCatching {
                SyncRepository.createInspection(
                    InspectionCreateRequest(
                        projectId = projectId,
                        structureId = structureId,
                        formId = formId,
                        answers = answers,
                        risk = risk,
                        condition = condition,
                        notes = notes.trim(),
                    )
                )
            }
                .onSuccess { onDone() }
                .onFailure { e -> _message.value = e.message ?: "Couldn't save the inspection" }
            _saving.value = false
        }
    }

    fun clearMessage() {
        _message.value = null
    }
}
