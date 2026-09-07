package com.asnidev.trailkeeper.data.local

import com.asnidev.trailkeeper.network.ProjectDto
import com.asnidev.trailkeeper.network.ProjectMemberDto
import com.asnidev.trailkeeper.network.TaskDto
import com.asnidev.trailkeeper.network.TrailDto
import com.asnidev.trailkeeper.network.WorkLogDto
import com.google.gson.Gson

private val gson = Gson()

fun ProjectDto.toEntity() =
    ProjectEntity(
        id = id,
        organisationId = organisationId,
        name = name,
        description = description,
        activity = activity,
        status = status,
    )

fun TrailDto.toEntity() =
    TrailEntity(
        id = id,
        organisationId = organisationId,
        name = name,
        activity = activity,
        difficulty = difficulty,
        status = status,
        source = source,
        lengthM = lengthM,
        geometryJson = geometry?.toString(),
    )

fun TaskDto.toEntity() =
    TaskEntity(
        id = id,
        projectId = projectId,
        organisationId = organisationId,
        title = title,
        description = description,
        taskType = taskType,
        priority = priority,
        status = status,
        geometryJson = geometry?.toString(),
        nearestTrailId = nearestTrailId,
        estimateMin = estimateMin,
        assigneeIdsJson = gson.toJson(assigneeIds),
        photosJson = gson.toJson(photos),
    )

fun WorkLogDto.toEntity() =
    WorkLogEntity(
        id = id,
        projectId = projectId,
        taskId = taskId,
        trailId = trailId,
        userId = userId,
        minutes = minutes,
        workedOn = workedOn,
        note = note,
        autoFromTask = autoFromTask,
    )

fun ProjectMemberDto.toEntity(projectId: String) =
    ProjectMemberEntity(
        projectId = projectId,
        userId = userId,
        email = email,
        name = name,
        projectRole = projectRole,
    )
