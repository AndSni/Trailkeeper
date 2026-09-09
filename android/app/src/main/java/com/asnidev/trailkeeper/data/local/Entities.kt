package com.asnidev.trailkeeper.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * Room mirror of the server's synced entities. This database is a cache:
 * every row can be rebuilt from `GET /sync/snapshot` + `GET /sync/changes`,
 * so schema changes just wipe and re-sync (see TrailkeeperDb). Geometry is
 * kept as the raw GeoJSON string and parsed on demand by the map layer.
 */

@Entity(tableName = "projects")
data class ProjectEntity(
    @PrimaryKey val id: String,
    val organisationId: String,
    val name: String,
    val description: String,
    val activity: String,
    val status: String,
)

@Entity(tableName = "trails")
data class TrailEntity(
    @PrimaryKey val id: String,
    val organisationId: String,
    val name: String,
    val activity: String,
    val difficulty: String,
    val status: String,
    val source: String,
    val lengthM: Double,
    val geometryJson: String?,
)

@Entity(tableName = "tasks")
data class TaskEntity(
    @PrimaryKey val id: String,
    val projectId: String,
    val organisationId: String,
    val title: String,
    val description: String,
    val taskType: String,
    val priority: String,
    val status: String,
    val geometryJson: String?,
    val nearestTrailId: String?,
    val estimateMin: Int?,
    val assigneeIdsJson: String, // JSON array of user ids
    val photosJson: String, // JSON array of {id, caption, url}
    // The server version this row reflects - sent as base_updated_at when an
    // offline edit is pushed, so the server can detect a stale write. Empty
    // for a row that only exists locally (not yet pushed).
    val updatedAt: String,
)

@Entity(tableName = "work_logs")
data class WorkLogEntity(
    @PrimaryKey val id: String,
    val projectId: String,
    val taskId: String?,
    val trailId: String?,
    val userId: String,
    val minutes: Int,
    val workedOn: String,
    val note: String,
    val autoFromTask: Boolean,
    val updatedAt: String,
)

@Entity(tableName = "project_members", primaryKeys = ["projectId", "userId"])
data class ProjectMemberEntity(
    val projectId: String,
    val userId: String,
    val email: String,
    val name: String,
    val projectRole: String,
)

/** One row per org: the incremental `/sync/changes` cursor. */
@Entity(tableName = "sync_state")
data class SyncStateEntity(
    @PrimaryKey val organisationId: String,
    val highSeq: Long,
)

/** Marks a project as having been seeded from `/sync/snapshot` at least once. */
@Entity(tableName = "project_sync")
data class ProjectSyncEntity(
    @PrimaryKey val projectId: String,
    val snapshotHighSeq: Long,
)

@Entity(tableName = "messages")
data class MessageEntity(
    @PrimaryKey val id: String,
    val projectId: String,
    val taskId: String?, // null = the project's own thread
    val authorId: String?,
    val body: String,
    val mentionedUserIdsJson: String,
    val createdAt: String,
)

@Entity(tableName = "notifications")
data class NotificationEntity(
    @PrimaryKey val id: String,
    val type: String,
    val subjectType: String,
    val subjectId: String,
    val projectId: String?,
    val actorId: String?,
    val body: String,
    val createdAt: String,
    val readAt: String?,
)

/** Org-wide taxonomy: how a kind of trail work is measured (BLUEPRINT sec 10). */
@Entity(tableName = "job_types")
data class JobTypeEntity(
    @PrimaryKey val id: String,
    val activity: String,
    val key: String,
    val label: String,
    val unit: String, // hours | km | m2 | count
    val defaultCrew: Int,
    val expectedRate: Double?, // minutes per unit
    val color: String,
    val sortGroup: String,
)

/** One timed piece of work. Derived numbers (person-hours, rate, delta) come
 * pre-computed from the server; the rollup view fetches fresh from the API. */
@Entity(tableName = "segment_work")
data class SegmentWorkEntity(
    @PrimaryKey val id: String,
    val projectId: String,
    val jobTypeId: String?,
    val trailId: String?,
    val quantity: Double,
    val unit: String,
    val quantitySource: String,
    val startedAt: String,
    val endedAt: String?,
    val activeSeconds: Int,
    val crewSize: Int,
    val equipmentJson: String,
    val notes: String,
    val createdById: String?,
    val personHours: Double,
    val rateMinPerUnit: Double?,
    val vsExpectedMinPerUnit: Double?,
)

/** Built asset on the network (culvert, bridge, sign, ...). Org-wide like a
 * trail; geometry kept as raw GeoJSON for the map layer. */
@Entity(tableName = "structures")
data class StructureEntity(
    @PrimaryKey val id: String,
    val organisationId: String,
    val name: String,
    val structureType: String,
    val status: String,
    val geometryJson: String?,
    val nearestTrailId: String?,
    val material: String,
    val installedOn: String?,
    val inspectionIntervalDays: Int?,
    val notes: String,
)

/** A reusable JSON-schema inspection questionnaire (org-wide, versioned).
 * [fieldsJson] is the serialized list of InspectionFieldDto. */
@Entity(tableName = "inspection_forms")
data class InspectionFormEntity(
    @PrimaryKey val id: String,
    val name: String,
    val targetType: String,
    val fieldsJson: String,
    val version: Int,
    val isActive: Boolean,
)

/** One filled-in form against one structure, in a project's context.
 * [answersJson] is the serialized answers object. */
@Entity(tableName = "inspections")
data class InspectionEntity(
    @PrimaryKey val id: String,
    val projectId: String,
    val structureId: String,
    val formId: String?,
    val formVersion: Int?,
    val inspectorId: String?,
    val inspectedOn: String,
    val answersJson: String,
    val risk: String?,
    val condition: String?,
    val notes: String,
)

/** A recorded or imported GPX route. Geometry kept as raw GeoJSON for the
 * map; the per-point detail lives only on the server (fetch via GPX). */
@Entity(tableName = "tracks")
data class TrackEntity(
    @PrimaryKey val id: String,
    val projectId: String,
    val name: String,
    val activity: String,
    val source: String,
    val startedAt: String?,
    val endedAt: String?,
    val movingSeconds: Int,
    val lengthM: Double,
    val pointCount: Int,
    val geometryJson: String?,
    val recordedById: String?,
)

/**
 * A pending offline write, queued for `POST /sync/push`. Rows are drained
 * before every pull; each carries the fields as a JSON object and the
 * client-generated [clientOpId] the server dedupes on.
 */
@Entity(tableName = "outbox")
data class OutboxEntity(
    @PrimaryKey val clientOpId: String,
    val entityType: String, // "task" | "work_log"
    val entityId: String,
    val op: String, // "upsert" | "delete"
    val baseUpdatedAt: String?, // null for a create
    val fieldsJson: String, // JSON object of the changed fields
    val createdAt: Long,
)
