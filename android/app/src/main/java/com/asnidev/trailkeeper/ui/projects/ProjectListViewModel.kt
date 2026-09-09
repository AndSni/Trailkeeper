package com.asnidev.trailkeeper.ui.projects

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.asnidev.trailkeeper.data.ProjectsRepository
import com.asnidev.trailkeeper.network.ProjectDto
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ProjectsUiState(
    val loading: Boolean = true,
    val projects: List<ProjectDto> = emptyList(),
    val error: String? = null,
    val creating: Boolean = false,
    val offline: Boolean = false,
)

class ProjectListViewModel : ViewModel() {
    private val _state = MutableStateFlow(ProjectsUiState())
    val state: StateFlow<ProjectsUiState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        _state.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            runCatching { ProjectsRepository.list() }
                .onSuccess { list ->
                    _state.update { it.copy(loading = false, projects = list, offline = false) }
                }
                .onFailure { e ->
                    val cached = runCatching { ProjectsRepository.cachedList() }.getOrDefault(emptyList())
                    _state.update {
                        if (cached.isNotEmpty()) {
                            it.copy(loading = false, projects = cached, offline = true, error = null)
                        } else {
                            it.copy(loading = false, error = e.message ?: "Failed to load")
                        }
                    }
                }
        }
    }

    fun create(name: String, activity: String) {
        if (name.isBlank() || _state.value.creating) return
        _state.update { it.copy(creating = true, error = null) }
        viewModelScope.launch {
            runCatching { ProjectsRepository.create(name, activity) }
                .onSuccess {
                    _state.update { it.copy(creating = false) }
                    refresh()
                }
                .onFailure { e ->
                    _state.update {
                        it.copy(creating = false, error = e.message ?: "Couldn't create project")
                    }
                }
        }
    }
}
