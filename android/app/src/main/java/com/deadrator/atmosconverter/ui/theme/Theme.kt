package com.deadrator.atmosconverter.ui.theme

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * "Ink & Phosphor" — a control-room instrument palette.
 *
 * Warm = human presence (the listener, primary actions): amber phosphor.
 * Cool = the signal path (meters, waveforms, data): cyan.
 * Everything else is quiet control-room darkness and hairline edges.
 */
object Palette {
    val Bg = Color(0xFF0C1017)
    val CanvasBg = Color(0xFF090C12)
    val Surface = Color(0xFF151B26)
    val Surface3 = Color(0xFF1B2331)
    val Border = Color(0xFF273142)
    val Text = Color(0xFFEAEDF2)
    val Muted = Color(0xFF8B95A5)
    val Ok = Color(0xFF7BD88B)
    val Err = Color(0xFFFF7A6B)
    val Warn = Color(0xFFE8B34B)
    val Front = Color(0xFF5CC8FF)   // cool cyan — front field
    val Rear = Color(0xFFFF7A6B)    // warm coral — rear field
    val Side = Color(0xFF7BD88B)    // mint — side field
    val Head = Color(0xFFE8B34B)    // amber — the listener
    val Accent = Color(0xFFE8B34B)  // phosphor — primary action
}

/**
 * Mono is the instrument voice: every technical readout (degrees, kbps,
 * kHz, timecode, filter strings) is set in monospace so data reads as data.
 */
object Type {
    val Mono = FontFamily.Monospace

    /** Small uppercase section label — reads like an instrument badge. */
    val Eyebrow = TextStyle(
        fontFamily = Mono,
        fontSize = 11.sp,
        letterSpacing = 2.4.sp,
        fontWeight = FontWeight.Medium,
        color = Palette.Muted
    )

    /** Technical readout / data value. */
    val Data = TextStyle(
        fontFamily = Mono,
        fontSize = 12.sp,
        color = Palette.Muted
    )

    /** Title used sparingly across screens. */
    val Title = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 21.sp,
        color = Palette.Text
    )
}

/**
 * A hairline-edged equipment panel. Replaces default Cards: no shadow,
 * just a thin Edge border — like a faceplate on a rack unit.
 */
@Composable
fun Panel(
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit
) {
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = Palette.Surface),
        border = BorderStroke(1.dp, Palette.Border),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp)
    ) {
        Box(modifier = Modifier) { content() }
    }
}

private val DarkColors = darkColorScheme(
    primary = Palette.Accent,
    onPrimary = Color(0xFF1A1200),
    secondary = Palette.Side,
    onSecondary = Color.Black,
    background = Palette.Bg,
    onBackground = Palette.Text,
    surface = Palette.Surface,
    onSurface = Palette.Text,
    surfaceVariant = Palette.Surface3,
    onSurfaceVariant = Palette.Muted,
    error = Palette.Err,
    onError = Color(0xFF1A0505),
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
