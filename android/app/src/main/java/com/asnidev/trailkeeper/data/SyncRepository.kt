package com.asnidev.trailkeeper.data

import androidx.room.withTransaction
import com.asnidev.trailkeeper.data.local.MessageEntity
import com.asnidev.trailkeeper.data.local.OutboxEntity
import com.asnidev.trailkeeper.data.local.ProjectSyncEntity
import com.asnidev.trailkeeper.data.local.SyncStateEntity
import com.asnidev.trailkeeper.data.local.TaskEntity
import com.asnidev.trailkeeper.data.local.TrailkeeperDb
import com.asnidev.trailkeeper.data.local.toEntity
import com.asnidev.trailkeeper.network.ApiClient
import com.asnidev.trailkeeper.network.MessageDto
import com.asnidev.trailkeeper.network.ProjectDto
import com.asnidev.trailkeeper.network.ProjectMemberDto
import com.asnidev.trailkeeper.network.SyncChangeDto
import com.asnidev.trailkeeper.network.SyncOpRequest
import com.asnidev.trailkeeper.network.SyncPushRequest
import com.asnidev.trailkeeper.network.TaskDto
import com.asnidev.trailkeeper.network.TrailDto
import com.asnidev.trailkeeper.network.WorkLogDto
import com.google.gson.Gson
import com.google.gson.JsonElement
import com.google.gson.reflect.TypeToken
import java.time.Instant
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private fun nowIso(): String = Instant.now().toString()

/**
 * Keeps the Room cache in step with the server (docs/BLUEPRINT.md sec 8).
 *
 * Read: a project is seeded once from `GET /sync/snapshot`, then every
 * [syncProject] runs the org-wide incremental loop `GET /sync/changes?since=
 * <cursor>`. Snapshots never move the cursor - re-applying a few already-seen
 * changes is idempotent.
 *
 * Write: offline edits are written to Room optimistically and queued in the
 * `outbox`; [drainOutbox] posts them to `POST /sync/push` and folds the
 * authoritative rows back in. It runs before every pull.
 */
object SyncRepository {
    private val gson = Gson()
    private val db get() = TrailkeeperDb.db

    /** Result of one sync pass, so the caller can surface conflicts. */
    data class Outcome(val conflicts: Int = 0, val rejected: Int = 0)

    /** Push the outbox, seed [projectId] if new, then pull org-wide deltas. */
    suspend fun syncProject(projectId: String): Outcome {
        val orgId = Session.currentOrgId() ?: return Outcome()
        val pushOutcome = drainOutbox()
        if (db.syncStateDao().projectSnapshotSeq(projectId) == null) {
            snapshotProject(projectId)
        }
        pullChanges(orgId)
        return pushOutcome
    }

    // ---- write path -----------------------------------------------------

    suspend fun createTask(projectId: String, title: String, priority: String): String {
        val orgId = Session.currentOrgId() ?: error("not signed in")
        val id = UUID.randomUUID().toString()
        val optimistic =
            TaskEntity(
                id = id,
                projectId = projectId,
                organisationId = orgId,
                title = title,
                description = "",
                taskType = "",
                priority = priority,
                status = "open",
                geometryJson = null,
                nearestTrailId = null,
                estimateMin = null,
                assigneeIdsJson = "[]",
                photosJson = "[]",
                updatedAt = "",
            )
        db.taskDao().upsert(optimistic)
        enqueue(
            "task", id, "upsert", baseUpdatedAt = null,
            fields = mapOf("project_id" to projectId, "title" to title, "priority" to priority),
        )
        drainOutbox()
        return id
    }

    suspend fun setTaskStatus(taskId: String, status: String) {
        val current = db.taskDao().getById(taskId) ?: return
        db.taskDao().upsert(current.copy(status = status))
        enqueue(
            "task", taskId, "upsert",
            baseUpdatedAt = current.updatedAt.ifBlank { null },
            fields = mapOf("status" to status),
        )
        drainOutbox()
    }

