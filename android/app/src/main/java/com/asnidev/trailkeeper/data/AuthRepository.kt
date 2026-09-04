package com.asnidev.trailkeeper.data

import com.asnidev.trailkeeper.network.ApiClient
import com.asnidev.trailkeeper.network.LoginRequest
import com.asnidev.trailkeeper.network.RegisterRequest
import com.asnidev.trailkeeper.network.TokenPair

object AuthRepository {
    suspend fun login(email: String, password: String) {
        persist(ApiClient.api().login(LoginRequest(email.trim(), password)))
    }

    suspend fun register(email: String, name: String, password: String, orgName: String) {
        persist(
            ApiClient.api()
                .register(RegisterRequest(email.trim(), name.trim(), password, orgName.trim()))
        )
    }

    private suspend fun persist(pair: TokenPair) {
        TokenStore.save(Tokens(pair.accessToken, pair.refreshToken))
        Session.onAuthenticated()
    }
}
