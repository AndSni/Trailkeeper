package com.asnidev.trailkeeper.data

import com.asnidev.trailkeeper.network.ApiClient
import com.asnidev.trailkeeper.network.MeResponse
import com.asnidev.trailkeeper.network.onAuthLost
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface AuthState {
    data object Loading : AuthState
    data object LoggedOut : AuthState
    data class LoggedIn(val me: MeResponse) : AuthState
}

/** App-wide auth state. The UI observes [state]; repositories call
 * [onAuthenticated] / [signOut]. */
object Session {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    private val _state = MutableStateFlow<AuthState>(AuthState.Loading)
    val state: StateFlow<AuthState> = _state.asStateFlow()

    fun start() {
        onAuthLost = { signOut() }
        scope.launch {
            if (TokenStore.current == null) {
                _state.value = AuthState.LoggedOut
            } else {
                refreshMe()
            }
        }
    }

    /** Called after a successful login/register (tokens already persisted). */
    fun onAuthenticated() {
        scope.launch { refreshMe() }
    }

    fun signOut() {
        scope.launch {
            TokenStore.clear()
            _state.value = AuthState.LoggedOut
        }
    }

    private suspend fun refreshMe() {
        _state.value =
            try {
                AuthState.LoggedIn(ApiClient.api().me())
            } catch (_: Exception) {
                // Token invalid / server unreachable at startup - treat as
                // logged out; the login screen surfaces any real error.
                TokenStore.clear()
                AuthState.LoggedOut
            }
    }
}
