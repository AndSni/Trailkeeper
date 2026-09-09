package com.asnidev.trailkeeper.ui.projects

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.gestures.waitForUpOrCancellation
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import coil.compose.AsyncImage
import com.asnidev.trailkeeper.data.ImageCompress
import com.asnidev.trailkeeper.data.local.TaskEntity
import com.asnidev.trailkeeper.network.ApiClient
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull

data class TaskPhotoRef(val id: String = "", val caption: String = "", val url: String = "")

private val gson = Gson()
private val PHOTO_LIST = object : TypeToken<List<TaskPhotoRef>>() {}.type

fun parseTaskPhotos(json: String): List<TaskPhotoRef> =
    runCatching { gson.fromJson<List<TaskPhotoRef>>(json, PHOTO_LIST) }.getOrDefault(emptyList())

@Composable
fun TaskPhotoStrip(
    task: TaskEntity,
    onUpload: (java.io.File) -> Unit,
    onDelete: (photoId: String) -> Unit,
    onOpen: (url: String) -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val photos = remember(task.photosJson) { parseTaskPhotos(task.photosJson) }
    var working by remember { mutableStateOf(false) }
    var pendingDelete by remember { mutableStateOf<TaskPhotoRef?>(null) }

    val picker =
        rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
            if (uri != null) {
                working = true
                scope.launch {
                    val file =
                        withContext(Dispatchers.IO) {
                            runCatching { ImageCompress.compressForUpload(context, uri) }.getOrNull()
                        }
                    working = false
                    if (file != null) onUpload(file)
                }
            }
        }

    Text("Photos (${photos.size})", style = MaterialTheme.typography.labelLarge)
    Text(
        "Tap to view · hold to delete",
        style = MaterialTheme.typography.labelSmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        item {
            OutlinedButton(
                onClick = {
                    picker.launch(
                        PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)
                    )
                },
                modifier = Modifier.size(96.dp),
                enabled = !working,
            ) {
                if (working) CircularProgressIndicator(Modifier.size(18.dp))
                else Icon(Icons.Default.Add, contentDescription = "Add photo")
            }
        }
        items(photos, key = { it.id }) { p ->
            val url = ApiClient.absoluteUrl(p.url)
            AsyncImage(
                model = url,
                contentDescription = p.caption,
                contentScale = ContentScale.Crop,
                modifier =
                    Modifier.size(96.dp)
                        .clip(RoundedCornerShape(8.dp))
                        .pointerInput(p.id) {
                            awaitEachGesture {
                                awaitFirstDown()
                                var released = false
                                val heldFull =
                                    withTimeoutOrNull(1_000L) {
                                        released = waitForUpOrCancellation() != null
                                        true
                                    } == null
                                when {
                                    heldFull -> {
                                        pendingDelete = p
                                        waitForUpOrCancellation()
                                    }
                                    released -> url?.let(onOpen)
                                }
                            }
                        },
            )
        }
    }

    pendingDelete?.let { photo ->
        AlertDialog(
            onDismissRequest = { pendingDelete = null },
            title = { Text("Delete photo?") },
            text = { Text("This removes the photo for everyone. It can't be undone.") },
            confirmButton = {
                TextButton(
                    onClick = {
                        onDelete(photo.id)
                        pendingDelete = null
                    }
                ) {
                    Text("Delete")
                }
            },
            dismissButton = { TextButton(onClick = { pendingDelete = null }) { Text("Cancel") } },
        )
    }
}

@Composable
fun PhotoViewerDialog(url: String, onClose: () -> Unit) {
    Dialog(
        onDismissRequest = onClose,
        properties = DialogProperties(usePlatformDefaultWidth = false),
    ) {
        var scale by remember { mutableFloatStateOf(1f) }
        var offset by remember { mutableStateOf(Offset.Zero) }
        Box(
            Modifier.fillMaxSize()
                .background(Color.Black)
                .pointerInput(Unit) {
                    detectTransformGestures { _, pan, zoom, _ ->
                        scale = (scale * zoom).coerceIn(1f, 6f)
                        offset = if (scale > 1f) offset + pan else Offset.Zero
                    }
                }
        ) {
            AsyncImage(
                model = url,
                contentDescription = null,
                contentScale = ContentScale.Fit,
                modifier =
                    Modifier.fillMaxSize().graphicsLayer {
                        scaleX = scale
                        scaleY = scale
                        translationX = offset.x
                        translationY = offset.y
                    },
            )
            IconButton(onClick = onClose, modifier = Modifier.align(Alignment.TopEnd)) {
                Icon(Icons.Default.Close, contentDescription = "Close", tint = Color.White)
            }
            Column(
                Modifier.align(Alignment.BottomCenter).padding(16.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text(
                    "Pinch to zoom",
                    color = Color.White.copy(alpha = 0.6f),
                    style = MaterialTheme.typography.labelSmall,
                    modifier = Modifier.height(16.dp),
                )
            }
        }
    }
}
