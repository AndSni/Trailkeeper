package com.asnidev.trailkeeper.ui.projects

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.asnidev.trailkeeper.data.Session
import com.asnidev.trailkeeper.data.SyncRepository
import com.asnidev.trailkeeper.data.local.ProjectEntity
import com.asnidev.trailkeeper.data.local.TaskEntity
import com.asnidev.trailkeeper.data.local.TrailEntity
import com.asnidev.trailkeeper.data.local.TrailkeeperDb
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ProjectDetailUiState(
    val project: ProjectEntity? = null,
    val trails: List<TrailEntity> = emptyList(),
    val tasks: List<TaskEntity> = emptyList(),
    val syncing: Boolean = false,
    val error: String? = null,
    val loaded: Boolean = false,
)

private data class SyncStatus(val syncing: Boolean = false, val error: String? = null)

/**
 * Reads the project's tasks and (org-wide) trails straight from Room, so the
 * screen renders offline from the last sync. [refresh] pulls fresh data via
 * [SyncRepository]; the Room flows push the update into the UI.
 */
class ProjectDetailViewModel(private val projectId: String) : ViewModel() {
    private val db = TrailkeeperDb.db
    private val orgId = Session.currentOrgId()
    private val sync = MutableStateFlow(SyncStatus())

    val state: StateFlow<ProjectDetailUiState> =
        combine(
            db.projectDao().observe(projectId),
            if (orgId != null) db.trailDao().observeForOrg(orgId) else flowOf(emptyList()),
            db.taskDao().observeForProject(projectId),
            sync,
        ) { project, trails, tasks, s ->
            ProjectDetailUiState(
                project = project,
                trails = trails,
                tasks = tasks,
                syncing = s.syncing,
                error = s.error,
                loaded = true,
            )
        }
            .stateIn(
                viewModelScope,
                SharingStarted.WhileSubscribed(5_000),
                ProjectDetailUiState(),
            )

    init {
        refresh()
    }

    fun refresh() {
        sync.update { it.copy(syncing = true, error = null) }
        viewModelScope.launch {
            runCatching { SyncRepository.syncProject(projectId) }
                .onSuccess { outcome ->
                    if (outcome.conflicts > 0) {
                        sync.update {
                            it.copy(
                                error =
                                    "${outcome.conflicts} edit(s) were replaced by newer server changes"
                            )
                        }
                    }
                }
                .onFailure { e -> sync.update { it.copy(error = e.message ?: "Sync failed") } }
            sync.update { it.copy(syncing = false) }
        }
    }

    /** Optimistic - the task shows immediately and syncs when online. */
    fun addTask(title: String, priority: String) {
        if (title.isBlank()) return
        viewModelScope.launch {
            runCatching { SyncRepository.createTask(projectId, title.trim(), priority) }
                .onFailure { e -> sync.update { it.copy(error = e.message ?: "Couldn't queue the task") } }
        }
    }

    fun setStatus(taskId: String, status: String) {
        viewModelScope.launch { runCatching { SyncRepository.setTaskStatus(taskId, status) } }
    }
}
