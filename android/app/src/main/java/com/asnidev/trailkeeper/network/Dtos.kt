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

data class JobTypeDto(
    val id: String,
    val activity: String,
    val key: String,
    val label: String,
    val unit: String, // hours | km | m2 | count
    @SerializedName("default_crew") val defaultCrew: Int,
    @SerializedName("expected_rate") val expectedRate: Double?,
    val color: String,
    @SerializedName("sort_group") val sortGroup: String,
)

data class SegmentWorkDto(
    val id: String,
    @SerializedName("project_id") val projectId: String,
    @SerializedName("job_type_id") val jobTypeId: String?,
    @SerializedName("trail_id") val trailId: String?,
    val quantity: Double,
    val unit: String,
    @SerializedName("quantity_source") val quantitySource: String,
    @SerializedName("started_at") val startedAt: String,
    @SerializedName("ended_at") val endedAt: String?,
    @SerializedName("active_seconds") val activeSeconds: Int,
    @SerializedName("crew_size") val crewSize: Int,
    val equipment: List<String> = emptyList(),
    val notes: String,
    @SerializedName("created_by_id") val createdById: String?,
    @SerializedName("person_hours") val personHours: Double,
    @SerializedName("rate_min_per_unit") val rateMinPerUnit: Double?,
    @SerializedName("vs_expected_min_per_unit") val vsExpectedMinPerUnit: Double?,
)

data class StructureDto(
    val id: String,
    @SerializedName("organisation_id") val organisationId: String,
    val name: String,
    @SerializedName("structure_type") val structureType: String,
    val status: String,
    val geometry: JsonElement?, // GeoJSON Point, or null
    @SerializedName("nearest_trail_id") val nearestTrailId: String?,
    val material: String,
    val color: String = "",
    @SerializedName("installed_on") val installedOn: String?,
    @SerializedName("inspection_interval_days") val inspectionIntervalDays: Int?,
    val notes: String,
)

data class InspectionFieldDto(
    val key: String,
    val label: String?,
    val type: String, // bool | text | number | choice | section
    val required: Boolean = false,
    val choices: List<String> = emptyList(),
)

data class InspectionFormDto(
    val id: String,
    val name: String,
    @SerializedName("target_type") val targetType: String,
    val fields: List<InspectionFieldDto> = emptyList(),
    val version: Int,
    @SerializedName("is_active") val isActive: Boolean,
)

data class InspectionDto(
    val id: String,
    @SerializedName("project_id") val projectId: String,
    @SerializedName("structure_id") val structureId: String,
    @SerializedName("form_id") val formId: String?,
    @SerializedName("form_version") val formVersion: Int?,
    @SerializedName("inspector_id") val inspectorId: String?,
    @SerializedName("inspected_on") val inspectedOn: String,
    val answers: JsonElement?,
    val risk: String?,
    val condition: String?,
    val notes: String,
)

data class TrackDto(
    val id: String,
    @SerializedName("project_id") val projectId: String,
    val name: String,
    val activity: String,
    val source: String,
    @SerializedName("started_at") val startedAt: String?,
    @SerializedName("ended_at") val endedAt: String?,
    @SerializedName("moving_seconds") val movingSeconds: Int,
    @SerializedName("length_m") val lengthM: Double,
    @SerializedName("point_count") val pointCount: Int,
    val geometry: JsonElement?, // GeoJSON LineString
    @SerializedName("recorded_by_id") val recordedById: String?,
)

data class TrackPointDto(
    val lat: Double,
    val lon: Double,
    val ele: Double? = null,
    val t: String? = null,
)

data class TaskCreateRequest(
    val title: String,
    val priority: String = "medium",
    val lat: Double? = null,
    val lon: Double? = null,
)

data class TrackCreateRequest(
    @SerializedName("project_id") val projectId: String,
    val name: String,
    val activity: String = "mtb",
    @SerializedName("started_at") val startedAt: String?,
    @SerializedName("ended_at") val endedAt: String?,
    @SerializedName("moving_seconds") val movingSeconds: Int,
    val points: List<TrackPointDto>,
)

data class SnapshotDto(
    val project: ProjectDto,
    val members: List<ProjectMemberDto> = emptyList(),
    val trails: List<TrailDto> = emptyList(),
    val tasks: List<TaskDto> = emptyList(),
    @SerializedName("work_logs") val workLogs: List<WorkLogDto> = emptyList(),
    val messages: List<MessageDto> = emptyList(),
    @SerializedName("job_types") val jobTypes: List<JobTypeDto> = emptyList(),
    @SerializedName("segment_work") val segmentWork: List<SegmentWorkDto> = emptyList(),
    val structures: List<StructureDto> = emptyList(),
    @SerializedName("inspection_forms") val inspectionForms: List<InspectionFormDto> = emptyList(),
    val inspections: List<InspectionDto> = emptyList(),
    val tracks: List<TrackDto> = emptyList(),
    @SerializedName("high_seq") val highSeq: Long,
)

data class StructureCreateRequest(
    val name: String,
    @SerializedName("structure_type") val structureType: String,
    val status: String = "good",
    val lat: Double? = null,
    val lon: Double? = null,
    val material: String = "",
    val color: String = "",
    val notes: String = "",
)

data class StructurePatchRequest(
    val name: String? = null,
    @SerializedName("structure_type") val structureType: String? = null,
    val status: String? = null,
    val lat: Double? = null,
    val lon: Double? = null,
    val material: String? = null,
    val color: String? = null,
    val notes: String? = null,
)

data class InspectionCreateRequest(
    @SerializedName("project_id") val projectId: String,
    @SerializedName("structure_id") val structureId: String,
    @SerializedName("form_id") val formId: String? = null,
    val answers: Map<String, Any?> = emptyMap(),
    val risk: String? = null,
    val condition: String? = null,
    val notes: String = "",
)

data class SegmentWorkCreateRequest(
    @SerializedName("project_id") val projectId: String,
    @SerializedName("job_type_id") val jobTypeId: String,
    @SerializedName("trail_id") val trailId: String? = null,
    val geometry: JsonElement? = null, // GeoJSON LineString / Polygon when measured
    val quantity: Double?,
    @SerializedName("quantity_source") val quantitySource: String = "manual",
    @SerializedName("started_at") val startedAt: String,
    @SerializedName("ended_at") val endedAt: String?,
    @SerializedName("active_seconds") val activeSeconds: Int,
    val pauses: List<Map<String, String>> = emptyList(),
    @SerializedName("crew_size") val crewSize: Int = 1,
    val equipment: List<String> = emptyList(),
    val notes: String = "",
)

data class RollupGroupDto(
    @SerializedName("group_key") val groupKey: String,
    @SerializedName("group_label") val groupLabel: String,
    @SerializedName("record_count") val recordCount: Int,
    val unit: String,
    @SerializedName("total_quantity") val totalQuantity: Double,
    @SerializedName("total_person_hours") val totalPersonHours: Double,
    @SerializedName("mean_rate_min_per_unit") val meanRateMinPerUnit: Double?,
    @SerializedName("expected_rate") val expectedRate: Double?,
    @SerializedName("delta_min_per_unit") val deltaMinPerUnit: Double?,
)

data class RollupDto(
    @SerializedName("group_by") val groupBy: String,
    val groups: List<RollupGroupDto> = emptyList(),
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
