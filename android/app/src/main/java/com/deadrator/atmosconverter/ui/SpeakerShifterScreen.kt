package com.deadrator.atmosconverter.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp
import com.deadrator.atmosconverter.dsp.SpeakerConfig
import com.deadrator.atmosconverter.dsp.SpeakerFilterGenerator
import com.deadrator.atmosconverter.ui.theme.Palette
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.sin

/**
 * Drag-to-position virtual speakers, ported from the desktop SpeakerCanvas.
 * Dragging rotates the speaker; dragging toward/away from the center moves it
 * NEAR/FAR (distance drives the distance->volume model).
 *
 * `config` + `layout` are shared with the Converter tab (single source of
 * truth, like the desktop app's one speaker_config).
 */
@Composable
fun SpeakerShifterScreen(
    config: SpeakerConfig,
    layout: String,
    onLayoutChange: (String) -> Unit
) {
    var presetName by remember { mutableStateOf<String?>(null) }
    var filterPreview by remember { mutableStateOf<String?>(null) }

    fun refreshPreview() {
        filterPreview = SpeakerFilterGenerator.generateBinauralFilter(config)
    }
    LaunchedEffect(layout) { refreshPreview() }

    // Applying a preset that switches the layout must happen AFTER the new
    // SpeakerConfig is created (layout drives config identity). So we stash
    // the preset and apply it once the layout recomposition has run.
    var pendingPreset by remember { mutableStateOf<Map<String, Double>?>(null) }
    LaunchedEffect(layout) {
        pendingPreset?.let { pos ->
            config.reset()
            pos.forEach { (l, a) -> config.setPosition(l, a) }
            pendingPreset = null
            refreshPreview()
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("🔊 Virtual Speaker Shifter", style = MaterialTheme.typography.headlineSmall)
        Text(
            "Drag speakers around the ring to rotate them; drag toward the center (NEAR) or the edge (FAR) - volume follows distance",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        // Layout + preset row
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedButton(onClick = {
                onLayoutChange(if (layout == "5.1") "7.1" else "5.1")
                presetName = null
            }) {
                Text("Layout: $layout")
            }
            var presetsOpen by remember { mutableStateOf(false) }
            Box {
                OutlinedButton(onClick = { presetsOpen = true }) {
                    Text(presetName ?: "Presets")
                }
                DropdownMenu(expanded = presetsOpen, onDismissRequest = { presetsOpen = false }) {
                    SpeakerConfig.PRESETS.forEach { (name, pos) ->
                        DropdownMenuItem(text = { Text(name) }, onClick = {
                            presetsOpen = false
                            presetName = name
                            val newLayout = if (pos.size > 6) "7.1" else "5.1"
                            if (newLayout != layout) onLayoutChange(newLayout)
                            pendingPreset = pos
                        })
                    }
                }
            }
            OutlinedButton(onClick = {
                config.reset()
                refreshPreview()
                presetName = null
            }) {
                Text("Reset")
            }
        }

        // Draggable ring
        Card {
            SpeakerRingCanvas(
                config = config,
                onChanged = { refreshPreview() },
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(1f)
            )
        }

        // Angle sliders per speaker
        Card {
            Column(
                Modifier
                    .fillMaxWidth()
                    .padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                Text("Angles", style = MaterialTheme.typography.titleSmall)
                config.labels.filter { it != "LFE" }.forEach { label ->
                    val angle = config.getPosition(label)
                    val vol = config.getVolume(label)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("$label", Modifier.width(34.dp))
                        Slider(
                            value = angle.toFloat(),
                            onValueChange = {
                                config.setPosition(label, it.toDouble())
                                refreshPreview()
                            },
                            valueRange = -180f..180f,
                            modifier = Modifier.weight(1f)
                        )
                        Text(
                            "${angle.toInt()}°  ${(vol * 100).toInt()}%",
                            Modifier.width(84.dp),
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }
            }
        }

        // Live filter preview
        Card {
            Column(
                Modifier
                    .fillMaxWidth()
                    .padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                Text("Custom pan filter (used by the Converter)", style = MaterialTheme.typography.titleSmall)
                Text(
                    filterPreview ?: "",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

/**
 * The speaker ring. Renders concentric rings, the "YOU" head, and speaker
 * dots that can be dragged; angle+distance update the SpeakerConfig.
 */
@Composable
fun SpeakerRingCanvas(
    config: SpeakerConfig,
    onChanged: () -> Unit,
    modifier: Modifier = Modifier
) {
    var draggingLabel by remember { mutableStateOf<String?>(null) }
    Canvas(
        modifier = modifier.pointerInput(config) {
            detectDragGestures(
                onDragStart = { offset ->
                    val cx = size.width / 2f
                    val cy = size.height / 2f
                    val r = minOf(size.width, size.height) / 2f * 0.9f
                    var best: String? = null
                    var bestDist = Float.MAX_VALUE
                    for ((label, angle) in config.positionsForFilter()) {
                        val rad = Math.toRadians(angle - 90.0)
                        val dist = config.getDistance(label)
                        val rr = radiusFor(dist, r)
                        val x = cx + (rr * cos(rad)).toFloat()
                        val y = cy + (rr * sin(rad)).toFloat()
                        val d = hypot((offset.x - x).toDouble(), (offset.y - y).toDouble())
                        if (d < 34 && d < bestDist) { best = label; bestDist = d.toFloat() }
                    }
                    draggingLabel = best
                },
                onDrag = { change, _ ->
                    val target = draggingLabel ?: return@detectDragGestures
                    val (angle, dist) = posToAngleDist(
                        change.position.x, change.position.y,
                        size.width / 2f, size.height / 2f
                    )
                    config.setPosition(target, angle, dist)
                    onChanged()
                },
                onDragEnd = { draggingLabel = null },
                onDragCancel = { draggingLabel = null }
            )
        }
    ) {
        val cx = size.width / 2f
        val cy = size.height / 2f
        val r = minOf(size.width, size.height) / 2f * 0.9f

        for (frac in listOf(0.55f, 0.75f, 1.0f)) {
            drawCircle(
                color = Palette.Border,
                radius = r * frac,
                center = Offset(cx, cy),
                style = Stroke(width = 1.5f)
            )
        }
        drawCircle(color = Palette.Head, radius = r * 0.16f, center = Offset(cx, cy))
        drawContext.canvas.nativeCanvas.drawText(
            "YOU",
            cx, cy + 6f,
            android.graphics.Paint().apply {
                color = android.graphics.Color.rgb(15, 20, 32)
                textSize = 14f
                textAlign = android.graphics.Paint.Align.CENTER
            }
        )

        for ((label, angle) in config.positionsForFilter()) {
            val rad = Math.toRadians(angle - 90.0)
            val dist = config.getDistance(label)
            val vol = config.getVolume(label)
            val rr = radiusFor(dist, r)
            val x = cx + (rr * cos(rad)).toFloat()
            val y = cy + (rr * sin(rad)).toFloat()

            drawLine(
                color = Palette.Border,
                start = Offset(cx, cy),
                end = Offset(x, y),
                strokeWidth = 1.5f,
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(8f, 8f))
            )
            // Note: named `dotColor` (not `color`) so the Paint().apply { color = ... }
            // blocks below can't be confused with this outer val during name resolution.
            val dotColor = when {
                label.startsWith("F") -> Palette.Front
                label.startsWith("B") -> Palette.Rear
                else -> Palette.Side
            }
            val dotR = (9 + vol * 7).toFloat()
            drawCircle(color = dotColor, radius = dotR, center = Offset(x, y))
            drawCircle(color = Color.White, radius = dotR, center = Offset(x, y), style = Stroke(width = 2f))

            drawContext.canvas.nativeCanvas.drawText(
                label,
                x, y + 4f,
                android.graphics.Paint().apply {
                    color = android.graphics.Color.WHITE
                    textSize = 13f
                    isFakeBoldText = true
                    textAlign = android.graphics.Paint.Align.CENTER
                }
            )
            val zone = when { dist < 0.33 -> "near"; dist > 0.66 -> "far"; else -> "mid" }
            drawContext.canvas.nativeCanvas.drawText(
                "${(vol * 100).toInt()}%  $zone",
                x, y + dotR + 16f,
                android.graphics.Paint().apply {
                    color = android.graphics.Color.rgb(147, 160, 184)
                    textSize = 11f
                    textAlign = android.graphics.Paint.Align.CENTER
                }
            )
        }
    }
}

/** Maps a normalized distance (0..1) to a screen radius (near < far). */
private fun radiusFor(dist: Double, ringR: Float): Float {
    val d = dist.coerceIn(0.0, 1.0)
    val nearFrac = 0.38
    val farFrac = 1.06
    return ringR * (nearFrac + (farFrac - nearFrac) * d).toFloat()
}

/** Converts a canvas point to (angleDeg, distance). */
private fun posToAngleDist(x: Float, y: Float, cx: Float, cy: Float): Pair<Double, Double> {
    val dx = x - cx
    val dy = y - cy
    var angle = Math.toDegrees(atan2(dy.toDouble(), dx.toDouble())) + 90.0
    if (angle > 180.0) angle -= 360.0
    val raw = hypot(dx.toDouble(), dy.toDouble())
    val ringR = hypot(cx.toDouble(), cy.toDouble()) * 0.9
    val dist = if (ringR <= 0) 0.0 else (raw / ringR - 0.38) / (1.06 - 0.38)
    return angle to dist.coerceIn(0.0, 1.0)
}
