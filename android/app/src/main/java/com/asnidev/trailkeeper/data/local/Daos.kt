package com.asnidev.trailkeeper.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Upsert
import kotlinx.coroutines.flow.Flow

@Dao
interface ProjectDao {
    @Upsert suspend fun upsert(row: ProjectEntity)

    @Query("SELECT * FROM projects WHERE id = :id") fun observe(id: String): Flow<ProjectEntity?>

    @Query("DELETE FROM projects WHERE id = :id") suspend fun deleteById(id: String)
}

@Dao
interface TrailDao {
    @Upsert suspend fun upsertAll(rows: List<TrailEntity>)

    @Upsert suspend fun upsert(row: TrailEntity)

    @Query("SELECT * FROM trails WHERE organisationId = :orgId ORDER BY name")
    fun observeForOrg(orgId: String): Flow<List<TrailEntity>>

    @Query("DELETE FROM trails WHERE id = :id") suspend fun deleteById(id: String)
}

@Dao
interface TaskDao {
    @Upsert suspend fun upsertAll(rows: List<TaskEntity>)

    @Upsert suspend fun upsert(row: TaskEntity)

    @Query("SELECT * FROM tasks WHERE projectId = :projectId ORDER BY title")
    fun observeForProject(projectId: String): Flow<List<TaskEntity>>

    @Query("SELECT * FROM tasks WHERE id = :id") suspend fun getById(id: String): TaskEntity?

    @Query("DELETE FROM tasks WHERE id = :id") suspend fun deleteById(id: String)

    @Query("DELETE FROM tasks WHERE projectId = :projectId") suspend fun deleteForProject(projectId: String)
}

@Dao
interface WorkLogDao {
    @Upsert suspend fun upsertAll(rows: List<WorkLogEntity>)

    @Upsert suspend fun upsert(row: WorkLogEntity)

    @Query("SELECT * FROM work_logs WHERE projectId = :projectId ORDER BY workedOn DESC")
    fun observeForProject(projectId: String): Flow<List<WorkLogEntity>>

    @Query("DELETE FROM work_logs WHERE id = :id") suspend fun deleteById(id: String)

    @Query("DELETE FROM work_logs WHERE projectId = :projectId") suspend fun deleteForProject(projectId: String)
}

@Dao
interface JobTypeDao {
    @Upsert suspend fun upsertAll(rows: List<JobTypeEntity>)

    @Upsert suspend fun upsert(row: JobTypeEntity)

    @Query("SELECT * FROM job_types ORDER BY sortGroup, label")
    fun observeAll(): Flow<List<JobTypeEntity>>

    @Query("DELETE FROM job_types WHERE id = :id") suspend fun deleteById(id: String)
}

@Dao
interface SegmentWorkDao {
    @Upsert suspend fun upsertAll(rows: List<SegmentWorkEntity>)

    @Upsert suspend fun upsert(row: SegmentWorkEntity)

    @Query("SELECT * FROM segment_work WHERE projectId = :projectId ORDER BY startedAt DESC")
    fun observeForProject(projectId: String): Flow<List<SegmentWorkEntity>>

    @Query("DELETE FROM segment_work WHERE id = :id") suspend fun deleteById(id: String)

    @Query("DELETE FROM segment_work WHERE projectId = :projectId")
    suspend fun deleteForProject(projectId: String)
}

@Dao
interface StructureDao {
    @Upsert suspend fun upsertAll(rows: List<StructureEntity>)

    @Upsert suspend fun upsert(row: StructureEntity)

    @Query("SELECT * FROM structures WHERE organisationId = :orgId ORDER BY name")
    fun observeForOrg(orgId: String): Flow<List<StructureEntity>>

    @Query("DELETE FROM structures WHERE id = :id") suspend fun deleteById(id: String)
}

@Dao
interface InspectionFormDao {
    @Upsert suspend fun upsertAll(rows: List<InspectionFormEntity>)

    @Upsert suspend fun upsert(row: InspectionFormEntity)

    @Query("SELECT * FROM inspection_forms ORDER BY name")
    fun observeAll(): Flow<List<InspectionFormEntity>>

