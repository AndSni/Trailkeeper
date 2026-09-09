package com.asnidev.trailkeeper.data

import com.asnidev.trailkeeper.network.ApiClient
import com.asnidev.trailkeeper.network.MeResponse
import com.asnidev.trailkeeper.network.onAuthLost
import com.google.gson.Gson
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
    private val gson = Gson()

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
            runCatching { IdentityStore.clear() }
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
                val me = ApiClient.api().me()
                runCatching { IdentityStore.save(gson.toJson(me)) }
                AuthState.LoggedIn(me)
            } catch (e: HttpException) {
                // A real auth failure (401/403) - the token is dead, drop it
                // and the cached identity with it.
                if (e.code() in 401..403) {
                    TokenStore.clear()
                    IdentityStore.clear()
                    AuthState.LoggedOut
                } else {
                    // 5xx etc. - treat like offline: fall back to the cache.
                    offlineIdentity()
                }
            } catch (_: Exception) {
                // Network error at startup - stay signed in from the cached
                // /auth/me if we have one, so the field app opens offline.
                offlineIdentity()
            }
    }

    private suspend fun offlineIdentity(): AuthState {
        val cached =
            runCatching { IdentityStore.load()?.let { gson.fromJson(it, MeResponse::class.java) } }
                .getOrNull()
        return if (cached != null) AuthState.LoggedIn(cached) else AuthState.LoggedOut
    }
}
