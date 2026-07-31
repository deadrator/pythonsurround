package com.deadrator.atmosconverter.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/**
 * Dark palette mirroring dark_theme.py PALETTE from the desktop app.
 */
object Palette {
    val Bg = Color(0xFF0F1420)
    val CanvasBg = Color(0xFF0A0E17)
    val Surface = Color(0xFF161C2A)
    val Surface3 = Color(0xFF1D2434)
    val Border = Color(0xFF33415E)
    val Text = Color(0xFFE8EDF6)
    val Muted = Color(0xFF93A0B8)
    val Ok = Color(0xFF3DDC84)
    val Err = Color(0xFFFF6B6B)
    val Warn = Color(0xFFFFB454)
    val Front = Color(0xFF4F8CFF)
    val Rear = Color(0xFFFF6B6B)
    val Side = Color(0xFF3DDC84)
    val Head = Color(0xFFE8EDF6)
    val Accent = Color(0xFF4F8CFF)
}

private val DarkColors = darkColorScheme(
    primary = Palette.Accent,
    onPrimary = Color.White,
    secondary = Palette.Side,
    onSecondary = Color.Black,
    background = Palette.Bg,
    onBackground = Palette.Text,
    surface = Palette.Surface,
    onSurface = Palette.Text,
    surfaceVariant = Palette.Surface3,
    onSurfaceVariant = Palette.Muted,
    error = Palette.Err,
    onError = Color.White,
    outline = Palette.Border
)

@Composable
fun AtmosTheme(content: @Composable () -> Unit) {
    // The app is dark-themed by design (matches desktop); ignore system light mode.
    MaterialTheme(
        colorScheme = DarkColors,
        content = content
    )
}
