package com.asnidev.trailkeeper.network

import com.google.gson.JsonElement
import com.google.gson.annotations.SerializedName

data class RegisterRequest(
    val email: String,
    val name: String,
    val password: String,
    @SerializedName("organisation_name") val organisationName: String,
)

data class LoginRequest(val email: String, val password: String)

data class RefreshRequest(@SerializedName("refresh_token") val refreshToken: String)

data class TokenPair(
    @SerializedName("access_token") val accessToken: String,
    @SerializedName("refresh_token") val refreshToken: String,
    @SerializedName("token_type") val tokenType: String = "bearer",
)

data class MembershipDto(
    @SerializedName("organisation_id") val organisationId: String,
    @SerializedName("org_role") val orgRole: String,
)

data class UserDto(
    val id: String,
    val email: String,
    val name: String,
    @SerializedName("is_active") val isActive: Boolean,
)

data class MeResponse(val user: UserDto, val memberships: List<MembershipDto>)

data class ProjectDto(
    val id: String,
    @SerializedName("organisation_id") val organisationId: String,
    val name: String,
    val description: String,
    val activity: String,
    val status: String,
)

data class CreateProjectRequest(
    val name: String,
    val description: String = "",
    val activity: String = "mtb",
)

// --- sync (GET /sync/snapshot) ---------------------------------------------

data class TrailDto(
    val id: String,
    @SerializedName("organisation_id") val organisationId: String,
    val name: String,
    val activity: String,
    val difficulty: String,
    val status: String,
    val source: String,
    @SerializedName("length_m") val lengthM: Double,
    val geometry: JsonElement?, // GeoJSON LineString - parsed by the map layer later
)

data class TaskPhotoDto(
    val id: String,
    val caption: String,
    val url: String,
)

data class TaskDto(
    val id: String,
    @SerializedName("organisation_id") val organisationId: String,
    @SerializedName("project_id") val projectId: String,
    val title: String,
    val description: String,
    @SerializedName("task_type") val taskType: String,
    val priority: String,
    val status: String,
    val geometry: JsonElement?, // GeoJSON Point, or null
    @SerializedName("nearest_trail_id") val nearestTrailId: String?,
    @SerializedName("estimate_min") val estimateMin: Int?,
    @SerializedName("assignee_ids") val assigneeIds: List<String> = emptyList(),
    val photos: List<TaskPhotoDto> = emptyList(),
    @SerializedName("updated_at") val updatedAt: String,
)

data class WorkLogDto(
    val id: String,
    @SerializedName("project_id") val projectId: String,
    @SerializedName("task_id") val taskId: String?,
    @SerializedName("trail_id") val trailId: String?,
    @SerializedName("user_id") val userId: String,
    val minutes: Int,
    @SerializedName("worked_on") val workedOn: String,
    val note: String,
    @SerializedName("auto_from_task") val autoFromTask: Boolean,
    @SerializedName("updated_at") val updatedAt: String,
)

data class ProjectMemberDto(
    @SerializedName("user_id") val userId: String,
    val email: String,
    val name: String,
    @SerializedName("project_role") val projectRole: String,
)

data class MessageDto(
    val id: String,
    @SerializedName("project_id") val projectId: String,
    @SerializedName("task_id") val taskId: String?,
    @SerializedName("author_id") val authorId: String?,
    val body: String,
    @SerializedName("mentioned_user_ids") val mentionedUserIds: List<String> = emptyList(),
    @SerializedName("created_at") val createdAt: String,
)

data class SnapshotDto(
    val project: ProjectDto,
    val members: List<ProjectMemberDto> = emptyList(),
    val trails: List<TrailDto> = emptyList(),
    val tasks: List<TaskDto> = emptyList(),
    @SerializedName("work_logs") val workLogs: List<WorkLogDto> = emptyList(),
    val messages: List<MessageDto> = emptyList(),
    @SerializedName("high_seq") val highSeq: Long,
)

data class NotificationDto(
    val id: String,
    val type: String,
    @SerializedName("subject_type") val subjectType: String,
    @SerializedName("subject_id") val subjectId: String,
    @SerializedName("project_id") val projectId: String?,
    @SerializedName("actor_id") val actorId: String?,
    val body: String,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("read_at") val readAt: String?,
)

// --- sync (GET /sync/changes) --------------------------------------------

data class SyncChangeDto(
    @SerializedName("server_seq") val serverSeq: Long,
    @SerializedName("entity_type") val entityType: String,
    @SerializedName("entity_id") val entityId: String,
    @SerializedName("project_id") val projectId: String?,
    val op: String, // "upsert" | "delete"
    // Shape depends on entityType: TrailDto / TaskDto / WorkLogDto /
    // ProjectDto, or (project_member) a JSON array of ProjectMemberDto.
    val row: JsonElement?,
)

data class SyncChangesDto(
    val changes: List<SyncChangeDto> = emptyList(),
    @SerializedName("high_seq") val highSeq: Long,
    @SerializedName("has_more") val hasMore: Boolean,
)

// --- sync (POST /sync/push) --------------------------------------------

data class SyncOpRequest(
    @SerializedName("client_op_id") val clientOpId: String,
    @SerializedName("entity_type") val entityType: String,
    @SerializedName("entity_id") val entityId: String,
    val op: String,
    @SerializedName("base_updated_at") val baseUpdatedAt: String?,
    val fields: JsonElement,
)

data class SyncPushRequest(val ops: List<SyncOpRequest>)

data class SyncOpResultDto(
    @SerializedName("client_op_id") val clientOpId: String,
    @SerializedName("entity_type") val entityType: String,
    @SerializedName("entity_id") val entityId: String,
    val status: String, // "applied" | "conflict" | "rejected"
    @SerializedName("server_seq") val serverSeq: Long?,
    val row: JsonElement?,
    val message: String?,
)

data class SyncPushResponse(
    val results: List<SyncOpResultDto> = emptyList(),
    @SerializedName("high_seq") val highSeq: Long,
)

data class MarkReadRequest(val ids: List<String> = emptyList(), val all: Boolean = false)
