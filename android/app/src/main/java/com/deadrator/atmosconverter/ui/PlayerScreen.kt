package com.deadrator.atmosconverter.ui

import android.content.Context
import android.media.MediaPlayer
import android.net.Uri
import android.util.Log
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.SkipNext
import androidx.compose.material.icons.filled.SkipPrevious
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.deadrator.atmosconverter.engine.AudioMeta
import com.deadrator.atmosconverter.engine.AudioProbe
import com.deadrator.atmosconverter.engine.FfmpegEngine
import com.deadrator.atmosconverter.ui.theme.Palette
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import kotlin.math.max

/**
 * Real media player with a playlist, per-channel VU meters, a waveform and
 * optional conversion preview (plays the file through the current filter
 * chain via FFmpeg, just like the desktop player's "Preview conversion").
 */
@Composable
fun PlayerScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    val playlist = remember { mutableStateListOf<PlaylistEntry>() }
    var currentIndex by rememberSaveable { mutableStateOf(-1) }
    var playing by remember { mutableStateOf(false) }
    var previewOn by remember { mutableStateOf(false) }
    var positionMs by remember { mutableStateOf(0L) }
    var durationMs by remember { mutableStateOf(0L) }
    var meta by remember { mutableStateOf<AudioMeta?>(null) }
    var previewFile by remember { mutableStateOf<File?>(null) }

    val player = remember { MediaPlayer() }
    DisposableEffect(Unit) {
        onDispose {
            player.release()
            previewFile?.delete()
        }
    }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        if (uris.isNotEmpty()) {
            scope.launch {
                val newEntries = uris.map { PlaylistEntry(it, it.lastPathSegment?.substringAfterLast('/') ?: "track") }
                playlist.addAll(newEntries)
                if (currentIndex == -1) {
                    currentIndex = 0
                    val res = loadTrack(context, player, playlist, 0, previewOn, previewFile) { _, _, _ -> }
                    previewFile = res.file
                    if (res.loaded) {
                        player.start()
                        playing = true
                    }
                    // metadata shown via update loop below
                    meta = AudioProbe.probe(FfmpegEngine.copyToCache(context, uris[0], "probe"))
                }
            }
        }
    }

    // Poll playhead while playing
    LaunchedEffect(playing) {
        while (playing) {
            if (currentIndex in playlist.indices) {
                positionMs = player.currentPosition.toLong()
                durationMs = player.duration.toLong()
            }
            delay(200)
        }
    }

    fun playIndex(i: Int) {
        if (i !in playlist.indices) return
        currentIndex = i
        scope.launch {
            meta = AudioProbe.probe(FfmpegEngine.copyToCache(context, playlist[i].uri, "probe"))
            val res = loadTrack(context, player, playlist, i, previewOn, previewFile) { _, _, _ -> }
            previewFile = res.file
            if (res.loaded) {
                player.start()
                playing = true
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("🎵 AC3 Music Player", style = MaterialTheme.typography.headlineSmall)

        // Playlist
        Card(modifier = Modifier.height(160.dp)) {
            LazyColumn(
                modifier = Modifier.padding(vertical = 4.dp),
                contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp)
            ) {
                items(playlist) { entry ->
                    val idx = playlist.indexOf(entry)
                    TextButton(onClick = { playIndex(idx) }) {
                        Text(
                            (if (idx == currentIndex) "▶ " else "") + entry.name,
                            maxLines = 1,
                            style = if (idx == currentIndex) MaterialTheme.typography.bodyLarge
                                    else MaterialTheme.typography.bodyMedium,
                            color = if (idx == currentIndex) Palette.Accent
                                    else MaterialTheme.colorScheme.onSurface
                        )
                    }
                }
            }
        }

        Button(onClick = { picker.launch(arrayOf("audio/*", "video/*", "*/*")) }) {
            Text("📂 Add Files")
        }

        // Track info
        Card {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(
                    playlist.getOrNull(currentIndex)?.name ?: "No track loaded",
                    style = MaterialTheme.typography.titleMedium
                )
                meta?.let {
                    Text(
                        "${it.channels}ch ${it.channelLayout ?: "?"} • " +
                            "${it.sampleRate / 1000}.${(it.sampleRate % 1000).toString().padStart(3, '0')} kHz • " +
                            (it.codecName ?: "?") + (it.codecLongName?.let { " ($it)" } ?: "") +
                            (it.bitRateKbps?.let { " • ${it} kbps" } ?: ""),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }

        // Transport
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = { if (currentIndex > 0) playIndex(currentIndex - 1) }) {
                Icon(Icons.Filled.SkipPrevious, contentDescription = "Prev")
            }
            IconButton(onClick = {
                if (playing) { player.pause(); playing = false } else { player.start(); playing = true }
            }, enabled = currentIndex in playlist.indices) {
                Icon(
                    if (playing) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                    contentDescription = if (playing) "Pause" else "Play",
                    modifier = Modifier.size(44.dp)
                )
            }
            IconButton(onClick = { if (currentIndex < playlist.size - 1) playIndex(currentIndex + 1) }) {
                Icon(Icons.Filled.SkipNext, contentDescription = "Next")
            }
        }

        // Seek
        Slider(
            value = positionMs.toFloat(),
            onValueChange = {
                positionMs = it.toLong()
                player.seekTo(it.toInt())
            },
            valueRange = 0f..max(1f, durationMs.toFloat())
        )
        Text(
            "${fmtTime(positionMs)} / ${fmtTime(durationMs)}",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        // Preview conversion toggle
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Switch(checked = previewOn, onCheckedChange = { v ->
                previewOn = v
                if (currentIndex in playlist.indices) {
                    scope.launch {
                        val res = loadTrack(context, player, playlist, currentIndex, v, previewFile) { _, _, _ -> }
                        previewFile = res.file
                        if (res.loaded) {
                            player.start()
                            playing = true
                        }
                    }
                }
            })
            Text("🎧 Preview conversion", style = MaterialTheme.typography.bodyMedium)
        }

        // VU meters (per channel)
        meta?.let { m ->
            Card {
                Column(
                    Modifier
                        .fillMaxWidth()
                        .padding(12.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    Text("Channel Levels (VU)", style = MaterialTheme.typography.titleSmall)
                    // levels are computed at load time from a decoded pass (see loadTrack)
                    var levels by remember { mutableStateOf<List<Float>>(emptyList()) }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        repeat(m.channels.coerceAtMost(8)) { ch ->
                            VuMeter(
                                level = levels.getOrElse(ch) { 0f },
                                color = channelColor(ch, m.channels),
                                modifier = Modifier.height(80.dp).width(18.dp)
                            )
                        }
                    }
                    // decode a block of PCM to drive meters (decoded once per track, not per play/pause)
                    LaunchedEffect(playlist.getOrNull(currentIndex)?.uri, currentIndex) {
                        val entry = playlist.getOrNull(currentIndex) ?: return@LaunchedEffect
                        val decoded = FfmpegEngine.copyToCache(context, entry.uri, "decode")
                        withContext(Dispatchers.IO) {
                            levels = computeChannelLevels(context, decoded, m.channels)
                        }
                    }
                }
            }
        }

        // Waveform
        meta?.let { m ->
            Card {
                Column(Modifier.padding(12.dp)) {
                    Text("Waveform", style = MaterialTheme.typography.titleSmall)
                    var peaks by remember { mutableStateOf<List<Float>>(emptyList()) }
                    LaunchedEffect(playlist.getOrNull(currentIndex)?.uri, currentIndex) {
                        val entry = playlist.getOrNull(currentIndex) ?: return@LaunchedEffect
                        val decoded = FfmpegEngine.copyToCache(context, entry.uri, "waveform")
                        withContext(Dispatchers.IO) {
                            peaks = computeWaveform(context, decoded, 64)
                        }
                    }
                    Canvas(modifier = Modifier.fillMaxWidth().height(90.dp)) {
                        val w = size.width
                        val h = size.height
                        val step = w / max(1, peaks.size)
                        peaks.forEachIndexed { i, p ->
                            val x = i * step
                            drawLine(
                                color = Palette.Accent,
                                start = Offset(x, h / 2 - h / 2 * p),
                                end = Offset(x, h / 2 + h / 2 * p),
                                strokeWidth = 2f,
                                cap = StrokeCap.Round
                            )
                        }
                    }
                }
            }
        }
    }
}

