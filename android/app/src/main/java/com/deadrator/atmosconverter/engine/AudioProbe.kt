package com.deadrator.atmosconverter.engine

import com.arthenica.ffmpegkit.FFprobeKit
import com.arthenica.ffmpegkit.MediaInformation
import com.arthenica.ffmpegkit.StreamInformation
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.io.File
import kotlin.coroutines.resume

/** Probed metadata for one audio stream. */
data class AudioMeta(
    val codecName: String?,
    val codecLongName: String?,
    val profile: String?,
    val channels: Int,
    val channelLayout: String?,
    val sampleRate: Int,
    val durationSeconds: Double,
    val bitRateKbps: Int?
)

/**
 * Wraps FFprobeKit to fetch the same info the desktop app probes
 * (channel count, codec, sample rate, duration, bitrate).
 */
object AudioProbe {

    suspend fun probe(file: File): AudioMeta? = withContext(Dispatchers.IO) {
        suspendCancellableCoroutine { cont ->
            FFprobeKit.getMediaInformation(file.absolutePath) { info ->
                val meta = extract(file, info)
                if (cont.isActive) cont.resume(meta)
            }
        }
    }

    private fun extract(file: File, info: MediaInformation?): AudioMeta? {
        if (info == null) return null
        val streams = info.streams?.filter { it.isAudio() } ?: emptyList()
        val stream = streams.firstOrNull() ?: return null
        return AudioMeta(
            codecName = stream.codecName,
            codecLongName = stream.codecLongName,
            profile = stream.profile,
            channels = stream.channels ?: 0,
            channelLayout = stream.channelLayout,
            sampleRate = parseSampleRate(stream),
            durationSeconds = parseDuration(info, stream),
            bitRateKbps = parseBitrate(stream)
        )
    }

    private fun StreamInformation.isAudio(): Boolean =
        codecType == "audio"

    private fun parseSampleRate(s: StreamInformation): Int =
        s.sampleRate?.toIntOrNull()
            ?: s.tags?.get("sample_rate")?.toIntOrNull()
            ?: 48000

    /** MediaInformation.getDuration() is a String (seconds); fall back to the
     *  stream's tags (e.g. "DURATION-eng") or 0. */
    private fun parseDuration(info: MediaInformation, s: StreamInformation): Double {
        info.duration?.toDoubleOrNull()?.let { return it }
        (s.tags?.values?.firstOrNull { it.startsWith("00:") })
            ?.let { return ffmpegTimeToSeconds(it) }
        return 0.0
    }

    private fun ffmpegTimeToSeconds(ts: String): Double {
        val parts = ts.split(":")
        if (parts.size != 3) return 0.0
        val h = parts[0].toDoubleOrNull() ?: return 0.0
        val m = parts[1].toDoubleOrNull() ?: return 0.0
        val s = parts[2].toDoubleOrNull() ?: return 0.0
        return h * 3600 + m * 60 + s
    }

    private fun parseBitrate(s: StreamInformation): Int? =
        s.bitRate?.toIntOrNull()?.let { it / 1000 }
            ?: s.tags?.get("bit_rate")?.toIntOrNull()?.let { it / 1000 }
}
