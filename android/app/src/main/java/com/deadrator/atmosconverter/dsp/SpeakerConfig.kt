package com.deadrator.atmosconverter.dsp

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * Port of speaker_shifter.py SpeakerConfig.
 *
 * Holds speaker angles (degrees, 0 = front center), normalized distances and
 * distance-based volumes, and exposes positions ready for pan-filter math.
 */
class SpeakerConfig(val layout: String = "5.1") {

    val labels: List<String> =
        if (layout == "5.1") SPEAKER_LABELS_51 else SPEAKER_LABELS_71

    val positions: MutableMap<String, Double> =
        (if (layout == "5.1") DEFAULT_POSITIONS_51 else DEFAULT_POSITIONS_71)
            .toMutableMap()

    val volumes: MutableMap<String, Double> = labels.associateWith { 1.0 }.toMutableMap()
    val distances: MutableMap<String, Double> = labels.associateWith { 0.0 }.toMutableMap()

    init {
        updateDistancesFromAngles()
    }

    private fun updateDistancesFromAngles() {
        for (label in labels) {
            if (label == "LFE") {
                distances[label] = 0.0
                continue
            }
            val angle = abs(positions.getOrDefault(label, 0.0))
            distances[label] = min(1.0, angle / 180.0)
            volumes[label] = volumeFromDistance(distances[label]!!)
        }
    }

    private fun volumeFromDistance(distance: Double): Double {
        val attenuation = 2.0
        val volume = 1.0 / (1.0 + distance * attenuation)
        return max(0.1, min(1.0, volume))
    }

    /** Set angle, optionally with an explicit distance override. */
    fun setPosition(speaker: String, angle: Double, distance: Double? = null) {
        if (speaker !in positions || speaker == "LFE") return
        positions[speaker] = max(-180.0, min(180.0, angle))
        distances[speaker] = distance?.let { max(0.0, min(1.0, it)) }
            ?: min(1.0, abs(angle) / 180.0)
        volumes[speaker] = volumeFromDistance(distances[speaker]!!)
    }

    fun getPosition(speaker: String): Double = positions.getOrDefault(speaker, 0.0)
    fun getVolume(speaker: String): Double = volumes.getOrDefault(speaker, 1.0)
    fun getDistance(speaker: String): Double = distances.getOrDefault(speaker, 0.0)

    fun reset() {
        positions.clear()
        positions.putAll(if (layout == "5.1") DEFAULT_POSITIONS_51 else DEFAULT_POSITIONS_71)
        volumes.clear()
        volumes.putAll(labels.associateWith { 1.0 })
        updateDistancesFromAngles()
    }

    /** Positions excluding LFE, ready for filter generation. */
    fun positionsForFilter(): Map<String, Double> =
        positions.filterKeys { it != "LFE" }

    companion object {
        val SPEAKER_LABELS_51 = listOf("FL", "FR", "FC", "LFE", "BL", "BR")
        val SPEAKER_LABELS_71 = listOf("FL", "FR", "FC", "LFE", "SL", "SR", "BL", "BR")

        val DEFAULT_POSITIONS_51 = mapOf(
            "FL" to -30.0, "FR" to 30.0, "FC" to 0.0, "LFE" to 0.0,
            "BL" to -110.0, "BR" to 110.0
        )
        val DEFAULT_POSITIONS_71 = mapOf(
            "FL" to -30.0, "FR" to 30.0, "FC" to 0.0, "LFE" to 0.0,
            "SL" to -90.0, "SR" to 90.0, "BL" to -150.0, "BR" to 150.0
        )

        /** Preset name -> positions (port of get_presets()). */
        val PRESETS: Map<String, Map<String, Double>> = mapOf(
            "Default 5.1" to DEFAULT_POSITIONS_51,
            "Default 7.1" to DEFAULT_POSITIONS_71,
            "Wide 5.1" to mapOf(
                "FL" to -45.0, "FR" to 45.0, "FC" to 0.0, "LFE" to 0.0,
                "BL" to -135.0, "BR" to 135.0
            ),
            "Narrow 5.1" to mapOf(
                "FL" to -20.0, "FR" to 20.0, "FC" to 0.0, "LFE" to 0.0,
                "BL" to -100.0, "BR" to 100.0
            ),
            "Gaming 7.1" to mapOf(
                "FL" to -30.0, "FR" to 30.0, "FC" to 0.0, "LFE" to 0.0,
                "SL" to -90.0, "SR" to 90.0, "BL" to -150.0, "BR" to 150.0
            ),
            "Cinema 7.1" to mapOf(
                "FL" to -25.0, "FR" to 25.0, "FC" to 0.0, "LFE" to 0.0,
                "SL" to -80.0, "SR" to 80.0, "BL" to -140.0, "BR" to 140.0
            )
        )
    }
}