private data class PlaylistEntry(val uri: Uri, val name: String)

/** Result of loadTrack: the fallback file to keep for cleanup (or null when
 *  playing the original) and whether a track is actually loaded/playable. */
private data class LoadResult(val file: File?, val loaded: Boolean)

private fun channelColor(ch: Int, total: Int): Color = when {
    ch == 0 || (total > 2 && ch == 1) -> Palette.Front
    total <= 2 -> Palette.Front
    ch >= total - 2 -> Palette.Rear
    else -> Palette.Side
}

/** Loads a track into the player. If preview is on, routes through FFmpeg first.
 *  If the platform MediaPlayer can't decode the file (AC3/E-AC3/DTS/TrueHD/AC-4
 *  are not supported by stock Android - `prepare()` throws IOException), it
 *  transcodes the track to AAC via FFmpeg and plays that instead. Never throws:
 *  failures surface as a Toast and LoadResult.loaded=false. */
private suspend fun loadTrack(
    context: Context,
    player: MediaPlayer,
    playlist: List<PlaylistEntry>,
    index: Int,
    previewOn: Boolean,
    previewFile: File?,
    onMeta: (Long, Long, AudioMeta?) -> Unit
): LoadResult {
    val entry = playlist[index]

    if (previewOn) {
        // decode to a temp WAV through the enhanced chain (stand-in for full preview)
        try {
            val cached = FfmpegEngine.copyToCache(context, entry.uri, entry.name)
            val out = File(context.cacheDir, "preview_${System.currentTimeMillis()}.wav")
            val ok = FfmpegEngine(context).convert(
                cached, out,
                com.deadrator.atmosconverter.dsp.FilterPresets.Method.ENHANCED,
                "pcm_s16le", "wav", null, null, null
            ) {}
            if (ok) {
                player.reset()
                player.setDataSource(out.absolutePath)
                player.prepare()
                previewFile?.delete()
                return LoadResult(out, true)
            }
        } catch (e: Exception) {
            Toast.makeText(context, "Preview failed: ${e.message}", Toast.LENGTH_SHORT).show()
        }
    }

    // Plain playback: try the platform decoder first (AAC/MP3/FLAC/Opus/WAV...).
    try {
        player.reset()
        player.setDataSource(context, entry.uri)
        player.prepare()
        previewFile?.delete() // drop any stale decoded fallback file from a previous track
        return LoadResult(null, true)
    } catch (e: Exception) {
        Log.w("AtmosConverter", "MediaPlayer cannot decode ${entry.name}: ${e.message}; falling back to FFmpeg")
    }

    // FFmpeg fallback: transcode to AAC (playable by any device) and play that.
    Toast.makeText(context, "Decoding ${entry.name} via FFmpeg…", Toast.LENGTH_SHORT).show()
    try {
        val cached = FfmpegEngine.copyToCache(context, entry.uri, entry.name)
        val out = File(context.cacheDir, "decoded_${System.currentTimeMillis()}.m4a")
        val ok = FfmpegEngine(context).execute(
            listOf(
                "-i", cached.absolutePath,
                "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
                "-f", "ipod", "-y", out.absolutePath
            )
        ) {}
        if (ok) {
            player.reset()
            player.setDataSource(out.absolutePath)
            player.prepare()
            previewFile?.delete()
            return LoadResult(out, true)
        }
    } catch (e: Exception) {
        Log.e("AtmosConverter", "FFmpeg decode fallback failed: ${e.message}")
    }
    Toast.makeText(context, "Cannot play ${entry.name}: no decoder available", Toast.LENGTH_LONG).show()
    return LoadResult(null, false)
}

