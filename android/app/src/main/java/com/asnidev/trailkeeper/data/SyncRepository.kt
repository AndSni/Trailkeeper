package com.asnidev.trailkeeper.data

import androidx.room.withTransaction
import com.asnidev.trailkeeper.data.local.ProjectSyncEntity
import com.asnidev.trailkeeper.data.local.SyncStateEntity
import com.asnidev.trailkeeper.data.local.TrailkeeperDb
import com.asnidev.trailkeeper.data.local.toEntity
import com.asnidev.trailkeeper.network.ApiClient
import com.asnidev.trailkeeper.network.ProjectDto
import com.asnidev.trailkeeper.network.ProjectMemberDto
import com.asnidev.trailkeeper.network.SyncChangeDto
import com.asnidev.trailkeeper.network.TaskDto
import com.asnidev.trailkeeper.network.TrailDto
import com.asnidev.trailkeeper.network.WorkLogDto
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Keeps the Room cache in step with the server (see docs/BLUEPRINT.md sec 8).
 *
 * A project is seeded once from `GET /sync/snapshot`; after that every
 * `sync()` runs the org-wide incremental loop `GET /sync/changes?since=
 * <cursor>`, applying each change to Room and advancing the cursor. Snapshots
 * never move the org cursor - the incremental loop re-applying a handful of
 * changes already in a snapshot is idempotent and keeps every project
 * converging.
 */
object SyncRepository {
    private val gson = Gson()
    private val db get() = TrailkeeperDb.db

    /** Seed [projectId] if it hasn't been, then pull org-wide deltas. */
    suspend fun syncProject(projectId: String) {
        val orgId = Session.currentOrgId() ?: return
        if (db.syncStateDao().projectSnapshotSeq(projectId) == null) {
            snapshotProject(projectId)
        }
        pullChanges(orgId)
    }

    private suspend fun snapshotProject(projectId: String) {
        val snap = ApiClient.api().snapshot(projectId)
        db.withTransaction {
            db.projectDao().upsert(snap.project.toEntity())
            db.projectMemberDao().deleteForProject(projectId)
            db.projectMemberDao().upsertAll(snap.members.map { it.toEntity(projectId) })
            db.trailDao().upsertAll(snap.trails.map { it.toEntity() })
            db.taskDao().deleteForProject(projectId)
            db.taskDao().upsertAll(snap.tasks.map { it.toEntity() })
            db.workLogDao().deleteForProject(projectId)
            db.workLogDao().upsertAll(snap.workLogs.map { it.toEntity() })
            db.syncStateDao().markProjectSnapshotted(ProjectSyncEntity(projectId, snap.highSeq))
        }
    }

    private suspend fun pullChanges(orgId: String) {
        var since = db.syncStateDao().highSeq(orgId) ?: 0L
        while (true) {
            val resp = ApiClient.api().changes(since)
            if (resp.changes.isNotEmpty()) {
                db.withTransaction { resp.changes.forEach { applyChange(it) } }
            }
            since = resp.highSeq
            db.syncStateDao().upsert(SyncStateEntity(orgId, since))
            if (!resp.hasMore) break
        }
    }

    private suspend fun applyChange(c: SyncChangeDto) {
        val row = c.row
        when (c.entityType) {
            "trail" ->
                if (c.op == "delete" || row == null) db.trailDao().deleteById(c.entityId)
                else db.trailDao().upsert(gson.fromJson(row, TrailDto::class.java).toEntity())
            "task" ->
                if (c.op == "delete" || row == null) db.taskDao().deleteById(c.entityId)
                else db.taskDao().upsert(gson.fromJson(row, TaskDto::class.java).toEntity())
            "work_log" ->
                if (c.op == "delete" || row == null) db.workLogDao().deleteById(c.entityId)
                else db.workLogDao().upsert(gson.fromJson(row, WorkLogDto::class.java).toEntity())
            "project" ->
                if (c.op == "delete" || row == null) db.projectDao().deleteById(c.entityId)
                else db.projectDao().upsert(gson.fromJson(row, ProjectDto::class.java).toEntity())
            "project_member" -> {
                // entityId is the project id; row is the full member list.
                db.projectMemberDao().deleteForProject(c.entityId)
                if (row != null) {
                    val type = object : TypeToken<List<ProjectMemberDto>>() {}.type
                    val members: List<ProjectMemberDto> = gson.fromJson(row, type)
                    db.projectMemberDao().upsertAll(members.map { it.toEntity(c.entityId) })
                }
            }
        }
    }

    /** Wipe the cache - used on sign-out so the next account starts clean. */
    suspend fun clear() {
        withContext(Dispatchers.IO) { db.clearAllTables() }
    }
}
