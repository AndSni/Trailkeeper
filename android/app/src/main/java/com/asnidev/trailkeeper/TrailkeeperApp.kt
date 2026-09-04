package com.asnidev.trailkeeper

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.asnidev.trailkeeper.data.AuthState
import com.asnidev.trailkeeper.data.Session
import com.asnidev.trailkeeper.ui.auth.LoginScreen
import com.asnidev.trailkeeper.ui.projects.ProjectListScreen

@Composable
fun TrailkeeperApp() {
    val auth by Session.state.collectAsState()
    when (auth) {
        AuthState.Loading ->
            Box(Modifier.fillMaxSize()) { CircularProgressIndicator(Modifier.align(Alignment.Center)) }
        AuthState.LoggedOut -> LoginScreen()
        is AuthState.LoggedIn -> ProjectListScreen()
    }
}
