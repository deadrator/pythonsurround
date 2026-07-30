#!/usr/bin/env python3
"""
Virtual Speaker Shifter Module
Provides FFmpeg filter chains for adjusting virtual speaker positions
in 5.1 and 7.1 surround sound configurations.
"""

from typing import Dict, List, Tuple, Optional
import math


# Default speaker positions (angles in degrees, 0 = front center)
DEFAULT_POSITIONS_51 = {
    "FL":  -30,   # Front Left
    "FR":   30,   # Front Right
    "FC":    0,   # Front Center
    "LFE":   0,   # LFE (no position)
    "BL": -110,   # Back Left
    "BR":  110,   # Back Right
}

DEFAULT_POSITIONS_71 = {
    "FL":  -30,   # Front Left
    "FR":   30,   # Front Right
    "FC":    0,   # Front Center
    "LFE":   0,   # LFE (no position)
    "SL":  -90,   # Side Left
    "SR":   90,   # Side Right
    "BL": -150,   # Back Left
    "BR":  150,   # Back Right
}

# Speaker labels for UI
SPEAKER_LABELS_51 = ["FL", "FR", "FC", "LFE", "BL", "BR"]
SPEAKER_LABELS_71 = ["FL", "FR", "FC", "LFE", "SL", "SR", "BL", "BR"]


class SpeakerConfig:
    """Configuration for virtual speaker positions with distance-based volume."""
    
    def __init__(self, layout: str = "5.1"):
        """
        Initialize speaker configuration.
        
        Args:
            layout: Either "5.1" or "7.1"
        """
        self.layout = layout
        if layout == "5.1":
            self.positions = dict(DEFAULT_POSITIONS_51)
            self.labels = SPEAKER_LABELS_51.copy()
        else:
            self.positions = dict(DEFAULT_POSITIONS_71)
            self.labels = SPEAKER_LABELS_71.copy()
        
        # Volume for each speaker (0.0 to 1.0)
        self.volumes: Dict[str, float] = {label: 1.0 for label in self.labels}
        
        # Distance from center (normalized 0-1, 0=center, 1=edge)
        self.distances: Dict[str, float] = {label: 0.0 for label in self.labels}
        
        # Initialize default distances from angles
        self._update_distances_from_angles()
    
    def _update_distances_from_angles(self):
        """Update distances based on current angles (default layout distance)."""
        for label in self.labels:
            if label == "LFE":
                self.distances[label] = 0.0
                continue
            angle = abs(self.positions.get(label, 0))
            # Map angle to distance: 0° = center (distance=0), 180° = edge (distance=1)
            self.distances[label] = min(1.0, angle / 180.0)
            # Apply distance-based volume
            self.volumes[label] = self._calculate_volume_from_distance(self.distances[label])
    
    def _calculate_volume_from_distance(self, distance: float) -> float:
        """
        Calculate volume based on distance using inverse distance law.
        
        Args:
            distance: Normalized distance (0=center, 1=edge)
        
        Returns:
            Volume multiplier (0.0 to 1.0)
        """
        # Inverse distance law with smooth rolloff
        # volume = 1 / (1 + distance * attenuation_factor)
        attenuation_factor = 2.0  # Controls how quickly volume drops
        volume = 1.0 / (1.0 + distance * attenuation_factor)
        return max(0.1, min(1.0, volume))  # Clamp between 0.1 and 1.0
    
    def set_position(self, speaker: str, angle: float, distance: Optional[float] = None):
        """
        Set speaker angle and optionally distance.
        
        Args:
            speaker: Speaker label
            angle: Angle in degrees (-180 to 180)
            distance: Optional manual distance override (0.0 to 1.0)
        """
        if speaker in self.positions and speaker != "LFE":
            self.positions[speaker] = max(-180, min(180, angle))
            
            if distance is not None:
                # Manual distance control
                self.distances[speaker] = max(0.0, min(1.0, distance))
            else:
                # Auto-calculate distance from angle
                self.distances[speaker] = min(1.0, abs(angle) / 180.0)
            
            # Update volume based on distance
            self.volumes[speaker] = self._calculate_volume_from_distance(self.distances[speaker])
    
    def get_position(self, speaker: str) -> float:
        """Get speaker angle in degrees."""
        return self.positions.get(speaker, 0)
    
    def get_volume(self, speaker: str) -> float:
        """Get speaker volume (0.0 to 1.0)."""
        return self.volumes.get(speaker, 1.0)
    
    def get_distance(self, speaker: str) -> float:
        """Get speaker distance from center (0.0 to 1.0)."""
        return self.distances.get(speaker, 0.0)
    
    def reset(self):
        """Reset to default positions."""
        if self.layout == "5.1":
            self.positions = dict(DEFAULT_POSITIONS_51)
        else:
            self.positions = dict(DEFAULT_POSITIONS_71)
        self.volumes = {label: 1.0 for label in self.labels}
        self._update_distances_from_angles()
    
    def get_positions_for_filter(self) -> Dict[str, float]:
        """Get positions formatted for FFmpeg filter."""
        return {k: v for k, v in self.positions.items() if k != "LFE"}


def angle_to_radian(angle_deg: float) -> float:
    """Convert degrees to radians."""
    return math.radians(angle_deg)


def compute_delay_from_angle(angle_deg: float, speed_of_sound: float = 343.0, 
                             head_radius: float = 0.0875) -> float:
    """
    Compute interaural time delay from speaker angle.
    
    Args:
        angle_deg: Speaker angle in degrees
        speed_of_sound: Speed of sound in m/s
        head_radius: Radius of head in meters
    
    Returns:
        Delay in seconds
    """
    angle_rad = angle_to_radian(angle_deg)
    # ITD approximation using Woodworth formula
    delay = (head_radius / speed_of_sound) * (angle_rad + math.sin(angle_rad))
    return delay


