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
interface ProjectMemberDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsertAll(rows: List<ProjectMemberEntity>)

    @Query("SELECT * FROM project_members WHERE projectId = :projectId ORDER BY name")
    fun observeForProject(projectId: String): Flow<List<ProjectMemberEntity>>

    @Query("DELETE FROM project_members WHERE projectId = :projectId")
    suspend fun deleteForProject(projectId: String)
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
