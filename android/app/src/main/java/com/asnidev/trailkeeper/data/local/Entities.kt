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