def compute_level_from_angle(angle_deg: float, spread: float = 30.0) -> float:
    """
    Compute level adjustment from speaker angle for binaural rendering.
    
    Args:
        angle_deg: Speaker angle in degrees
        spread: Spread factor in degrees
    
    Returns:
        Level multiplier (0.0 to 1.0)
    """
    # Simple HRTF-inspired level panning
    normalized = abs(angle_deg) / 180.0
    return max(0.3, 1.0 - (normalized * 0.4))


def generate_51_to_binaural_filter(config: SpeakerConfig) -> str:
    """
    Generate FFmpeg filter for 5.1 to binaural with custom speaker positions.
    
    Args:
        config: Speaker configuration with custom positions
    
    Returns:
        FFmpeg filter string
    """
    positions = config.get_positions_for_filter()
    
    # Get angles
    fl_angle = positions.get("FL", -30)
    fr_angle = positions.get("FR", 30)
    fc_angle = positions.get("FC", 0)
    bl_angle = positions.get("BL", -110)
    br_angle = positions.get("BR", 110)
    
    # Compute gains based on angles and volume (simplified HRTF)
    fl_gain = compute_level_from_angle(fl_angle) * config.get_volume("FL")
    fr_gain = compute_level_from_angle(fr_angle) * config.get_volume("FR")
    fc_gain = compute_level_from_angle(fc_angle) * config.get_volume("FC")
    bl_gain = compute_level_from_angle(bl_angle) * config.get_volume("BL")
    br_gain = compute_level_from_angle(br_angle) * config.get_volume("BR")
    
    # Pan filter with custom gains
    # 5.1 channel order: FL, FR, FC, LFE, BL, BR (c0-c5)
    pan_filter = (
        f"pan=stereo|"
        f"c0={fl_gain:.3f}*c0+{fc_gain:.3f}*c2+{bl_gain:.3f}*c4|"
        f"c1={fr_gain:.3f}*c1+{fc_gain:.3f}*c2+{br_gain:.3f}*c5"
    )
    
    return pan_filter


def generate_71_to_binaural_filter(config: SpeakerConfig) -> str:
    """
    Generate FFmpeg filter for 7.1 to binaural with custom speaker positions.
    
    Args:
        config: Speaker configuration with custom positions
    
    Returns:
        FFmpeg filter string
    """
    positions = config.get_positions_for_filter()
    
    # Get angles
    fl_angle = positions.get("FL", -30)
    fr_angle = positions.get("FR", 30)
    fc_angle = positions.get("FC", 0)
    sl_angle = positions.get("SL", -90)
    sr_angle = positions.get("SR", 90)
    bl_angle = positions.get("BL", -150)
    br_angle = positions.get("BR", 150)
    
    # Compute gains based on angles and volume
    fl_gain = compute_level_from_angle(fl_angle) * config.get_volume("FL")
    fr_gain = compute_level_from_angle(fr_angle) * config.get_volume("FR")
    fc_gain = compute_level_from_angle(fc_angle) * config.get_volume("FC")
    sl_gain = compute_level_from_angle(sl_angle) * config.get_volume("SL")
    sr_gain = compute_level_from_angle(sr_angle) * config.get_volume("SR")
    bl_gain = compute_level_from_angle(bl_angle) * config.get_volume("BL")
    br_gain = compute_level_from_angle(br_angle) * config.get_volume("BR")
    
    # Pan filter with custom gains
    # 7.1 channel order: FL, FR, FC, LFE, SL, SR, BL, BR (c0-c7)
    pan_filter = (
        f"pan=stereo|"
        f"c0={fl_gain:.3f}*c0+{fc_gain:.3f}*c2+{sl_gain:.3f}*c4+{bl_gain:.3f}*c6|"
        f"c1={fr_gain:.3f}*c1+{fc_gain:.3f}*c2+{sr_gain:.3f}*c5+{br_gain:.3f}*c7"
    )
    
    return pan_filter


def generate_binaural_filter(config: SpeakerConfig) -> str:
    """
    Generate appropriate binaural filter based on speaker configuration.
    
    Args:
        config: Speaker configuration
    
    Returns:
        FFmpeg filter string
    """
    base_filter = "aresample=48000,"
    
    if config.layout == "5.1":
        pan_filter = generate_51_to_binaural_filter(config)
    else:
        pan_filter = generate_71_to_binaural_filter(config)
    
    # Add spatial enhancement
    eq_filter = (
        ",anequalizer=c0 f=80 w=200 g=3 t=1|c1 f=80 w=200 g=3 t=1"
        ",equalizer=f=2500:t=q:w=1:g=2"
        ",equalizer=f=8000:t=q:w=1:g=1"
    )
    
    return base_filter + pan_filter + eq_filter


def get_presets() -> Dict[str, Dict[str, float]]:
    """Get preset speaker configurations."""
    return {
        "Default 5.1": dict(DEFAULT_POSITIONS_51),
        "Default 7.1": dict(DEFAULT_POSITIONS_71),
        "Wide 5.1": {
            "FL": -45, "FR": 45, "FC": 0, "LFE": 0,
            "BL": -135, "BR": 135
        },
        "Narrow 5.1": {
            "FL": -20, "FR": 20, "FC": 0, "LFE": 0,
            "BL": -100, "BR": 100
        },
        "Gaming 7.1": {
            "FL": -30, "FR": 30, "FC": 0, "LFE": 0,
            "SL": -90, "SR": 90, "BL": -150, "BR": 150
        },
        "Cinema 7.1": {
            "FL": -25, "FR": 25, "FC": 0, "LFE": 0,
            "SL": -80, "SR": 80, "BL": -140, "BR": 140
        },
    }
