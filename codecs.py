#!/usr/bin/env python3
"""
Audio Codec and Container Configuration Module
Defines supported codecs, containers, and their FFmpeg encoding parameters.

Supports:
- Codecs: AAC, MP3, FLAC, Opus, Vorbis, AC3, E-AC-3
- Containers: M4A, MP4, MKV, OGG, WebM, FLAC, WAV, AVI
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class AudioCodec:
    """Audio codec configuration."""
    name: str
    extension: str
    ffmpeg_name: str
    supports_bitrate: bool = True
    default_bitrate: str = "256k"
    min_bitrate: str = "64k"
    max_bitrate: str = "640k"
    description: str = ""


@dataclass
class Container:
    """Audio container configuration."""
    name: str
    extension: str
    ffmpeg_format: str
    supported_codecs: List[str]
    description: str = ""


# ==================== CODECS ====================

CODECS: Dict[str, AudioCodec] = {
    "aac": AudioCodec(
        name="AAC",
        extension=".m4a",
        ffmpeg_name="aac",
        default_bitrate="256k",
        description="Advanced Audio Coding - Universal compatibility"
    ),
    "mp3": AudioCodec(
        name="MP3",
        extension=".mp3",
        ffmpeg_name="libmp3lame",
        default_bitrate="320k",
        description="MPEG Audio Layer III - Widely supported"
    ),
    "flac": AudioCodec(
        name="FLAC",
        extension=".flac",
        ffmpeg_name="flac",
        supports_bitrate=False,
        description="Free Lossless Audio Codec - Lossless quality"
    ),
    "opus": AudioCodec(
        name="Opus",
        extension=".opus",
        ffmpeg_name="libopus",
        default_bitrate="192k",
        min_bitrate="6k",
        max_bitrate="510k",
        description="Opus - Best quality at low bitrates"
    ),
    "vorbis": AudioCodec(
        name="Vorbis",
        extension=".ogg",
        ffmpeg_name="libvorbis",
        default_bitrate="192k",
        description="Ogg Vorbis - Open source, good quality"
    ),
    "ac3": AudioCodec(
        name="AC3",
        extension=".ac3",
        ffmpeg_name="ac3",
        default_bitrate="384k",
        description="Dolby Digital - Surround sound"
    ),
    "eac3": AudioCodec(
        name="E-AC-3",
        extension=".eac3",
        ffmpeg_name="eac3",
        default_bitrate="256k",
        description="Dolby Digital Plus - Enhanced surround"
    ),
    "pcm_s16le": AudioCodec(
        name="PCM 16-bit",
        extension=".wav",
        ffmpeg_name="pcm_s16le",
        supports_bitrate=False,
        description="Uncompressed 16-bit audio"
    ),
    "pcm_s24le": AudioCodec(
        name="PCM 24-bit",
        extension=".wav",
        ffmpeg_name="pcm_s24le",
        supports_bitrate=False,
        description="Uncompressed 24-bit audio"
    ),
}


# ==================== CONTAINERS ====================

CONTAINERS: Dict[str, Container] = {
    "m4a": Container(
        name="M4A",
        extension=".m4a",
        ffmpeg_format="ipod",
        supported_codecs=["aac", "alac"],
        description="MPEG-4 Audio - iOS/Android compatible"
    ),
    "mp4": Container(
        name="MP4",
        extension=".mp4",
        ffmpeg_format="mp4",
        supported_codecs=["aac", "mp3", "ac3", "eac3"],
        description="MPEG-4 - Universal video/audio"
    ),
    "mkv": Container(
        name="MKV",
        extension=".mkv",
        ffmpeg_format="matroska",
        supported_codecs=["aac", "mp3", "flac", "opus", "vorbis", "ac3", "eac3"],
        description="Matroska - Maximum codec support"
    ),
    "ogg": Container(
        name="OGG",
        extension=".ogg",
        ffmpeg_format="ogg",
        supported_codecs=["opus", "vorbis"],
        description="Ogg - Open source container"
    ),
    "webm": Container(
        name="WebM",
        extension=".webm",
        ffmpeg_format="webm",
        supported_codecs=["opus", "vorbis"],
        description="WebM - Web optimized"
    ),
    "flac": Container(
        name="FLAC",
        extension=".flac",
        ffmpeg_format="flac",
        supported_codecs=["flac"],
        description="FLAC container - Lossless"
    ),
    "wav": Container(
        name="WAV",
        extension=".wav",
        ffmpeg_format="wav",
        supported_codecs=["pcm_s16le", "pcm_s24le"],
        description="WAV - Uncompressed, maximum compatibility"
    ),
    "avi": Container(
        name="AVI",
        extension=".avi",
        ffmpeg_format="avi",
        supported_codecs=["mp3", "pcm_s16le"],
        description="AVI - Legacy compatibility"
    ),
}


def get_codec(codec_name: str) -> Optional[AudioCodec]:
    """Get codec by name."""
    return CODECS.get(codec_name.lower())


def get_container(container_name: str) -> Optional[Container]:
    """Get container by name."""
    return CONTAINERS.get(container_name.lower())


def get_compatible_containers(codec_name: str) -> List[Container]:
    """Get all containers that support the given codec."""
    codec_name = codec_name.lower()
    return [c for c in CONTAINERS.values() if codec_name in c.supported_codecs]


def get_compatible_codecs(container_name: str) -> List[AudioCodec]:
    """Get all codecs supported by the given container."""
    container = get_container(container_name)
    if container:
        return [CODECS[c] for c in container.supported_codecs if c in CODECS]
    return []


def get_ffmpeg_encode_args(
    codec_name: str,
    bitrate: Optional[str] = None,
    sample_rate: int = 48000
) -> List[str]:
    """
    Get FFmpeg arguments for encoding with the specified codec.
    
    Args:
        codec_name: Codec name (e.g., "aac", "mp3", "flac")
        bitrate: Target bitrate (uses default if None)
        sample_rate: Output sample rate
    
    Returns:
        List of FFmpeg arguments
    """
    codec = get_codec(codec_name)
    if not codec:
        # Default to AAC
        codec = CODECS["aac"]
    
    args = ["-c:a", codec.ffmpeg_name]
    
    if codec.supports_bitrate and bitrate:
        args.extend(["-b:a", bitrate])
    elif codec.supports_bitrate:
        args.extend(["-b:a", codec.default_bitrate])
    
    args.extend(["-ar", str(sample_rate)])
    
    # Codec-specific options
    if codec_name == "mp3":
        args.extend(["-q:a", "0"])  # VBR quality 0
    elif codec_name == "opus":
        args.extend(["-vbr", "on"])
    elif codec_name == "vorbis":
        args.extend(["-q:a", "6"])  # VBR quality 6
    
    return args


def get_output_args(container_name: str) -> List[str]:
    """
    Get FFmpeg arguments for output container format.
    
    Args:
        container_name: Container name (e.g., "m4a", "mkv", "ogg")
    
    Returns:
        List of FFmpeg arguments
    """
    container = get_container(container_name)
    if not container:
        container = CONTAINERS["m4a"]
    
    args = ["-f", container.ffmpeg_format]
    
    # Container-specific flags
    if container_name in ["m4a", "mp4"]:
        args.extend(["-movflags", "+faststart"])
    
    return args


# Preset combinations for quick selection
PRESETS = {
    "Android Best": {"codec": "aac", "container": "m4a", "bitrate": "256k"},
    "Android Compact": {"codec": "aac", "container": "m4a", "bitrate": "128k"},
    "Universal": {"codec": "aac", "container": "mp4", "bitrate": "192k"},
    "Lossless": {"codec": "flac", "container": "flac", "bitrate": None},
    "Web Optimized": {"codec": "opus", "container": "webm", "bitrate": "128k"},
    "Maximum Quality": {"codec": "flac", "container": "mkv", "bitrate": None},
    "Podcast": {"codec": "mp3", "container": "mp3", "bitrate": "192k"},
    "Legacy Compatible": {"codec": "mp3", "container": "avi", "bitrate": "320k"},
}


def get_preset(preset_name: str) -> Optional[Dict]:
    """Get preset configuration."""
    return PRESETS.get(preset_name)


def get_available_presets() -> Dict[str, Dict]:
    """Get all available presets."""
    return PRESETS.copy()


# Recommended settings for different use cases
USE_CASES = {
    "TWS Earbuds": {
        "codec": "aac",
        "container": "m4a",
        "bitrate": "256k",
        "note": "Best compatibility with Android/iOS"
    },
    "High-End Headphones": {
        "codec": "flac",
        "container": "flac",
        "bitrate": None,
        "note": "Lossless for audiophile listening"
    },
    "Spatial Audio": {
        "codec": "opus",
        "container": "ogg",
        "bitrate": "256k",
        "note": "Best for Atmos/spatial content"
    },
    "Music Production": {
        "codec": "pcm_s24le",
        "container": "wav",
        "bitrate": None,
        "note": "Uncompressed for editing"
    },
}
