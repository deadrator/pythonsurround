package com.deadrator.atmosconverter.ui

import android.Manifest
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import android.widget.Toast
import androidx.core.content.ContextCompat
import com.deadrator.atmosconverter.engine.FfmpegEngine
import com.deadrator.atmosconverter.ui.theme.Palette
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.coroutines.coroutineContext
import java.io.File
import kotlin.math.abs
import kotlin.math.max

/**
 * Channel visualizer: play any file and watch per-channel levels (5.1 / 7.1 /
 * Atmos / any layout FFmpeg can decode), or capture live mic levels.
 * Port of the desktop Channel Visualizer tab.
 */
@Composable
fun VisualizerScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val engine = remember { FfmpegEngine(context) }

    var channels by remember { mutableStateOf(2) }
    var labels by remember { mutableStateOf(listOf("L", "R")) }
    var levels by remember { mutableStateOf(List(8) { 0f }) }
    var peaks by remember { mutableStateOf(List(64) { 0f }) }
    var fileName by remember { mutableStateOf<String?>(null) }
    var micOn by remember { mutableStateOf(false) }
    var micLevel by remember { mutableStateOf(0f) }
    val micJob = remember { mutableStateOf<kotlinx.coroutines.Job?>(null) }

    val micLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        if (it) micOn = true
    }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) {
            scope.launch {
                try {
                    fileName = uri.lastPathSegment?.substringAfterLast('/')
                    val f = FfmpegEngine.copyToCache(context, uri, "viz")
                    val meta = com.deadrator.atmosconverter.engine.AudioProbe.probe(f)
                    val ch = meta?.channels?.coerceAtLeast(1) ?: 2
                    channels = ch
                    labels = standardLabels(ch)
                    // Decode the first 60s to mono/float for levels + waveform
                    // buckets. -t caps the decode: a full album-length 5.1 decode
                    // (~1.15 MB/s per channel of f32le) would OOM readBytes()
                    // and crash - which is what happened with AC3 files here.
                    withContext(Dispatchers.IO) {
                        val out = File(context.cacheDir, "viz_${System.currentTimeMillis()}.f32le")
                        val ok = engine.execute(
                            listOf("-i", f.absolutePath, "-t", "60", "-f", "f32le", "-ac", "1", "-y", out.absolutePath)
                        ) {}
                        if (ok) {
                            val bytes = out.readBytes()
                            val floats = FloatArray(bytes.size / 4)
                            java.nio.ByteBuffer.wrap(bytes).asFloatBuffer().get(floats)
                            out.delete()
                            peaks = bucketPeaks(floats, 64)
                        }
                    }
                    // per-channel RMS (decode multichannel float, capped)
                    withContext(Dispatchers.IO) {
                        val out2 = File(context.cacheDir, "vizch_${System.currentTimeMillis()}.f32le")
                        val ok2 = engine.execute(
                            listOf("-i", f.absolutePath, "-t", "60", "-f", "f32le", "-ac", ch.toString(), "-y", out2.absolutePath)
                        ) {}
                        if (ok2) {
                            val bytes = out2.readBytes()
                            val floats = FloatArray(bytes.size / 4)
                            java.nio.ByteBuffer.wrap(bytes).asFloatBuffer().get(floats)
                            out2.delete()
                            levels = channelRms(floats, ch)
                        }
                    }
                } catch (e: Exception) {
                    // copyToCache can throw, probe can fail; never crash the app.
                    Toast.makeText(context, "✗ Cannot analyze: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    // Mic capture while on (runs until cancelled) - audio reads on IO thread
    LaunchedEffect(micOn) {
        if (micOn) {
            micJob.value = scope.launch(Dispatchers.IO) {
                startMic { lvl -> micLevel = lvl }
            }
        } else {
            micJob.value?.cancel()
            micJob.value = null
            micLevel = 0f
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("📊 Channel Visualizer", style = MaterialTheme.typography.headlineSmall)
        Text(
            "Play any file and watch 5.1 / 7.1 / Atmos per-channel levels",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { picker.launch(arrayOf("audio/*", "video/*", "*/*")) }) {
                Text("📂 Load File")
            }
            OutlinedButton(onClick = {
                if (micOn) {
                    micOn = false
                    micJob.value?.cancel()
                    micJob.value = null
                } else {
                    if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO)
                        == PackageManager.PERMISSION_GRANTED
                    ) {
                        micOn = true
                    } else {
                        micLauncher.launch(Manifest.permission.RECORD_AUDIO)
                    }
                }
            }) {
                Icon(if (micOn) Icons.Filled.Mic else Icons.Filled.MicOff, contentDescription = null)
                Text(if (micOn) "Stop Mic" else "Live Mic")
            }
        }

        fileName?.let {
            Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }

        // Channel bars
        Card {
            Column(
                Modifier
                    .fillMaxWidth()
                    .padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text("Channel Levels (${channels}ch)", style = MaterialTheme.typography.titleSmall)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    repeat(channels.coerceAtMost(8)) { i ->
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Canvas(modifier = Modifier.width(20.dp).height(110.dp)) {
                                drawRoundRect(
                                    color = Palette.Surface3,
                                    size = androidx.compose.ui.geometry.Size(size.width, size.height)
                                )
                                val fill = size.height * levels.getOrElse(i) { 0f }.coerceIn(0f, 1f)
                                drawRoundRect(
                                    color = channelColor(i, channels),
                                    size = androidx.compose.ui.geometry.Size(size.width, fill),
                                    topLeft = Offset(0f, size.height - fill)
                                )
                            }
                            Text(
                                labels.getOrElse(i) { "?" },
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                    if (micOn) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Canvas(modifier = Modifier.width(20.dp).height(110.dp)) {
                                drawRoundRect(
                                    color = Palette.Surface3,
                                    size = androidx.compose.ui.geometry.Size(size.width, size.height)
                                )
                                val fill = size.height * micLevel.coerceIn(0f, 1f)
                                drawRoundRect(
                                    color = Palette.Side,
                                    size = androidx.compose.ui.geometry.Size(size.width, fill),
                                    topLeft = Offset(0f, size.height - fill)
                                )
                            }
                            Text("MIC", style = MaterialTheme.typography.labelSmall, color = Palette.Side)
                        }
                    }
                }
            }
        }

        // Waveform
        Card {
            Column(Modifier.padding(12.dp)) {
                Text("Waveform", style = MaterialTheme.typography.titleSmall)
                Canvas(modifier = Modifier.fillMaxWidth().height(100.dp).padding(top = 6.dp)) {
                    val step = size.width / max(1, peaks.size)
                    peaks.forEachIndexed { i, p ->
                        val x = i * step
                        drawLine(
                            color = Palette.Accent,
                            start = Offset(x, size.height / 2 - size.height / 2 * p),
                            end = Offset(x, size.height / 2 + size.height / 2 * p),
                            strokeWidth = 2f,
                            cap = StrokeCap.Round
                        )
                    }
                }
            }
        }
    }
}

