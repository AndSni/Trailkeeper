package com.asnidev.trailkeeper.ui.notifications

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.asnidev.trailkeeper.data.NotificationRepository
import com.asnidev.trailkeeper.data.local.NotificationEntity
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class NotificationsViewModel : ViewModel() {
    val items: StateFlow<List<NotificationEntity>> =
        NotificationRepository.all()
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    var loading by mutableStateOf(false)
        private set

    init {
        refresh()
    }

    fun refresh() {
        loading = true
        viewModelScope.launch {
            runCatching { NotificationRepository.refresh() }
            loading = false
        }
    }

    fun markRead(id: String) {
        viewModelScope.launch { runCatching { NotificationRepository.markRead(listOf(id)) } }
    }

    fun markAllRead() {
        viewModelScope.launch { runCatching { NotificationRepository.markAllRead() } }
    }
}
