package com.asnidev.trailkeeper.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.first

private val Context.identityStore: DataStore<Preferences> by
    preferencesDataStore(name = "trailkeeper_identity")

/**
 * Caches the last successful `/auth/me` so the app can open offline: at
 * startup, a network error no longer forces the login screen if we still
 * have a token and a cached identity.
 */
object IdentityStore {
    private val ME = stringPreferencesKey("me_json")
    private lateinit var appContext: Context

    fun init(context: Context) {
        appContext = context.applicationContext
    }

    suspend fun save(meJson: String) {
        appContext.identityStore.edit { it[ME] = meJson }
    }

    suspend fun load(): String? = appContext.identityStore.data.first()[ME]

    suspend fun clear() {
        appContext.identityStore.edit { it.clear() }
    }
}
