package com.deadrator.atmosconverter.dsp

/**
 * Port of audio_codecs.py - the codec/container/preset registry.
 *
 * Data mirrors CODECS / CONTAINERS / PRESETS in the Python module.
 */
object CodecRegistry {

    data class AudioCodec(
        val name: String,
        val extension: String,
        val ffmpegName: String,
        val supportsBitrate: Boolean = true,
        val defaultBitrate: String = "256k",
        val description: String = ""
    )

    data class Container(
        val name: String,
        val extension: String,
        val ffmpegFormat: String,
        val supportedCodecs: Set<String>,
        val description: String = ""
    )

    val CODECS: Map<String, AudioCodec> = mapOf(
        "aac" to AudioCodec("AAC", ".m4a", "aac", defaultBitrate = "256k",
            description = "Advanced Audio Coding - Universal compatibility"),
        "mp3" to AudioCodec("MP3", ".mp3", "libmp3lame", defaultBitrate = "320k",
            description = "MPEG Audio Layer III - Widely supported"),
        "flac" to AudioCodec("FLAC", ".flac", "flac", supportsBitrate = false,
            description = "Free Lossless Audio Codec - Lossless quality"),
        "opus" to AudioCodec("Opus", ".opus", "libopus", defaultBitrate = "192k",
            description = "Opus - Best quality at low bitrates"),
        "vorbis" to AudioCodec("Vorbis", ".ogg", "libvorbis", defaultBitrate = "192k",
            description = "Ogg Vorbis - Open source, good quality"),
        "ac3" to AudioCodec("AC3", ".ac3", "ac3", defaultBitrate = "384k",
            description = "Dolby Digital - Surround sound"),
        "eac3" to AudioCodec("E-AC-3", ".eac3", "eac3", defaultBitrate = "256k",
            description = "Dolby Digital Plus - Enhanced surround"),
        "pcm_s16le" to AudioCodec("PCM 16-bit", ".wav", "pcm_s16le", supportsBitrate = false,
            description = "Uncompressed 16-bit audio"),
        "pcm_s24le" to AudioCodec("PCM 24-bit", ".wav", "pcm_s24le", supportsBitrate = false,
            description = "Uncompressed 24-bit audio"),
        "ac4" to AudioCodec("AC-4", ".ac4", "ac4", defaultBitrate = "192k",
            description = "Dolby AC-4 - Next-gen Atmos/broadcast (decode + remux; encode only if your FFmpeg build has it)"),
        "truehd" to AudioCodec("TrueHD", ".thd", "truehd", supportsBitrate = false,
            description = "Dolby TrueHD - Lossless Atmos surround"),
        "dts" to AudioCodec("DTS", ".dts", "dca", defaultBitrate = "768k",
            description = "DTS Coherent Acoustics - Surround sound"),
        "alac" to AudioCodec("ALAC", ".m4a", "alac", supportsBitrate = false,
            description = "Apple Lossless Audio Codec")
    )

    val CONTAINERS: Map<String, Container> = mapOf(
        "m4a" to Container("M4A", ".m4a", "ipod", setOf("aac", "alac"),
            "MPEG-4 Audio - iOS/Android compatible"),
        "mp4" to Container("MP4", ".mp4", "mp4", setOf("aac", "mp3", "ac3", "eac3", "ac4"),
            "MPEG-4 - Universal video/audio"),
        "mkv" to Container("MKV", ".mkv", "matroska",
            setOf("aac", "mp3", "flac", "opus", "vorbis", "ac3", "eac3", "truehd", "dts", "alac", "ac4"),
            "Matroska - Maximum codec support"),
        "mka" to Container("MKA", ".mka", "matroska",
            setOf("aac", "mp3", "flac", "opus", "vorbis", "ac3", "eac3", "truehd", "dts", "alac", "ac4"),
            "Matroska Audio - Max codec support, audio only"),
        "ac4" to Container("AC-4", ".ac4", "ac4", setOf("ac4"),
            "Dolby AC-4 raw stream - Atmos / broadcast"),
        "dts" to Container("DTS", ".dts", "dts", setOf("dts"),
            "Raw DTS stream"),
        "ogg" to Container("OGG", ".ogg", "ogg", setOf("opus", "vorbis"),
            "Ogg - Open source container"),
        "webm" to Container("WebM", ".webm", "webm", setOf("opus", "vorbis"),
            "WebM - Web optimized"),
        "flac" to Container("FLAC", ".flac", "flac", setOf("flac"),
            "FLAC container - Lossless"),
        "wav" to Container("WAV", ".wav", "wav", setOf("pcm_s16le", "pcm_s24le"),
            "WAV - Uncompressed, maximum compatibility"),
        "avi" to Container("AVI", ".avi", "avi", setOf("mp3", "pcm_s16le"),
            "AVI - Legacy compatibility")
    )