    @Query("DELETE FROM inspection_forms WHERE id = :id") suspend fun deleteById(id: String)
}

@Dao
interface InspectionDao {
    @Upsert suspend fun upsertAll(rows: List<InspectionEntity>)

    @Upsert suspend fun upsert(row: InspectionEntity)

    @Query("SELECT * FROM inspections WHERE projectId = :projectId ORDER BY inspectedOn DESC")
    fun observeForProject(projectId: String): Flow<List<InspectionEntity>>

    @Query("DELETE FROM inspections WHERE id = :id") suspend fun deleteById(id: String)

    @Query("DELETE FROM inspections WHERE projectId = :projectId")
    suspend fun deleteForProject(projectId: String)
}

@Dao
interface TrackDao {
    @Upsert suspend fun upsertAll(rows: List<TrackEntity>)

    @Upsert suspend fun upsert(row: TrackEntity)

    @Query("SELECT * FROM tracks WHERE projectId = :projectId ORDER BY startedAt DESC")
    fun observeForProject(projectId: String): Flow<List<TrackEntity>>

    @Query("DELETE FROM tracks WHERE id = :id") suspend fun deleteById(id: String)

    @Query("DELETE FROM tracks WHERE projectId = :projectId")
    suspend fun deleteForProject(projectId: String)
}

@Dao
interface ProjectMemberDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsertAll(rows: List<ProjectMemberEntity>)

    @Query("SELECT * FROM project_members WHERE projectId = :projectId ORDER BY name")
    fun observeForProject(projectId: String): Flow<List<ProjectMemberEntity>>

    @Query("DELETE FROM project_members WHERE projectId = :projectId")
    suspend fun deleteForProject(projectId: String)
}

@Dao
interface MessageDao {
    @Upsert suspend fun upsertAll(rows: List<MessageEntity>)

    @Upsert suspend fun upsert(row: MessageEntity)

    @Query(
        "SELECT * FROM messages WHERE projectId = :projectId AND taskId IS :taskId ORDER BY createdAt"
    )
    fun observeThread(projectId: String, taskId: String?): Flow<List<MessageEntity>>

    @Query("DELETE FROM messages WHERE id = :id") suspend fun deleteById(id: String)

    @Query("DELETE FROM messages WHERE projectId = :projectId")
    suspend fun deleteForProject(projectId: String)
}

@Dao
interface NotificationDao {
    @Upsert suspend fun upsertAll(rows: List<NotificationEntity>)

    @Query("SELECT * FROM notifications ORDER BY createdAt DESC")
    fun observeAll(): Flow<List<NotificationEntity>>

    @Query("SELECT COUNT(*) FROM notifications WHERE readAt IS NULL")
    fun observeUnreadCount(): Flow<Int>

    @Query("UPDATE notifications SET readAt = :ts WHERE id IN (:ids)")
    suspend fun markRead(ids: List<String>, ts: String)

    @Query("UPDATE notifications SET readAt = :ts WHERE readAt IS NULL")
    suspend fun markAllRead(ts: String)

    @Query("DELETE FROM notifications") suspend fun clear()
}

@Dao
interface OutboxDao {
    @Insert suspend fun insert(row: OutboxEntity)

    @Query("SELECT * FROM outbox ORDER BY createdAt") suspend fun all(): List<OutboxEntity>

    @Query("SELECT COUNT(*) FROM outbox") fun count(): Flow<Int>

    @Query("DELETE FROM outbox WHERE clientOpId = :id") suspend fun deleteById(id: String)
}

@Dao
interface SyncStateDao {
    @Query("SELECT highSeq FROM sync_state WHERE organisationId = :orgId")
    suspend fun highSeq(orgId: String): Long?

    @Upsert suspend fun upsert(row: SyncStateEntity)

    @Query("SELECT snapshotHighSeq FROM project_sync WHERE projectId = :projectId")
    suspend fun projectSnapshotSeq(projectId: String): Long?

    @Upsert suspend fun markProjectSnapshotted(row: ProjectSyncEntity)

    @Query("DELETE FROM sync_state") suspend fun clearSyncState()

    @Query("DELETE FROM project_sync") suspend fun clearProjectSync()
}