    /** Post a comment (project thread when [taskId] is null). Optimistic +
     * queued through the outbox. */
    suspend fun postMessage(projectId: String, taskId: String?, body: String) {
        val id = UUID.randomUUID().toString()
        db.messageDao().upsert(
            MessageEntity(
                id = id,
                projectId = projectId,
                taskId = taskId,
                authorId = Session.currentUserId(),
                body = body,
                mentionedUserIdsJson = "[]",
                createdAt = nowIso(),
            )
        )
        val fields = buildMap<String, Any?> {
            put("project_id", projectId)
            if (taskId != null) put("task_id", taskId)
            put("body", body)
        }
        enqueue("message", id, "upsert", baseUpdatedAt = null, fields = fields)
        drainOutbox()
    }

    private suspend fun enqueue(
        entityType: String,
        entityId: String,
        op: String,
        baseUpdatedAt: String?,
        fields: Map<String, Any?>,
    ) {
        db.outboxDao().insert(
            OutboxEntity(
                clientOpId = UUID.randomUUID().toString(),
                entityType = entityType,
                entityId = entityId,
                op = op,
                baseUpdatedAt = baseUpdatedAt,
                fieldsJson = gson.toJson(fields),
                createdAt = System.currentTimeMillis(),
            )
        )
    }

    /** Post every queued op; apply the returned rows; drop the queue entries. */
    suspend fun drainOutbox(): Outcome {
        val pending = db.outboxDao().all()
        if (pending.isEmpty()) return Outcome()

        val req =
            SyncPushRequest(
                ops =
                    pending.map {
                        SyncOpRequest(
                            clientOpId = it.clientOpId,
                            entityType = it.entityType,
                            entityId = it.entityId,
                            op = it.op,
                            baseUpdatedAt = it.baseUpdatedAt,
                            fields = gson.fromJson(it.fieldsJson, JsonElement::class.java),
                        )
                    }
            )
        val resp = ApiClient.api().push(req) // throws if offline -> queue stays intact

        var conflicts = 0
        var rejected = 0
        db.withTransaction {
            for (r in resp.results) {
                when (r.status) {
                    "conflict" -> conflicts++
                    "rejected" -> rejected++
                }
                applyRow(r.entityType, r.entityId, r.row)
                db.outboxDao().deleteById(r.clientOpId)
            }
        }
        return Outcome(conflicts, rejected)
    }

    private suspend fun applyRow(entityType: String, entityId: String, row: JsonElement?) {
        when (entityType) {
            "task" ->
                if (row == null) db.taskDao().deleteById(entityId)
                else db.taskDao().upsert(gson.fromJson(row, TaskDto::class.java).toEntity())
            "work_log" ->
                if (row == null) db.workLogDao().deleteById(entityId)
                else db.workLogDao().upsert(gson.fromJson(row, WorkLogDto::class.java).toEntity())
            "message" ->
                if (row == null) db.messageDao().deleteById(entityId)
                else db.messageDao().upsert(gson.fromJson(row, MessageDto::class.java).toEntity())
        }
    }

    // ---- read path ----------------------------------------------------

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
            db.messageDao().deleteForProject(projectId)
            db.messageDao().upsertAll(snap.messages.map { it.toEntity() })
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
                db.projectMemberDao().deleteForProject(c.entityId)
                if (row != null) {
                    val type = object : TypeToken<List<ProjectMemberDto>>() {}.type
                    val members: List<ProjectMemberDto> = gson.fromJson(row, type)
                    db.projectMemberDao().upsertAll(members.map { it.toEntity(c.entityId) })
                }
            }
            "message" ->
                if (c.op == "delete" || row == null) db.messageDao().deleteById(c.entityId)
                else db.messageDao().upsert(gson.fromJson(row, MessageDto::class.java).toEntity())
        }
    }

    /** Wipe the cache - used on sign-out so the next account starts clean. */
    suspend fun clear() {
        withContext(Dispatchers.IO) { db.clearAllTables() }
    }
}