    /** Preset -> (codec, container, bitrate|null). Port of PRESETS in audio_codecs.py */
    val PRESETS: Map<String, Triple<String, String, String?>> = mapOf(
        "Android Best" to Triple("aac", "m4a", "256k"),
        "Android Compact" to Triple("aac", "m4a", "128k"),
        "Universal" to Triple("aac", "mp4", "192k"),
        "Lossless" to Triple("flac", "flac", null),
        "Web Optimized" to Triple("opus", "webm", "128k"),
        "Maximum Quality" to Triple("flac", "mkv", null),
        "Podcast" to Triple("mp3", "mp3", "192k"),
        "AC-4 Atmos" to Triple("ac4", "mp4", "192k"),
        "TrueHD Lossless" to Triple("truehd", "mkv", null),
        "DTS Surround" to Triple("dts", "dts", "768k"),
        "ALAC Lossless" to Triple("alac", "m4a", null)
    )

    fun getCodec(name: String): AudioCodec? = CODECS[name.lowercase()]

    fun getContainer(name: String): Container? = CONTAINERS[name.lowercase()]

    fun getCompatibleContainers(codec: String): List<Container> =
        CONTAINERS.values.filter { codec.lowercase() in it.supportedCodecs }

    /** Port of get_ffmpeg_encode_args - returns arg pairs to append to the ffmpeg cmd. */
    fun encodeArgs(codecName: String, bitrate: String?, sampleRate: Int = 48000): List<String> {
        val codec = getCodec(codecName) ?: CODECS.getValue("aac")
        val args = mutableListOf("-c:a", codec.ffmpegName)
        if (codec.supportsBitrate) {
            args += "-b:a"
            args += bitrate ?: codec.defaultBitrate
        }
        args += listOf("-ar", sampleRate.toString())
        when (codecName.lowercase()) {
            "mp3" -> args += listOf("-q:a", "0")
            "opus" -> args += listOf("-vbr", "on")
            "vorbis" -> args += listOf("-q:a", "6")
            "truehd" -> args += listOf("-strict", "experimental")
        }
        return args
    }

    /** Port of get_output_args. */
    fun outputArgs(containerName: String): List<String> {
        val container = getContainer(containerName) ?: CONTAINERS.getValue("m4a")
        val args = mutableListOf("-f", container.ffmpegFormat)
        if (containerName in setOf("m4a", "mp4")) {
            args += listOf("-movflags", "+faststart")
        }
        return args
    }

    /** Input codec -> sensible container for a stream-copy remux. Port of _PASSTHROUGH_CONTAINERS. */
    val PASSTHROUGH_CONTAINERS: Map<String, String> = mapOf(
        "ac4" to "ac4", "truehd" to "mkv", "dca" to "dts", "dts" to "dts",
        "eac3" to "mkv", "ac3" to "mkv", "aac" to "m4a", "mp3" to "mp3",
        "opus" to "ogg", "vorbis" to "ogg", "flac" to "flac", "alac" to "m4a",
        "pcm_s16le" to "wav", "pcm_s24le" to "wav", "pcm_f32le" to "wav"
    )
}
