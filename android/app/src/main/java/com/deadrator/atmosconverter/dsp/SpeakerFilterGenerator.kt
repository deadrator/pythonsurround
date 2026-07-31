package com.deadrator.atmosconverter.dsp

import java.util.Locale
import kotlin.math.abs

/**
 * Port of speaker_shifter.py filter generation.
 *
 * Produces an FFmpeg `pan=stereo` filter string whose gains follow the
 * custom speaker angles + distance-based volumes.
 */
object SpeakerFilterGenerator {

    /** Simple HRTF-inspired level panning. */
    private fun computeLevelFromAngle(angleDeg: Double): Double {
        val normalized = abs(angleDeg) / 180.0
        return maxOf(0.3, 1.0 - (normalized * 0.4))
    }

    /** 5.1 channel order: FL, FR, FC, LFE, BL, BR -> c0..c5 */
    fun generate51ToBinaural(config: SpeakerConfig): String {
        val p = config.positionsForFilter()
        val fl = p.getOrDefault("FL", -30.0)
        val fr = p.getOrDefault("FR", 30.0)
        val fc = p.getOrDefault("FC", 0.0)
        val bl = p.getOrDefault("BL", -110.0)
        val br = p.getOrDefault("BR", 110.0)

        val flGain = computeLevelFromAngle(fl) * config.getVolume("FL")
        val frGain = computeLevelFromAngle(fr) * config.getVolume("FR")
        val fcGain = computeLevelFromAngle(fc) * config.getVolume("FC")
        val blGain = computeLevelFromAngle(bl) * config.getVolume("BL")
        val brGain = computeLevelFromAngle(br) * config.getVolume("BR")

        return "pan=stereo|" +
            "c0=${fmt(flGain)}*c0+${fmt(fcGain)}*c2+${fmt(blGain)}*c4|" +
            "c1=${fmt(frGain)}*c1+${fmt(fcGain)}*c2+${fmt(brGain)}*c5"
    }

    /** 7.1 channel order: FL, FR, FC, LFE, SL, SR, BL, BR -> c0..c7 */
    fun generate71ToBinaural(config: SpeakerConfig): String {
        val p = config.positionsForFilter()
        val fl = p.getOrDefault("FL", -30.0)
        val fr = p.getOrDefault("FR", 30.0)
        val fc = p.getOrDefault("FC", 0.0)
        val sl = p.getOrDefault("SL", -90.0)
        val sr = p.getOrDefault("SR", 90.0)
        val bl = p.getOrDefault("BL", -150.0)
        val br = p.getOrDefault("BR", 150.0)

        val flGain = computeLevelFromAngle(fl) * config.getVolume("FL")
        val frGain = computeLevelFromAngle(fr) * config.getVolume("FR")
        val fcGain = computeLevelFromAngle(fc) * config.getVolume("FC")
        val slGain = computeLevelFromAngle(sl) * config.getVolume("SL")
        val srGain = computeLevelFromAngle(sr) * config.getVolume("SR")
        val blGain = computeLevelFromAngle(bl) * config.getVolume("BL")
        val brGain = computeLevelFromAngle(br) * config.getVolume("BR")

        return "pan=stereo|" +
            "c0=${fmt(flGain)}*c0+${fmt(fcGain)}*c2+${fmt(slGain)}*c4+${fmt(blGain)}*c6|" +
            "c1=${fmt(frGain)}*c1+${fmt(fcGain)}*c2+${fmt(srGain)}*c5+${fmt(brGain)}*c7"
    }

    /** Full custom-layout filter chain with EQ (port of generate_binaural_filter). */
    fun generateBinauralFilter(config: SpeakerConfig): String {
        val base = "aresample=48000,"
        val pan = if (config.layout == "5.1") generate51ToBinaural(config)
                  else generate71ToBinaural(config)
        val eq = ",anequalizer=c0 f=80 w=200 g=3 t=1|c1 f=80 w=200 g=3 t=1" +
            ",equalizer=f=2500:t=q:w=1:g=2" +
            ",equalizer=f=8000:t=q:w=1:g=1"
        return base + pan + eq
    }

    private fun fmt(v: Double): String = String.format(Locale.US, "%.3f", v)
}
