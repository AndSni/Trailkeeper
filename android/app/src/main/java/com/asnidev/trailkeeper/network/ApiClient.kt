package com.asnidev.trailkeeper.network

import com.asnidev.trailkeeper.BuildConfig
import com.asnidev.trailkeeper.data.TokenStore
import com.asnidev.trailkeeper.data.Tokens
import com.google.gson.Gson
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import okhttp3.Authenticator
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.Route
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

/** Called when a refresh attempt fails - the session is over, the UI should
 * drop back to the login screen. Wired up by [com.asnidev.trailkeeper.data.Session]. */
var onAuthLost: () -> Unit = {}

private val gson = Gson()
private val JSON = "application/json; charset=utf-8".toMediaType()

private class AuthInterceptor : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val token = TokenStore.current?.access
        val request =
            if (token != null && chain.request().header("Authorization") == null) {
                chain.request().newBuilder().header("Authorization", "Bearer $token").build()
            } else {
                chain.request()
            }
        return chain.proceed(request)
    }
}

/** On a 401, try the refresh token once (synchronously), persist the new pair
 * and retry the original request with it. If refresh itself fails, clear the
 * tokens and notify the app. */
private class RefreshAuthenticator(private val baseUrl: () -> String?) : Authenticator {
    override fun authenticate(route: Route?, response: Response): Request? {
        if (response.request.header("X-Retry") != null) return null
        val refresh = TokenStore.current?.refresh ?: return null
        val base = baseUrl() ?: return null

        val newTokens = runCatching { refreshBlocking(base, refresh) }.getOrNull()
        if (newTokens == null) {
            TokenStore.let { store ->
                kotlinx.coroutines.runBlocking { store.clear() }
            }
            onAuthLost()
            return null
        }
        kotlinx.coroutines.runBlocking { TokenStore.save(newTokens) }
        return response.request.newBuilder()
            .header("Authorization", "Bearer ${newTokens.access}")
            .header("X-Retry", "1")
            .build()
    }

    private fun refreshBlocking(base: String, refreshToken: String): Tokens {
        val body = gson.toJson(RefreshRequest(refreshToken)).toRequestBody(JSON)
        val req = Request.Builder().url(base + "auth/refresh").post(body).build()
        bareClient.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) throw IOException("refresh failed: ${resp.code}")
            val pair = gson.fromJson(resp.body!!.charStream(), TokenPair::class.java)
            return Tokens(pair.accessToken, pair.refreshToken)
        }
    }
}

private val bareClient =
    OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

private data class Candidate(val label: String, val baseUrl: String)

object ApiClient {
    // External Cloudflare Tunnel first (works anywhere), then LAN wifi, then
    // adb-reverse loopback for local dev. Same idea as SharpRight's ApiClient.
    private val candidates =
        listOf(
            Candidate("External (Cloudflare)", BuildConfig.EXTERNAL_API_BASE_URL),
            Candidate("LAN (home network)", BuildConfig.LAN_API_BASE_URL),
            Candidate("ADB reverse (local dev)", BuildConfig.API_BASE_URL),
        )

    @Volatile private var resolvedCandidate: Candidate? = null
    @Volatile private var resolvedApi: TrailkeeperApi? = null
    private val resolveMutex = Mutex()

    private val probeClient =
        OkHttpClient.Builder()
            .connectTimeout(2, TimeUnit.SECONDS)
            .readTimeout(2, TimeUnit.SECONDS)
            .build()

    private val client =
        OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor())
            .authenticator(RefreshAuthenticator { resolvedCandidate?.baseUrl })
            .addInterceptor(
                HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BASIC }
            )
            // If a real request dies at the transport level, whatever was
            // resolved just proved itself dead - re-run resolution next call.
            .addInterceptor(
                Interceptor { chain ->
                    try {
                        chain.proceed(chain.request())
                    } catch (e: IOException) {
                        resolvedApi = null
                        resolvedCandidate = null
                        throw e
                    }
                }
            )
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .build()

    suspend fun api(): TrailkeeperApi {
        resolvedApi?.let { return it }
        return resolveMutex.withLock {
            resolvedApi?.let { return it }
            val candidate = withContext(Dispatchers.IO) { firstReachableCandidate() }
            resolvedCandidate = candidate
            Retrofit.Builder()
                .baseUrl(candidate.baseUrl)
                .client(client)
                .addConverterFactory(GsonConverterFactory.create())
                .build()
                .create(TrailkeeperApi::class.java)
                .also { resolvedApi = it }
        }
    }

    private fun firstReachableCandidate(): Candidate {
        for (candidate in candidates) {
            val request = Request.Builder().url(candidate.baseUrl + "health").build()
            try {
                probeClient.newCall(request).execute().use { if (it.isSuccessful) return candidate }
            } catch (_: IOException) {
                // Unreachable on this transport - try the next.
            }
        }
        // Nothing answered; return the last candidate so the real request's
        // own error surfaces instead of the probe swallowing it.
        return candidates.last()
    }
}
