package com.asnidev.trailkeeper

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.Saver
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.asnidev.trailkeeper.data.AuthState
import com.asnidev.trailkeeper.data.Session
import com.asnidev.trailkeeper.ui.auth.LoginScreen
import com.asnidev.trailkeeper.ui.projects.ProjectDetailScreen
import com.asnidev.trailkeeper.ui.projects.ProjectListScreen

private data class OpenProject(val id: String, val name: String)

private val openProjectSaver: Saver<OpenProject?, List<String>> =
    Saver(
        save = { it?.let { p -> listOf(p.id, p.name) } ?: emptyList() },
        restore = { if (it.size == 2) OpenProject(it[0], it[1]) else null },
    )

@Composable
fun TrailkeeperApp() {
    val auth by Session.state.collectAsState()
    var open by rememberSaveable(stateSaver = openProjectSaver) { mutableStateOf<OpenProject?>(null) }

    when (auth) {
        AuthState.Loading ->
            Box(Modifier.fillMaxSize()) { CircularProgressIndicator(Modifier.align(Alignment.Center)) }
        AuthState.LoggedOut -> LoginScreen()
        is AuthState.LoggedIn -> {
            val current = open
            if (current == null) {
                ProjectListScreen(onOpenProject = { id, name -> open = OpenProject(id, name) })
            } else {
                ProjectDetailScreen(
                    projectId = current.id,
                    projectName = current.name,
                    onBack = { open = null },
                )
            }
        }
    }
}
