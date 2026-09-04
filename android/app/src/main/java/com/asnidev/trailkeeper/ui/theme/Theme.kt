package com.asnidev.trailkeeper.ui.theme

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color

// Moss-on-birch, dark. Same palette family as docs/BLUEPRINT.md.
private val TrailkeeperDarkColors = darkColorScheme(
    primary = Color(0xFF9CC17F),
    onPrimary = Color(0xFF16210D),
    secondary = Color(0xFF98A188),
    background = Color(0xFF141712),
    surface = Color(0xFF1E241C),
    surfaceVariant = Color(0xFF2C3327),
    onBackground = Color(0xFFE7EADD),
    onSurface = Color(0xFFE7EADD),
    onSurfaceVariant = Color(0xFF98A188),
    outline = Color(0xFF3B4433),
    error = Color(0xFFE27A5C),
    onError = Color(0xFF16210D),
)

@Composable
fun TrailkeeperTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = TrailkeeperDarkColors) {
        // Surface sets LocalContentColor; without it, uncoloured Text falls
        // back to Compose's hardcoded black. (Same note as SharpRight.)
        Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
            content()
        }
    }
}
