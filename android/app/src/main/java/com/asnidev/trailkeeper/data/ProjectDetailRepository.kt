package com.asnidev.trailkeeper.data

import com.asnidev.trailkeeper.network.ApiClient
import com.asnidev.trailkeeper.network.SnapshotDto

object ProjectDetailRepository {
    /**
     * One call fills the whole detail screen: project, members, trails,
     * tasks, work logs. From Phase 1c this becomes a Room-backed read with
     * `GET /sync/changes` keeping it fresh in the background; for now it's a
     * straight online fetch.
     */
    suspend fun snapshot(projectId: String): SnapshotDto = ApiClient.api().snapshot(projectId)
}
