package com.asnidev.trailkeeper.ui.projects

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
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
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.asnidev.trailkeeper.data.local.TaskEntity
import com.asnidev.trailkeeper.data.local.TrailEntity
import com.google.gson.JsonParser
import kotlin.math.roundToInt

private val PRIORITIES = listOf("low", "medium", "high", "urgent")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProjectDetailScreen(projectId: String, projectName: String, onBack: () -> Unit) {
    val vm: ProjectDetailViewModel =
        viewModel(
            key = "project-$projectId",
            factory = viewModelFactory { initializer { ProjectDetailViewModel(projectId) } },
        )
    val s by vm.state.collectAsState()
    var tab by rememberSaveable { mutableIntStateOf(0) }
    var showAdd by remember { mutableStateOf(false) }

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

            TabRow(selectedTabIndex = tab) {
                Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("Tasks (${s.tasks.size})") })
                Tab(selected = tab == 1, onClick = { tab = 1 }, text = { Text("Trails (${s.trails.size})") })
            }

            Box(Modifier.fillMaxSize()) {
                when {
                    !s.loaded -> CircularProgressIndicator(Modifier.align(Alignment.Center))
                    tab == 0 -> TaskList(s.tasks, onSetStatus = vm::setStatus)
                    else -> TrailList(s.trails)
                }
            }
        }
    }

    if (showAdd) {
        AddTaskDialog(
            onDismiss = { showAdd = false },
            onCreate = { title, priority ->
                vm.addTask(title, priority)
                showAdd = false
            },
        )
    }
}

@Composable
private fun TaskList(tasks: List<TaskEntity>, onSetStatus: (String, String) -> Unit) {
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
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        PriorityTag(t.priority)
                        Text(
                            t.title,
                            style = MaterialTheme.typography.titleMedium,
                            modifier = Modifier.padding(start = 8.dp),
                        )
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

@Composable
private fun TrailList(trails: List<TrailEntity>) {
    if (trails.isEmpty()) {
        EmptyHint("No trails imported yet.")
        return
    }
    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        items(trails, key = { it.id }) { tr ->
            Card(Modifier.fillMaxWidth()) {
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
