package com.asnidev.trailkeeper.ui.projects

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Comment
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Button
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Tab
import androidx.compose.material3.ScrollableTabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.asnidev.trailkeeper.network.StructurePatchRequest
import com.asnidev.trailkeeper.ui.common.PointPickerScreen
import com.asnidev.trailkeeper.ui.map.MapFocus
import com.asnidev.trailkeeper.ui.structures.ColorPicker
import com.asnidev.trailkeeper.ui.map.ProjectMap
import com.asnidev.trailkeeper.ui.segments.SegmentWorkTab
import com.asnidev.trailkeeper.ui.segments.SegmentWorkViewModel
import com.asnidev.trailkeeper.ui.record.RouteTab
import com.asnidev.trailkeeper.ui.structures.StructuresTab
import com.asnidev.trailkeeper.ui.structures.StructuresViewModel
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.asnidev.trailkeeper.data.local.StructureEntity
import com.asnidev.trailkeeper.data.local.TaskEntity
import com.asnidev.trailkeeper.data.local.TrailEntity
import com.asnidev.trailkeeper.data.local.TrackEntity
import com.google.android.gms.location.LocationServices
import com.google.gson.JsonParser
import kotlin.coroutines.resume
import kotlin.math.roundToInt
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine

private val PRIORITIES = listOf("low", "medium", "high", "urgent")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProjectDetailScreen(projectId: String, projectName: String, onBack: () -> Unit) {
    val vm: ProjectDetailViewModel =
        viewModel(
            key = "project-$projectId",
            factory = viewModelFactory { initializer { ProjectDetailViewModel(projectId) } },
        )
    val workVm: SegmentWorkViewModel =
        viewModel(
            key = "segwork-$projectId",
            factory = viewModelFactory { initializer { SegmentWorkViewModel(projectId) } },
        )
    val structuresVm: StructuresViewModel =
        viewModel(
            key = "structures-$projectId",
            factory = viewModelFactory { initializer { StructuresViewModel(projectId) } },
        )
    val s by vm.state.collectAsState()
    val structures by structuresVm.structures.collectAsState()
    val tracks by
        remember(projectId) {
            com.asnidev.trailkeeper.data.local.TrailkeeperDb.db
                .trackDao()
                .observeForProject(projectId)
        }
            .collectAsState(initial = emptyList())
    val messages by vm.discussion.collectAsState()
    val commentCounts by vm.taskCommentCounts.collectAsState()
    val unreadCommentTasks by vm.unreadCommentTasks.collectAsState()
    var tab by rememberSaveable { mutableIntStateOf(0) }
    var showAdd by remember { mutableStateOf(false) }

    // Selected entity for the detail bottom-sheet: Pair(kind, id).
    var selected by remember { mutableStateOf<Pair<String, String>?>(null) }
    var mapFocus by remember { mutableStateOf<MapFocus?>(null) }
    var editingTask by remember { mutableStateOf<TaskEntity?>(null) }
    var movingTask by remember { mutableStateOf<TaskEntity?>(null) }
    var movingStructure by remember { mutableStateOf<StructureEntity?>(null) }
    var discussingTask by remember { mutableStateOf<TaskEntity?>(null) }

    fun geomLatLon(json: String?): Pair<Double, Double>? =
        runCatching {
            val c = JsonParser.parseString(json).asJsonObject.getAsJsonArray("coordinates")
            c[1].asDouble to c[0].asDouble
        }.getOrNull()

    fun focusOnMap(json: String?) {
        geomLatLon(json)?.let { (lat, lon) ->
            mapFocus = MapFocus(lat, lon, System.currentTimeMillis())
            tab = 1 // Map
        }
    }

    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var hasLocation by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
                PackageManager.PERMISSION_GRANTED
        )
    }
    val requestLocation =
        rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
            hasLocation = it
        }
    val requestNotifications =
        rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {}
    // Tab order: 0 Tasks · 1 Map · 2 Route · 3 Trails · 4 Work · 5 Structures · 6 Discussion
    LaunchedEffect(tab) {
        if (tab in intArrayOf(1, 2, 3, 4, 5) && !hasLocation) {
            requestLocation.launch(Manifest.permission.ACCESS_FINE_LOCATION)
        }
        if ((tab == 2 || tab == 3) && android.os.Build.VERSION.SDK_INT >= 33) {
            requestNotifications.launch("android.permission.POST_NOTIFICATIONS")
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(projectName, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = vm::refresh, enabled = !s.syncing) {
                        Icon(Icons.Default.Refresh, contentDescription = "Sync")
                    }
                },
            )
        },
        floatingActionButton = {
            if (tab == 0) {
                FloatingActionButton(onClick = { showAdd = true }) {
                    Icon(Icons.Default.Add, contentDescription = "New task")
                }
            }
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            if (s.syncing) LinearProgressIndicator(Modifier.fillMaxWidth())
            s.error?.let {
                Surface(
                    color = MaterialTheme.colorScheme.errorContainer,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(
                        it,
                        Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onErrorContainer,
                    )
                }
            }

            ScrollableTabRow(selectedTabIndex = tab, edgePadding = 8.dp) {
                Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("Tasks") })
                Tab(selected = tab == 1, onClick = { tab = 1 }, text = { Text("Map") })
                Tab(selected = tab == 2, onClick = { tab = 2 }, text = { Text("Route") })
                Tab(selected = tab == 3, onClick = { tab = 3 }, text = { Text("Trails") })
                Tab(selected = tab == 4, onClick = { tab = 4 }, text = { Text("Work") })
                Tab(selected = tab == 5, onClick = { tab = 5 }, text = { Text("Structures") })
                Tab(selected = tab == 6, onClick = { tab = 6 }, text = { Text("Discussion") })
            }

            Box(Modifier.fillMaxSize()) {
                val moveTask = movingTask
                val moveStructure = movingStructure
                val chatTask = discussingTask
                when {
                    !s.loaded -> CircularProgressIndicator(Modifier.align(Alignment.Center))
                    chatTask != null -> {
                        val rows by
                            remember(chatTask.id) { vm.taskThread(chatTask.id) }
                                .collectAsState(initial = emptyList())
                        TaskDiscussionScreen(
                            taskTitle = chatTask.title,
                            messages = rows,
                            onSend = { vm.postMessage(it, taskId = chatTask.id) },
                            onDelete = vm::deleteMessage,
                            onBack = { discussingTask = null },
                        )
                    }
                    moveTask != null ->
                        PointPickerScreen(
                            title = "Move \"${moveTask.title}\"",
                            hasLocation = hasLocation,
                            initial = geomLatLon(moveTask.geometryJson),
                            onDone = { lat, lon ->
                                vm.moveTask(moveTask.id, lat, lon)
                                movingTask = null
                            },
                            onCancel = { movingTask = null },
                        )
                    moveStructure != null ->
                        PointPickerScreen(
                            title = "Move \"${moveStructure.name}\"",
                            hasLocation = hasLocation,
                            initial = geomLatLon(moveStructure.geometryJson),
                            onDone = { lat, lon ->
                                structuresVm.moveStructure(moveStructure.id, lat, lon)
                                movingStructure = null
                            },
                            onCancel = { movingStructure = null },
                        )
                    tab == 0 ->
                        TaskList(
                            s.tasks,
                            commentCounts = commentCounts,
                            unreadTasks = unreadCommentTasks,
                            onSetStatus = vm::setStatus,
                            onOpen = { t -> selected = "task" to t.id; focusOnMap(t.geometryJson) },
                        )
                    tab == 1 ->
                        ProjectMap(
                            trails = s.trails,
                            tasks = s.tasks,
                            structures = structures,
                            tracks = tracks,
                            hasLocationPermission = hasLocation,
                            modifier = Modifier.fillMaxSize(),
                            focus = mapFocus,
                            onFeatureTap = { kind, id -> selected = kind to id },
                        )
                    tab == 2 ->
                        RouteTab(
                            projectId = projectId,
                            activity = s.project?.activity ?: "mtb",
                            hasLocation = hasLocation,
                        )
                    tab == 3 ->
                        TrailList(
                            s.trails,
                            projectId = projectId,
                            hasLocation = hasLocation,
                            onSaveWalkedTrail = { name -> vm.saveWalkedTrail(name, s.project?.activity ?: "mtb") },
                            onOpen = { tr -> selected = "trail" to tr.id; focusOnMap(tr.geometryJson) },
                        )
                    tab == 4 -> SegmentWorkTab(workVm, s.trails, hasLocation)
                    tab == 5 -> StructuresTab(structuresVm, hasLocation)
                    else ->
                        DiscussionTab(
                            messages,
                            onSend = { vm.postMessage(it) },
                            onDelete = vm::deleteMessage,
                        )
                }
            }
        }
    }

    if (showAdd) {
        AddTaskDialog(
            onDismiss = { showAdd = false },
            onCreate = { title, priority ->
                showAdd = false
                scope.launch {
                    val loc = if (hasLocation) currentDeviceLocation(context) else null
                    vm.addTask(title, priority, loc?.latitude, loc?.longitude)
                }
            },
        )
    }

    val sel = selected
    if (sel != null) {
        val (kind, id) = sel
        val task = if (kind == "task") s.tasks.firstOrNull { it.id == id } else null
        val trail = if (kind == "trail") s.trails.firstOrNull { it.id == id } else null
        val structure = if (kind == "structure") structures.firstOrNull { it.id == id } else null
        val track = if (kind == "track") tracks.firstOrNull { it.id == id } else null
        if (task == null && trail == null && structure == null && track == null) {
            selected = null
        } else {
            ModalBottomSheet(onDismissRequest = { selected = null }) {
                Column(
                    Modifier.fillMaxWidth().padding(horizontal = 20.dp).padding(bottom = 28.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    when {
                        task != null ->
                            TaskDetailBody(
                                task = task,
                                onShowOnMap = { focusOnMap(task.geometryJson); selected = null },
                                onEdit = { editingTask = task; selected = null },
                                onToggleDone = {
                                    vm.setStatus(task.id, if (task.status == "done") "open" else "done")
                                },
                                onMove = { movingTask = task; selected = null },
                                onDiscuss = {
                                    vm.markTaskCommentsRead(task.id)
                                    discussingTask = task
                                    selected = null
                                },
                                onUploadPhoto = { file -> vm.uploadTaskPhoto(task.id, file) },
                                onDeletePhoto = { photoId -> vm.deleteTaskPhoto(task.id, photoId) },
                            )
                        structure != null ->
                            StructureDetailBody(
                                structure = structure,
                                onShowOnMap = { focusOnMap(structure.geometryJson); selected = null },
                                onPatch = { structuresVm.patchStructure(structure.id, it) },
                                onMove = { movingStructure = structure; selected = null },
                                onDelete = { structuresVm.deleteStructure(structure.id); selected = null },
                            )
                        trail != null -> {
                            Text(trail.name, style = MaterialTheme.typography.titleLarge)
                            Text(
                                "${trail.activity} · ${trail.status.replace('_', ' ')} · ${km(trail.lengthM)}",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            OutlinedButton(onClick = { focusOnMap(trail.geometryJson); selected = null }) {
                                Text("Show on map")
                            }
                        }
                        track != null -> {
                            Text(track.name, style = MaterialTheme.typography.titleLarge)
                            Text(
                                "${km(track.lengthM)} · ${track.pointCount} points · ${track.source}",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            OutlinedButton(onClick = { focusOnMap(track.geometryJson); selected = null }) {
                                Text("Show on map")
                            }
                        }
                    }
                }
            }
        }
    }

    editingTask?.let { t ->
        EditTaskDialog(
            task = t,
            onDismiss = { editingTask = null },
            onSave = { title, desc, priority ->
                vm.editTask(t.id, title, desc, priority)
                editingTask = null
            },
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun TaskDetailBody(
    task: TaskEntity,
    onShowOnMap: () -> Unit,
    onEdit: () -> Unit,
    onToggleDone: () -> Unit,
    onMove: () -> Unit,
    onDiscuss: () -> Unit,
    onUploadPhoto: (java.io.File) -> Unit,
    onDeletePhoto: (String) -> Unit,
) {
    var viewingPhoto by remember { mutableStateOf<String?>(null) }
    Row(verticalAlignment = Alignment.CenterVertically) {
        PriorityTag(task.priority)
        Text(task.title, style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(start = 8.dp))
    }
    Text(
        task.status.replace('_', ' ') + if (task.geometryJson == null) " · no location" else "",
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    if (task.description.isNotBlank()) Text(task.description, style = MaterialTheme.typography.bodyMedium)
    TaskPhotoStrip(
        task = task,
        onUpload = onUploadPhoto,
        onDelete = onDeletePhoto,
        onOpen = { viewingPhoto = it },
    )
    viewingPhoto?.let { url -> PhotoViewerDialog(url = url, onClose = { viewingPhoto = null }) }
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Button(onClick = onEdit) { Text("Edit") }
        OutlinedButton(onClick = onDiscuss) { Text("Discussion") }
        OutlinedButton(onClick = onToggleDone) {
            Text(if (task.status == "done") "Reopen" else "Mark done")
        }
        OutlinedButton(onClick = onMove) { Text(if (task.geometryJson == null) "Set location" else "Move") }
        if (task.geometryJson != null) OutlinedButton(onClick = onShowOnMap) { Text("Show on map") }
    }
}

@Composable
private fun TaskDiscussionScreen(
    taskTitle: String,
    messages: List<MessageRow>,
    onSend: (String) -> Unit,
    onDelete: (String) -> Unit,
    onBack: () -> Unit,
) {
    Column(Modifier.fillMaxSize()) {
        Surface(tonalElevation = 2.dp) {
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                IconButton(onClick = onBack) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                }
                Text(
                    taskTitle,
                    style = MaterialTheme.typography.titleMedium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        DiscussionTab(messages = messages, onSend = onSend, onDelete = onDelete)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun StructureDetailBody(
    structure: StructureEntity,
    onShowOnMap: () -> Unit,
    onPatch: (StructurePatchRequest) -> Unit,
    onMove: () -> Unit,
    onDelete: () -> Unit,
) {
    val statuses = listOf("good", "monitor", "needs_repair", "failed", "decommissioned")
    var confirmDelete by remember { mutableStateOf(false) }
    var name by remember(structure.id) { mutableStateOf(structure.name) }

    OutlinedTextField(
        value = name,
        onValueChange = { name = it },
        label = { Text("Name") },
        singleLine = true,
        trailingIcon = {
            if (name.isNotBlank() && name != structure.name) {
                TextButton(onClick = { onPatch(StructurePatchRequest(name = name.trim())) }) {
                    Text("Rename")
                }
            }
        },
        modifier = Modifier.fillMaxWidth(),
    )
    Text(
        structure.structureType.replace('_', ' ') +
            (if (structure.material.isNotBlank()) " · ${structure.material}" else ""),
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    if (structure.notes.isNotBlank()) Text(structure.notes, style = MaterialTheme.typography.bodyMedium)
    Text("Status", style = MaterialTheme.typography.labelLarge)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        statuses.forEach { st ->
            FilterChip(
                selected = structure.status == st,
                onClick = { onPatch(StructurePatchRequest(status = st)) },
                label = { Text(st.replace('_', ' ')) },
            )
        }
    }
    Text("Marker colour", style = MaterialTheme.typography.labelLarge)
    ColorPicker(selected = structure.color, onSelect = { onPatch(StructurePatchRequest(color = it)) })
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedButton(onClick = onMove) {
            Text(if (structure.geometryJson == null) "Set location" else "Move")
        }
        if (structure.geometryJson != null) OutlinedButton(onClick = onShowOnMap) { Text("Show on map") }
        Button(
            colors = androidx.compose.material3.ButtonDefaults.buttonColors(
                containerColor = MaterialTheme.colorScheme.error
            ),
            onClick = { confirmDelete = true },
        ) { Text("Delete") }
    }
    if (confirmDelete) {
        AlertDialog(
            onDismissRequest = { confirmDelete = false },
            title = { Text("Delete structure?") },
            text = { Text("\"${structure.name}\" and its inspections will be removed.") },
            confirmButton = {
                TextButton(onClick = { confirmDelete = false; onDelete() }) { Text("Delete") }
            },
            dismissButton = { TextButton(onClick = { confirmDelete = false }) { Text("Cancel") } },
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun EditTaskDialog(
    task: TaskEntity,
    onDismiss: () -> Unit,
    onSave: (String, String, String) -> Unit,
) {
    var title by remember { mutableStateOf(task.title) }
    var desc by remember { mutableStateOf(task.description) }
    var priority by remember { mutableStateOf(task.priority) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Edit task") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = title,
                    onValueChange = { title = it },
                    label = { Text("Title") },
                    singleLine = true,
                )
                OutlinedTextField(
                    value = desc,
                    onValueChange = { desc = it },
                    label = { Text("Description") },
                    maxLines = 4,
                )
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    PRIORITIES.forEach { p ->
                        FilterChip(selected = priority == p, onClick = { priority = p }, label = { Text(p) })
                    }
                }
            }
        },
        confirmButton = {
            TextButton(enabled = title.isNotBlank(), onClick = { onSave(title, desc, priority) }) {
                Text("Save")
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TaskList(
    tasks: List<TaskEntity>,
    commentCounts: Map<String, Int>,
    unreadTasks: Set<String>,
    onSetStatus: (String, String) -> Unit,
    onOpen: (TaskEntity) -> Unit,
) {
    if (tasks.isEmpty()) {
        EmptyHint("No tasks in this project yet. Tap + to add one.")
        return
    }
    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        items(tasks, key = { it.id }) { t ->
            val photos = jsonArraySize(t.photosJson)
            val assignees = jsonArraySize(t.assigneeIdsJson)
            val comments = commentCounts[t.id] ?: 0
            val unread = t.id in unreadTasks
            val commentTint =
                if (unread) MaterialTheme.colorScheme.primary
                else MaterialTheme.colorScheme.onSurfaceVariant
            Card(onClick = { onOpen(t) }, modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        PriorityTag(t.priority)
                        Text(
                            t.title,
                            style = MaterialTheme.typography.titleMedium,
                            modifier = Modifier.padding(start = 8.dp).weight(1f, fill = false),
                        )
                        if (comments > 0) {
                            Spacer(Modifier.weight(1f))
                            Icon(
                                Icons.AutoMirrored.Filled.Comment,
                                contentDescription = if (unread) "Unread comments" else "Comments",
                                modifier = Modifier.size(16.dp),
                                tint = commentTint,
                            )
                            Text(
                                " $comments",
                                style = MaterialTheme.typography.labelMedium,
                                fontWeight = if (unread) FontWeight.Bold else null,
                                color = commentTint,
                            )
                        }
                    }
                    Text(
                        buildString {
                            append(t.status.replace('_', ' '))
                            if (t.taskType.isNotBlank()) append(" · ${t.taskType}")
                            if (photos > 0) append(" · $photos photo${plural(photos)}")
                            if (assignees > 0) append(" · $assignees assignee${plural(assignees)}")
                        },
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    if (t.description.isNotBlank()) {
                        Text(
                            t.description,
                            style = MaterialTheme.typography.bodySmall,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                        if (t.status == "done") {
                            TextButton(onClick = { onSetStatus(t.id, "open") }) { Text("Reopen") }
                        } else {
                            TextButton(onClick = { onSetStatus(t.id, "done") }) { Text("Mark done") }
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
private fun TrailList(
    trails: List<TrailEntity>,
    projectId: String,
    hasLocation: Boolean,
    onSaveWalkedTrail: (String) -> Unit,
    onOpen: (TrailEntity) -> Unit,
) {
    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item { WalkTrailCard(projectId, hasLocation, onSaveWalkedTrail) }
        if (trails.isEmpty()) {
            item {
                Text(
                    "No trails yet — record one by walking it, or draw one in the web console.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        items(trails, key = { it.id }) { tr ->
            Card(onClick = { onOpen(tr) }, modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(tr.name, style = MaterialTheme.typography.titleMedium)
                    Text(
                        "${tr.activity} · ${tr.status.replace('_', ' ')} · ${km(tr.lengthM)}",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun WalkTrailCard(projectId: String, hasLocation: Boolean, onSave: (String) -> Unit) {
    val context = LocalContext.current
    val rec by com.asnidev.trailkeeper.record.TrackRecorder.state.collectAsState()
    var name by remember { mutableStateOf("") }
    val phase = rec.phase

    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Record a trail by walking it", style = MaterialTheme.typography.titleSmall)
            when (phase) {
                com.asnidev.trailkeeper.record.RecPhase.IDLE ->
                    Button(
                        enabled = hasLocation,
                        onClick = {
                            com.asnidev.trailkeeper.record.TrackRecordingService.start(context, projectId)
                        },
                    ) { Text(if (hasLocation) "＋ Start recording" else "Location permission needed") }

                com.asnidev.trailkeeper.record.RecPhase.RECORDING,
                com.asnidev.trailkeeper.record.RecPhase.PAUSED -> {
                    Text(
                        "%.2f km · %d points%s".format(
                            rec.distanceM / 1000.0,
                            rec.points.size,
                            if (phase == com.asnidev.trailkeeper.record.RecPhase.PAUSED) " · paused" else "",
                        ),
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (phase == com.asnidev.trailkeeper.record.RecPhase.RECORDING) {
                            OutlinedButton(onClick = {
                                com.asnidev.trailkeeper.record.TrackRecordingService.pause(context)
                            }) { Text("Pause") }
                        } else {
                            Button(onClick = {
                                com.asnidev.trailkeeper.record.TrackRecordingService.resume(context)
                            }) { Text("Resume") }
                        }
                        OutlinedButton(onClick = {
                            com.asnidev.trailkeeper.record.TrackRecordingService.stop(context)
                        }) { Text("Stop") }
                    }
                }

                com.asnidev.trailkeeper.record.RecPhase.STOPPED -> {
                    Text(
                        "%.2f km · %d points".format(rec.distanceM / 1000.0, rec.points.size),
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    OutlinedTextField(
                        value = name,
                        onValueChange = { name = it },
                        label = { Text("Trail name") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(
                            enabled = name.isNotBlank() && rec.points.size >= 2,
                            onClick = { onSave(name); name = "" },
                        ) { Text("Save as trail") }
                        OutlinedButton(onClick = {
                            com.asnidev.trailkeeper.record.TrackRecorder.reset(); name = ""
                        }) { Text("Discard") }
                    }
                }
            }
        }
    }
}

/** Best-effort current fix from the fused provider; null if unavailable. */
@SuppressLint("MissingPermission")
private suspend fun currentDeviceLocation(context: Context): android.location.Location? =
    suspendCancellableCoroutine { cont ->
        LocationServices.getFusedLocationProviderClient(context).lastLocation
            .addOnSuccessListener { cont.resume(it) }
            .addOnFailureListener { cont.resume(null) }
    }

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun AddTaskDialog(onDismiss: () -> Unit, onCreate: (String, String) -> Unit) {
    var title by remember { mutableStateOf("") }
    var priority by remember { mutableStateOf("medium") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("New task") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = title,
                    onValueChange = { title = it },
                    label = { Text("Title") },
                    singleLine = true,
                )
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    PRIORITIES.forEach { p ->
                        FilterChip(
                            selected = priority == p,
                            onClick = { priority = p },
                            label = { Text(p) },
                        )
                    }
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onCreate(title, priority) },
                enabled = title.isNotBlank(),
            ) {
                Text("Add")
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun PriorityTag(priority: String) {
    val color =
        when (priority) {
            "urgent" -> MaterialTheme.colorScheme.error
            "high" -> Color(0xFFD6A64B)
            "low" -> MaterialTheme.colorScheme.onSurfaceVariant
            else -> MaterialTheme.colorScheme.primary
        }
    Surface(color = color, shape = RoundedCornerShape(4.dp)) {
        Text(
            priority.uppercase(),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onPrimary,
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
        )
    }
}

@Composable
private fun EmptyHint(text: String) {
    Box(Modifier.fillMaxSize().padding(32.dp), contentAlignment = Alignment.Center) {
        Text(
            text,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

private fun jsonArraySize(json: String): Int =
    runCatching { JsonParser.parseString(json).asJsonArray.size() }.getOrDefault(0)

private fun plural(n: Int) = if (n == 1) "" else "s"

private fun km(m: Double): String =
    if (m < 950) "${m.roundToInt()} m" else "${(m / 100).roundToInt() / 10.0} km"

@Composable
private fun DiscussionTab(
    messages: List<MessageRow>,
    onSend: (String) -> Unit,
    onDelete: (String) -> Unit = {},
) {
    var draft by rememberSaveable { mutableStateOf("") }
    val listState = rememberLazyListState()

    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) listState.animateScrollToItem(messages.lastIndex)
    }

    Column(Modifier.fillMaxSize()) {
        if (messages.isEmpty()) {
            Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                Text(
                    "No messages yet. Start the conversation.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        } else {
            LazyColumn(
                state = listState,
                modifier = Modifier.weight(1f).fillMaxWidth(),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(messages, key = { it.id }) { m -> MessageBubble(m, onDelete = { onDelete(m.id) }) }
            }
        }

        Surface(tonalElevation = 2.dp) {
            Row(
                Modifier.fillMaxWidth().padding(8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OutlinedTextField(
                    value = draft,
                    onValueChange = { draft = it },
                    modifier = Modifier.weight(1f),
                    placeholder = { Text("Message") },
                    maxLines = 4,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                    keyboardActions =
                        KeyboardActions(
                            onSend = {
                                onSend(draft)
                                draft = ""
                            }
                        ),
                )
                IconButton(
                    onClick = {
                        onSend(draft)
                        draft = ""
                    },
                    enabled = draft.isNotBlank(),
                ) {
                    Icon(Icons.AutoMirrored.Filled.Send, contentDescription = "Send")
                }
            }
        }
    }
}

@Composable
private fun MessageBubble(m: MessageRow, onDelete: () -> Unit) {
    val bg =
        if (m.mine) MaterialTheme.colorScheme.primaryContainer
        else MaterialTheme.colorScheme.surfaceVariant
    var confirm by remember { mutableStateOf(false) }
    Column {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                "${m.authorName} · ${formatTime(m.createdAt)}",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (m.mine) {
                TextButton(onClick = { confirm = true }, contentPadding = PaddingValues(horizontal = 6.dp)) {
                    Text("Delete", style = MaterialTheme.typography.labelSmall)
                }
            }
        }
        Surface(color = bg, shape = RoundedCornerShape(10.dp)) {
            Text(m.body, Modifier.padding(horizontal = 12.dp, vertical = 8.dp))
        }
    }
    if (confirm) {
        AlertDialog(
            onDismissRequest = { confirm = false },
            title = { Text("Delete comment?") },
            confirmButton = { TextButton(onClick = { confirm = false; onDelete() }) { Text("Delete") } },
            dismissButton = { TextButton(onClick = { confirm = false }) { Text("Cancel") } },
        )
    }
}

private fun formatTime(iso: String): String =
    runCatching {
            java.time.Instant.parse(iso)
                .atZone(java.time.ZoneId.systemDefault())
                .format(java.time.format.DateTimeFormatter.ofPattern("d MMM HH:mm"))
        }
        .getOrDefault(iso.take(16).replace('T', ' '))
