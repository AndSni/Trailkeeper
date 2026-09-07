package com.asnidev.trailkeeper.ui.projects

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.asnidev.trailkeeper.data.ProjectDetailRepository
import com.asnidev.trailkeeper.network.SnapshotDto
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ProjectDetailUiState(
    val loading: Boolean = true,
    val snapshot: SnapshotDto? = null,
    val error: String? = null,
)

class ProjectDetailViewModel(private val projectId: String) : ViewModel() {
    private val _state = MutableStateFlow(ProjectDetailUiState())
    val state: StateFlow<ProjectDetailUiState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        _state.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            runCatching { ProjectDetailRepository.snapshot(projectId) }
                .onSuccess { snap -> _state.update { it.copy(loading = false, snapshot = snap) } }
                .onFailure { e ->
                    _state.update {
                        it.copy(loading = false, error = e.message ?: "Couldn't load the project")
                    }
                }
        }
    }
}