private fun standardLabels(ch: Int): List<String> {
    val labels = when (ch) {
        1 -> listOf("M")
        2 -> listOf("L", "R")
        6 -> listOf("FL", "FR", "FC", "LFE", "BL", "BR")
        8 -> listOf("FL", "FR", "FC", "LFE", "SL", "SR", "BL", "BR")
        else -> (0 until ch).map { "C$it" }
    }
    return labels
}

private fun channelColor(i: Int, total: Int) = when {
    i < 2 -> Palette.Front
    i >= total - 2 && total > 4 -> Palette.Rear
    else -> Palette.Side
}

private fun bucketPeaks(floats: FloatArray, buckets: Int): List<Float> {
    if (floats.isEmpty()) return List(buckets) { 0f }
    val per = max(1, floats.size / buckets)
    return (0 until buckets).map { b ->
        val start = b * per
        val end = minOf(start + per, floats.size)
        if (start >= end) 0f else (start until end).maxOf { abs(floats[it]) }
    }
}

private fun channelRms(floats: FloatArray, channels: Int): List<Float> =
    List(channels) { ch ->
        var sum = 0.0
        var count = 0
        var i = ch
        while (i < floats.size) {
            sum += floats[i] * floats[i]
            count++
            i += channels
        }
        if (count == 0) 0f else (Math.sqrt(sum / count).toFloat() * 4f).coerceIn(0f, 1f)
    }

/** Live microphone level capture (mono 16-bit). Runs until the calling coroutine is cancelled. */
private suspend fun startMic(onLevel: (Float) -> Unit) {
    val sampleRate = 44100
    val bufSize = AudioRecord.getMinBufferSize(
        sampleRate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT
    )
    val recorder = AudioRecord(
        MediaRecorder.AudioSource.MIC, sampleRate,
        AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
        bufSize.coerceAtLeast(sampleRate)
    )
    if (recorder.state != AudioRecord.STATE_INITIALIZED) return
    recorder.startRecording()
    val buf = ShortArray(sampleRate / 10)
    try {
        while (coroutineContext.isActive) {
            val read = recorder.read(buf, 0, buf.size)
            if (read > 0) {
                var peak = 0
                for (i in 0 until read) peak = max(peak, abs(buf[i].toInt()))
                onLevel((peak / 32768f).coerceIn(0f, 1f))
            }
            kotlinx.coroutines.delay(90)
        }
    } finally {
        recorder.stop()
        recorder.release()
    }
}
