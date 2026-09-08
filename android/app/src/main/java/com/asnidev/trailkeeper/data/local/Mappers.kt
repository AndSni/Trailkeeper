package com.asnidev.trailkeeper.data.local

import com.asnidev.trailkeeper.network.InspectionDto
import com.asnidev.trailkeeper.network.InspectionFormDto
import com.asnidev.trailkeeper.network.JobTypeDto
import com.asnidev.trailkeeper.network.MessageDto
import com.asnidev.trailkeeper.network.NotificationDto
import com.asnidev.trailkeeper.network.ProjectDto
import com.asnidev.trailkeeper.network.ProjectMemberDto
import com.asnidev.trailkeeper.network.SegmentWorkDto
import com.asnidev.trailkeeper.network.StructureDto
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
        updatedAt = updatedAt,
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
        updatedAt = updatedAt,
    )

fun ProjectMemberDto.toEntity(projectId: String) =
    ProjectMemberEntity(
        projectId = projectId,
        userId = userId,
        email = email,
        name = name,
        projectRole = projectRole,
    )

fun MessageDto.toEntity() =
    MessageEntity(
        id = id,
        projectId = projectId,
        taskId = taskId,
        authorId = authorId,
        body = body,
        mentionedUserIdsJson = gson.toJson(mentionedUserIds),
        createdAt = createdAt,
    )

fun JobTypeDto.toEntity() =
    JobTypeEntity(
        id = id,
        activity = activity,
        key = key,
        label = label,
        unit = unit,
        defaultCrew = defaultCrew,
        expectedRate = expectedRate,
        color = color,
        sortGroup = sortGroup,
    )

fun SegmentWorkDto.toEntity() =
    SegmentWorkEntity(
        id = id,
        projectId = projectId,
        jobTypeId = jobTypeId,
        trailId = trailId,
        quantity = quantity,
        unit = unit,
        quantitySource = quantitySource,
        startedAt = startedAt,
        endedAt = endedAt,
        activeSeconds = activeSeconds,
        crewSize = crewSize,
        equipmentJson = gson.toJson(equipment),
        notes = notes,
        createdById = createdById,
        personHours = personHours,
        rateMinPerUnit = rateMinPerUnit,
        vsExpectedMinPerUnit = vsExpectedMinPerUnit,
    )

fun StructureDto.toEntity() =
    StructureEntity(
        id = id,
        organisationId = organisationId,
        name = name,
        structureType = structureType,
        status = status,
        geometryJson = geometry?.toString(),
        nearestTrailId = nearestTrailId,
        material = material,
        installedOn = installedOn,
        inspectionIntervalDays = inspectionIntervalDays,
        notes = notes,
    )

fun InspectionFormDto.toEntity() =
    InspectionFormEntity(
        id = id,
        name = name,
        targetType = targetType,
        fieldsJson = gson.toJson(fields),
        version = version,
        isActive = isActive,
    )

fun InspectionDto.toEntity() =
    InspectionEntity(
        id = id,
        projectId = projectId,
        structureId = structureId,
        formId = formId,
        formVersion = formVersion,
        inspectorId = inspectorId,
        inspectedOn = inspectedOn,
        answersJson = answers?.toString() ?: "{}",
        risk = risk,
        condition = condition,
        notes = notes,
    )

fun NotificationDto.toEntity() =
    NotificationEntity(
        id = id,
        type = type,
        subjectType = subjectType,
        subjectId = subjectId,
        projectId = projectId,
        actorId = actorId,
        body = body,
        createdAt = createdAt,
        readAt = readAt,
    )
