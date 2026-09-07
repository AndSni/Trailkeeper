package com.asnidev.trailkeeper.data

import com.asnidev.trailkeeper.network.ApiClient
import com.asnidev.trailkeeper.network.MeResponse
import com.asnidev.trailkeeper.network.onAuthLost
// SyncRepository is in the same package (com.asnidev.trailkeeper.data)
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import retrofit2.HttpException

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
            runCatching { SyncRepository.clear() } // next account starts with a clean cache
            _state.value = AuthState.LoggedOut
        }
    }

    /** The org this session acts on (single-org for now). Null when logged out. */
    fun currentOrgId(): String? =
        (_state.value as? AuthState.LoggedIn)?.me?.memberships?.firstOrNull()?.organisationId

    fun currentUserId(): String? = (_state.value as? AuthState.LoggedIn)?.me?.user?.id

    private suspend fun refreshMe() {
        _state.value =
            try {
                AuthState.LoggedIn(ApiClient.api().me())
            } catch (e: HttpException) {
                // A real auth failure (401/403) - the token is dead, drop it.
                if (e.code() in 401..403) TokenStore.clear()
                AuthState.LoggedOut
            } catch (_: Exception) {
                // Network error at startup - keep the token so a later launch
                // with connectivity works. (Full offline login needs a cached
                // /auth/me; that's a later slice.)
                AuthState.LoggedOut
            }
    }
}
