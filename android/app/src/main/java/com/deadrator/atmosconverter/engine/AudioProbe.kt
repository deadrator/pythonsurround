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
 * Wraps FFprobeKit (the maintained `dev.ffmpegkit-maintained` fork) to fetch
 * the same info the desktop app probes (channel count, codec, sample rate,
 * duration, bitrate).
 *
 * NOTE: the maintained fork's API differs from the retired `com.arthenica`
 * artifact, which this file was originally written against:
 *  - stream getters are getCodec()/getCodecLong()/getType()/getBitrate()
 *    (there is no getCodecName()/getCodecLongName()/getCodecType()/getBitRate());
 *  - tags are an org.json.JSONObject, not a Map;
 *  - arbitrary stream fields are read via getStringProperty()/getNumberProperty();
 *  - there is no getMediaInformation(path, callback) overload - use the
 *    async variant, whose callback receives a MediaInformationSession.
 */
object AudioProbe {

    suspend fun probe(file: File): AudioMeta? = withContext(Dispatchers.IO) {
        suspendCancellableCoroutine { cont ->
            // getMediaInformationAsync returns the session immediately; the
            // callback fires when the probe finishes. Cancel the probe if the
            // calling coroutine is cancelled (same pattern as FfmpegEngine).
            val probeSession = FFprobeKit.getMediaInformationAsync(file.absolutePath) { session ->
                val meta = extract(session?.mediaInformation)
                if (cont.isActive) cont.resume(meta)
            }
            cont.invokeOnCancellation { probeSession.cancel() }
        }
    }

    private fun extract(info: MediaInformation?): AudioMeta? {
        if (info == null) return null
        val stream = info.streams
            ?.filterIsInstance<StreamInformation>()
            ?.firstOrNull { it.type == "audio" }
            ?: return null
        return AudioMeta(
            codecName = stream.codec,
            codecLongName = stream.codecLong,
            profile = stream.getStringProperty("profile"),
            channels = stream.getNumberProperty("channels")?.toInt() ?: 0,
            channelLayout = stream.channelLayout,
            sampleRate = parseSampleRate(stream),
            durationSeconds = parseDuration(info, stream),
            bitRateKbps = parseBitrate(stream)
        )
    }

    private fun parseSampleRate(s: StreamInformation): Int =
        s.sampleRate?.toIntOrNull()
            ?: s.getStringProperty("sample_rate")?.toIntOrNull()
            ?: 48000

    /** MediaInformation.getDuration() is a String (seconds); fall back to the
     *  stream's DURATION-* tags (e.g. "DURATION-eng": "00:04:12.34") or 0. */
    private fun parseDuration(info: MediaInformation, s: StreamInformation): Double {
        info.duration?.toDoubleOrNull()?.let { return it }
        val tags = info.tags ?: s.tags
        if (tags != null) {
            val keys = tags.keys()
            while (keys.hasNext()) {
                val key = keys.next()
                if (key.startsWith("DURATION")) {
                    val secs = ffmpegTimeToSeconds(tags.optString(key))
                    if (secs > 0.0) return secs
                }
            }
        }
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
        s.bitrate?.toIntOrNull()?.let { it / 1000 }
            ?: s.getStringProperty("bit_rate")?.toIntOrNull()?.let { it / 1000 }
}
