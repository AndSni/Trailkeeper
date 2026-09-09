package com.asnidev.trailkeeper.network

import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Path
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

    @GET("sync/snapshot")
    suspend fun snapshot(@Query("project") projectId: String): SnapshotDto

    @GET("sync/changes")
    suspend fun changes(@Query("since") since: Long): SyncChangesDto

    @POST("sync/push")
    suspend fun push(@Body body: SyncPushRequest): SyncPushResponse

    @GET("job-types")
    suspend fun listJobTypes(): List<JobTypeDto>

    @POST("segment-work")
    suspend fun createSegmentWork(@Body body: SegmentWorkCreateRequest): SegmentWorkDto

    @GET("segment-work/rollup")
    suspend fun segmentRollup(
        @Query("project_id") projectId: String,
        @Query("group_by") groupBy: String,
    ): RollupDto

    @POST("structures")
    suspend fun createStructure(@Body body: StructureCreateRequest): StructureDto

    @PATCH("structures/{id}")
    suspend fun updateStructure(
        @Path("id") id: String,
        @Body body: StructurePatchRequest,
    ): StructureDto

    @DELETE("structures/{id}")
    suspend fun deleteStructure(@Path("id") id: String): retrofit2.Response<Unit>

    @POST("inspections")
    suspend fun createInspection(@Body body: InspectionCreateRequest): InspectionDto

    @POST("tracks")
    suspend fun createTrack(@Body body: TrackCreateRequest): TrackDto

    @POST("trails")
    suspend fun createTrail(@Body body: TrailCreateRequest): TrailDto

    @POST("tasks")
    suspend fun createTask(
        @Query("project_id") projectId: String,
        @Body body: TaskCreateRequest,
    ): TaskDto

    @DELETE("messages/{id}")
    suspend fun deleteMessage(@Path("id") id: String): retrofit2.Response<Unit>

    @GET("notifications")
    suspend fun notifications(@Query("limit") limit: Int = 100): List<NotificationDto>

    @POST("notifications/read")
    suspend fun markNotificationsRead(@Body body: MarkReadRequest)
}