private fun fmtTime(ms: Long): String {
    val s = ms / 1000
    return "${s / 60}:${(s % 60).toString().padStart(2, '0')}"
}

@Composable
private fun VuMeter(level: Float, color: Color, modifier: Modifier = Modifier) {
    Canvas(modifier = modifier) {
        val h = size.height
        val fill = (h * level.coerceIn(0f, 1f))
        drawRoundRect(
            color = Palette.Surface3,
            size = androidx.compose.ui.geometry.Size(size.width, h)
        )
        drawRoundRect(
            color = color,
            size = androidx.compose.ui.geometry.Size(size.width, fill),
            topLeft = Offset(0f, h - fill)
        )
    }
}

/** Quick PCM level estimation using ffmpeg (decode to mono raw, measure RMS). */
private suspend fun computeChannelLevels(context: Context, file: File, channels: Int): List<Float> =
    withContext(Dispatchers.IO) {
        val out = File(context.cacheDir, "levels_${System.currentTimeMillis()}.f32le")
        try {
            FfmpegEngine(context).execute(
                // -t 60 caps the decoded sample (a full album-length 5.1 decode
                // would OOM readBytes(): ~1.15 MB/s per channel).
                listOf("-i", file.absolutePath, "-t", "60", "-f", "f32le", "-ac", channels.toString(), "-y", out.absolutePath)
            ) {}
            val bytes = out.readBytes()
            val floats = FloatArray(bytes.size / 4)
            java.nio.ByteBuffer.wrap(bytes).asFloatBuffer().get(floats)
            out.delete()
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
        } catch (e: Exception) {
            emptyList()
        }
    }

/** Downsampled peak waveform (mixdown to mono peaks over N buckets). */
private suspend fun computeWaveform(context: Context, file: File, buckets: Int): List<Float> =
    withContext(Dispatchers.IO) {
        val out = File(context.cacheDir, "wave_${System.currentTimeMillis()}.f32le")
        try {
            FfmpegEngine(context).execute(
                listOf("-i", file.absolutePath, "-t", "60", "-f", "f32le", "-ac", "1", "-y", out.absolutePath)
            ) {}
            val bytes = out.readBytes()
            val floats = FloatArray(bytes.size / 4)
            java.nio.ByteBuffer.wrap(bytes).asFloatBuffer().get(floats)
            out.delete()
            if (floats.isEmpty()) return@withContext emptyList()
            val perBucket = max(1, floats.size / buckets)
            (0 until buckets).map { b ->
                val start = b * perBucket
                val end = minOf(start + perBucket, floats.size)
                if (start >= end) 0f
                else (start until end).maxOf { kotlin.math.abs(floats[it]) }
            }
        } catch (e: Exception) {
            emptyList()
        }
    }
