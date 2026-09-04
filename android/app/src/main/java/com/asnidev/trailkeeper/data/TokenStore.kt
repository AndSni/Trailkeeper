package com.asnidev.trailkeeper.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "trailkeeper_auth")

data class Tokens(val access: String, val refresh: String)

/**
 * Persists the JWT pair. Exposes a plain synchronous [current] snapshot for
 * the OkHttp interceptor / authenticator (they run off non-suspend threads);
 * that snapshot is kept warm by [init] at startup and every [save] / [clear].
 */
object TokenStore {
    private val ACCESS = stringPreferencesKey("access")
    private val REFRESH = stringPreferencesKey("refresh")

    @Volatile
    private var cache: Tokens? = null
    private lateinit var appContext: Context

    fun init(context: Context) {
        appContext = context.applicationContext
        runBlocking { cache = read() }
    }

    val current: Tokens?
        get() = cache

    private suspend fun read(): Tokens? {
        val prefs = appContext.dataStore.data.first()
        val a = prefs[ACCESS]
        val r = prefs[REFRESH]
        return if (a != null && r != null) Tokens(a, r) else null
    }

    suspend fun save(tokens: Tokens) {
        appContext.dataStore.edit {
            it[ACCESS] = tokens.access
            it[REFRESH] = tokens.refresh
        }
        cache = tokens
    }

    suspend fun clear() {
        appContext.dataStore.edit { it.clear() }
        cache = null
    }
}
