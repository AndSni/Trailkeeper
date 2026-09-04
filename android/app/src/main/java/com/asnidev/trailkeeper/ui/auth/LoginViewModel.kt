package com.asnidev.trailkeeper.ui.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.asnidev.trailkeeper.data.AuthRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import retrofit2.HttpException

data class LoginUiState(
    val register: Boolean = false,
    val email: String = "",
    val password: String = "",
    val name: String = "",
    val orgName: String = "",
    val busy: Boolean = false,
    val error: String? = null,
) {
    val canSubmit: Boolean
        get() =
            !busy &&
                email.isNotBlank() &&
                password.length >= 8 &&
                (!register || (name.isNotBlank() && orgName.isNotBlank()))
}

class LoginViewModel : ViewModel() {
    private val _state = MutableStateFlow(LoginUiState())
    val state: StateFlow<LoginUiState> = _state.asStateFlow()

    fun setEmail(v: String) = _state.update { it.copy(email = v, error = null) }

    fun setPassword(v: String) = _state.update { it.copy(password = v, error = null) }

    fun setName(v: String) = _state.update { it.copy(name = v, error = null) }

    fun setOrgName(v: String) = _state.update { it.copy(orgName = v, error = null) }

    fun toggleMode() = _state.update { it.copy(register = !it.register, error = null) }

    fun submit() {
        val s = _state.value
        if (!s.canSubmit) return
        _state.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            val result =
                runCatching {
                    if (s.register) {
                        AuthRepository.register(s.email, s.name, s.password, s.orgName)
                    } else {
                        AuthRepository.login(s.email, s.password)
                    }
                }
            result.onFailure { e ->
                _state.update { it.copy(busy = false, error = humanError(e)) }
            }
            // On success, Session flips to LoggedIn and this screen is
            // replaced; no need to clear busy.
        }
    }

    private fun humanError(e: Throwable): String =
        when (e) {
            is HttpException ->
                when (e.code()) {
                    401 -> "Invalid email or password"
                    409 -> "That email is already registered"
                    403 -> "Registration is disabled on this server"
                    else -> "Server error (${e.code()})"
                }
            else -> "Can't reach the server. Check your connection."
        }
}
