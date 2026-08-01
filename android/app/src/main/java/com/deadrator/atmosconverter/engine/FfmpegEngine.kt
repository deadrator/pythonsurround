package com.deadrator.atmosconverter.engine

import android.content.Context
import android.net.Uri
import com.arthenica.ffmpegkit.FFmpegKit
import com.arthenica.ffmpegkit.ReturnCode
import com.arthenica.ffmpegkit.Session
import com.deadrator.atmosconverter.dsp.CodecRegistry
import com.deadrator.atmosconverter.dsp.FilterPresets
import com.deadrator.atmosconverter.dsp.SpeakerConfig
import com.deadrator.atmosconverter.dsp.SpeakerFilterGenerator
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.coroutines.resume

/**
 * Wraps FFmpegKit (maintained fork, com.arthenica API drop-in) to run the
 * same filter chains as the desktop app.
 */
class FfmpegEngine(private val context: Context) {

    /** Build the `-af` filter chain for the selected method. */
    fun filterChainFor(method: String, speakerConfig: SpeakerConfig?, sofaPath: String?): String? {
        if (method in FilterPresets.PASSTHROUGH_METHODS) return null
        return when (method) {
            FilterPresets.Method.CUSTOM -> speakerConfig?.let { SpeakerFilterGenerator.generateBinauralFilter(it) }
            FilterPresets.Method.HRTF -> sofaPath?.let {
                // Android paths already use '/', so no Windows escaping needed
                "sofalizer=sofa='$it':radius=1.0"
            }
            else -> FilterPresets.filterFor(method)
        }
    }

    /**
     * Suspend until ffmpeg finishes.
     * `totalDurationSeconds` enables a real 0..100 progress mapping (from
     * FFmpegKit's statistics `time` in microseconds). The running session is
     * cancelled if the calling coroutine is cancelled.
     */
    suspend fun execute(
        args: List<String>,
        totalDurationSeconds: Double? = null,
        onProgress: ((Int) -> Unit)? = null
    ): Boolean = withContext(Dispatchers.IO) {
        suspendCancellableCoroutine { cont ->
            var session: Session? = null
            // FFmpegKit parses the command STRING and splits it on whitespace, so
            // any argument containing spaces (filter chains like
            // "anequalizer=c0 f=80 w=200 g=4 t=1", filenames with spaces) must be
            // single-quoted to survive as one token. Args that already embed
            // quotes (the HRTF sofalizer path) are left untouched.
            val command = args.joinToString(" ") { arg ->
                if (arg.any { it.isWhitespace() } && !arg.contains("'")) "'$arg'" else arg
            }
            FFmpegKit.executeAsync(
                command,
                { s ->
                    session = s
                    val ok = ReturnCode.isSuccess(s.returnCode)
                    if (!ok && s.failStackTrace != null) {
                        android.util.Log.e("AtmosConverter", "ffmpeg failed: ${s.failStackTrace}")
                    }
                    if (cont.isActive) cont.resume(ok)
                },
                null,
                if (onProgress != null && totalDurationSeconds != null && totalDurationSeconds > 0) {
                    { stats ->
                        val seconds = stats.time / 1_000_000.0
                        val pct = ((seconds / totalDurationSeconds) * 100).toInt().coerceIn(0, 100)
                        onProgress(pct)
                    }
                } else {
                    null
                }
            )
            cont.invokeOnCancellation { session?.cancel() }
        }
    }

    /**
     * Convert a local file to binaural/remuxed output. Mirrors the desktop
     * guard: the -af filter is only applied for multichannel input or upmix
     * methods (pan chains reference c2/c4/... that don't exist in stereo).
     */
    suspend fun convert(
        input: File,
        output: File,
        method: String,
        codec: String,
        container: String,
        bitrate: String?,
        speakerConfig: SpeakerConfig?,
        sofaPath: String?,
        onProgress: ((Int) -> Unit)? = null
    ): Boolean = withContext(Dispatchers.IO) {
        val meta = AudioProbe.probe(input)
        val channels = meta?.channels ?: 0
        val duration = meta?.durationSeconds

        if (method in FilterPresets.PASSTHROUGH_METHODS) {
            // -vn: audio-only output. Without it, M4A/MOV inputs with embedded
            // cover-art video streams get mapped and re-encoded (defaulting to
            // h264_mediacodec, which fails to configure on many devices),
            // failing the whole conversion with a 0-byte output.
            val args = listOf("-i", input.absolutePath, "-vn", "-c:a", "copy", "-map_metadata", "0") +
                CodecRegistry.outputArgs(container) + listOf("-y", output.absolutePath)
            return@withContext execute(args, duration, onProgress)
        }

        val encodeArgs = CodecRegistry.encodeArgs(codec, bitrate ?: codecDefault(codec), 48000)
        val outArgs = CodecRegistry.outputArgs(container)
        val chain = filterChainFor(method, speakerConfig, sofaPath) ?: FilterPresets.ENHANCED
        val applyFilter = channels > 2 || method in FilterPresets.UPMIX_METHODS

        val args = if (applyFilter) {
            // -vn drops cover-art/video streams (see passthrough comment above).
            listOf("-i", input.absolutePath, "-vn", "-af", chain) + encodeArgs + outArgs +
                listOf("-y", output.absolutePath)
        } else {
            listOf("-i", input.absolutePath, "-vn") + encodeArgs + outArgs +
                listOf("-y", output.absolutePath)
        }
        execute(args, duration, onProgress)
    }

    private fun codecDefault(codec: String): String =
        CodecRegistry.getCodec(codec)?.defaultBitrate ?: "256k"

    /** Output filename for a conversion. */
    fun outputName(base: String, container: String): String {
        val ext = CodecRegistry.getContainer(container)?.extension ?: ".m4a"
        val stamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
        return "${base}_binaural_$stamp$ext"
    }

    companion object {
        /**
         * Copy a content:// document into the app cache so FFmpegKit (which
         * needs a real file path) can read it. Returns the cached File.
         */
        fun copyToCache(context: Context, uri: Uri, fallbackName: String): File {
            val name = uri.lastPathSegment?.substringAfterLast('/')?.ifBlank { null }
                ?: fallbackName
            val cache = File(context.cacheDir, "input_${System.currentTimeMillis()}_$name")
            context.contentResolver.openInputStream(uri)?.use { input ->
                cache.outputStream().use { output -> input.copyTo(output) }
            } ?: throw IllegalStateException("Cannot open $uri")
            return cache
        }

        /** Write a converted file into the app's Music dir so it can be shared. */
        fun saveOutput(context: Context, src: File, name: String): File {
            val dir = File(context.getExternalFilesDir(null), "Music").apply { mkdirs() }
            val dest = File(dir, name)
            src.copyTo(dest, overwrite = true)
            return dest
        }
    }
}
