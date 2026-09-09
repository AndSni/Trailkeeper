package com.asnidev.trailkeeper.data

import com.asnidev.trailkeeper.data.local.NotificationEntity
import com.asnidev.trailkeeper.data.local.TrailkeeperDb
import com.asnidev.trailkeeper.data.local.toEntity
import com.asnidev.trailkeeper.network.ApiClient
import com.asnidev.trailkeeper.network.MarkReadRequest
import java.time.Instant
import kotlinx.coroutines.flow.Flow

/**
 * The notification inbox. It isn't part of the org-wide change stream (rows
 * are per-user), so it's fetched on its own from `GET /notifications` and
 * cached in Room for the unread badge and the list to read offline.
 */
object NotificationRepository {
    private val db get() = TrailkeeperDb.db

    fun unreadCount(): Flow<Int> = db.notificationDao().observeUnreadCount()

    fun all(): Flow<List<NotificationEntity>> = db.notificationDao().observeAll()

    /** Task ids that have at least one unread notification (e.g. a new comment). */
    fun unreadTaskIds(): Flow<List<String>> = db.notificationDao().observeUnreadTaskIds()

    /** Clear the unread flag for one task's notifications (call when its thread is opened). */
    suspend fun markTaskRead(taskId: String) {
        val ids = db.notificationDao().unreadIdsForTask(taskId)
        markRead(ids)
    }

    suspend fun refresh() {
        val fresh = ApiClient.api().notifications()
        db.notificationDao().upsertAll(fresh.map { it.toEntity() })
    }

    suspend fun markRead(ids: List<String>) {
        if (ids.isEmpty()) return
        ApiClient.api().markNotificationsRead(MarkReadRequest(ids = ids))
        db.notificationDao().markRead(ids, Instant.now().toString())
    }

    suspend fun markAllRead() {
        ApiClient.api().markNotificationsRead(MarkReadRequest(all = true))
        db.notificationDao().markAllRead(Instant.now().toString())
    }
}
