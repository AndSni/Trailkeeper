package com.asnidev.trailkeeper.network

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query

interface TrailkeeperApi {
    @POST("auth/register")
    suspend fun register(@Body body: RegisterRequest): TokenPair

    @POST("auth/login")
    suspend fun login(@Body body: LoginRequest): TokenPair

    @POST("auth/refresh")
    suspend fun refresh(@Body body: RefreshRequest): TokenPair

    @GET("auth/me")
    suspend fun me(): MeResponse

    @GET("projects")
    suspend fun listProjects(@Query("status") status: String? = null): List<ProjectDto>

    @POST("projects")
    suspend fun createProject(@Body body: CreateProjectRequest): ProjectDto
}
