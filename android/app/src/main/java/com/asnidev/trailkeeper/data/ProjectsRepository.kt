package com.asnidev.trailkeeper.data

import com.asnidev.trailkeeper.network.ApiClient
import com.asnidev.trailkeeper.network.CreateProjectRequest
import com.asnidev.trailkeeper.network.ProjectDto

object ProjectsRepository {
    suspend fun list(): List<ProjectDto> = ApiClient.api().listProjects()

    suspend fun create(name: String, activity: String): ProjectDto =
        ApiClient.api().createProject(CreateProjectRequest(name = name.trim(), activity = activity))
}
