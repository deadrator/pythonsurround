package com.deadrator.atmosconverter.dsp

/**
 * Port of the desktop app's FFmpeg filter presets.
 *
 * Mirrors FILTERS in gui_app.py / FILTER_PRESETS in convert_atmos.py.
 * Every chain is an FFmpeg `-af` filter string applied to the input audio.
 */
object FilterPresets {

    const val STANDARD = "aresample=48000,pan=stereo|c0=c0+0.707*c2+0.707*c4|c1=c1+0.707*c2+0.707*c5"

    const val ENHANCED = (
        "aresample=48000,pan=stereo|c0=c0+0.707*c2+0.707*c4|c1=c1+0.707*c2+0.707*c5," +
        "anequalizer=c0 f=80 w=200 g=4 t=1|c1 f=80 w=200 g=4 t=1," +
        "equalizer=f=2500:t=q:w=1:g=2,equalizer=f=8000:t=q:w=1:g=1"
        )

    const val SPATIAL = (
        "aresample=48000,aformat=channel_layouts=5.1," +
        "pan=stereo|c0=0.87*c0+0.707*c2+0.707*c4+0.25*c5|c1=0.87*c1+0.707*c2+0.707*c5+0.25*c4," +
        "anequalizer=c0 f=60 w=150 g=5 t=1|c1 f=60 w=150 g=5 t=1," +
        "equalizer=f=2000:t=q:w=1.5:g=3,equalizer=f=6000:t=q:w=1:g=2," +
        "equalizer=f=10000:t=q:w=1:g=1.5,volume=0.95"
        )

    const val UPMIX_51 = "aresample=48000,surround=chl_out=5.1"
    const val UPMIX_71 = "aresample=48000,surround=chl_out=7.1"

    const val DOWNMIX_51 = (
        "aresample=48000,pan=5.1|c0=c0|c1=c1|c2=c2|c3=c3|c4=c4+0.707*c6|c5=c5+0.707*c7"
        )

    /** Method keys used by the rest of the app (match METHOD_PRESETS keys). */
    object Method {
        const val STANDARD = "standard"
        const val ENHANCED = "enhanced"
        const val SPATIAL = "spatial"
        const val HRTF = "hrtf"
        const val ATMOS_IR = "atmos_ir"
        const val STEREO_CONV = "stereo_conv"
        const val CUSTOM = "custom"
        const val UPMIX51 = "upmix51"
        const val UPMIX71 = "upmix71"
        const val DOWNMIX51 = "downmix51"
        const val PASSTHROUGH = "passthrough"
    }

    /** Methods that always need the filter applied (even to stereo input). */
    val UPMIX_METHODS = setOf(Method.UPMIX51, Method.UPMIX71)

    /** Methods that copy the stream without re-encoding. */
    val PASSTHROUGH_METHODS = setOf(Method.PASSTHROUGH)

    val ALL_METHODS = listOf(
        Method.STANDARD, Method.ENHANCED, Method.SPATIAL, Method.HRTF,
        Method.ATMOS_IR, Method.STEREO_CONV, Method.CUSTOM,
        Method.UPMIX51, Method.UPMIX71, Method.DOWNMIX51, Method.PASSTHROUGH
    )

    fun filterFor(method: String): String? = when (method) {
        Method.STANDARD -> STANDARD
        Method.ENHANCED -> ENHANCED
        Method.SPATIAL -> SPATIAL
        Method.UPMIX51 -> UPMIX_51
        Method.UPMIX71 -> UPMIX_71
        Method.DOWNMIX51 -> DOWNMIX_51
        else -> null
    }
}
