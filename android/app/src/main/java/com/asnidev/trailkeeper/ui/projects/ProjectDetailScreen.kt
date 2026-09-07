package com.asnidev.trailkeeper.ui.projects

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
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
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
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
import com.asnidev.trailkeeper.network.TaskDto
import com.asnidev.trailkeeper.network.TrailDto
import kotlin.math.roundToInt

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
                    IconButton(onClick = vm::refresh) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                    }
                },
            )
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            val tasks = s.snapshot?.tasks.orEmpty()
            val trails = s.snapshot?.trails.orEmpty()
            TabRow(selectedTabIndex = tab) {
                Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("Tasks (${tasks.size})") })
                Tab(selected = tab == 1, onClick = { tab = 1 }, text = { Text("Trails (${trails.size})") })
            }

            Box(Modifier.fillMaxSize()) {
                when {
                    s.loading && s.snapshot == null ->
                        CircularProgressIndicator(Modifier.align(Alignment.Center))
                    s.error != null && s.snapshot == null ->
                        Text(
                            s.error!!,
                            Modifier.align(Alignment.Center).padding(32.dp),
                            color = MaterialTheme.colorScheme.error,
                        )
                    tab == 0 -> TaskList(tasks)
                    else -> TrailList(trails)
                }
            }
        }
    }
}

@Composable
private fun TaskList(tasks: List<TaskDto>) {
    if (tasks.isEmpty()) {
        EmptyHint("No tasks in this project yet.")
        return
    }
    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        items(tasks, key = { it.id }) { t ->
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
                            if (t.photos.isNotEmpty()) append(" · ${t.photos.size} photo${plural(t.photos.size)}")
                            if (t.assigneeIds.isNotEmpty()) {
                                append(" · ${t.assigneeIds.size} assignee${plural(t.assigneeIds.size)}")
                            }
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
                }
            }
        }
    }
}

@Composable
private fun TrailList(trails: List<TrailDto>) {
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
        Text(text, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

private fun plural(n: Int) = if (n == 1) "" else "s"

private fun km(m: Double): String =
    if (m < 950) "${m.roundToInt()} m" else "${(m / 100).roundToInt() / 10.0} km"
