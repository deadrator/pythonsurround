#!/usr/bin/env python3
"""
Audio Codec and Container Configuration Module
Defines supported codecs, containers, and their FFmpeg encoding parameters.

Supports:
- Codecs: AAC, MP3, FLAC, Opus, Vorbis, AC3, E-AC-3, AC-4, TrueHD, DTS, ALAC
- Containers: M4A, MP4, MKV, MKA, OGG, WebM, FLAC, WAV, AVI, AC-4, DTS
"""

import re
import subprocess
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
    "ac4": AudioCodec(
        name="AC-4",
        extension=".ac4",
        ffmpeg_name="ac4",
        default_bitrate="192k",
        min_bitrate="24k",
        max_bitrate="448k",
        description="Dolby AC-4 - Next-gen Atmos/broadcast (decode + remux; encode if your FFmpeg build has it)"
    ),
    "truehd": AudioCodec(
        name="TrueHD",
        extension=".thd",
        ffmpeg_name="truehd",
        supports_bitrate=False,
        description="Dolby TrueHD - Lossless Atmos surround"
    ),
    "dts": AudioCodec(
        name="DTS",
        extension=".dts",
        ffmpeg_name="dca",
        default_bitrate="768k",
        description="DTS Coherent Acoustics - Surround sound"
    ),
    "alac": AudioCodec(
        name="ALAC",
        extension=".m4a",
        ffmpeg_name="alac",
        supports_bitrate=False,
        description="Apple Lossless Audio Codec"
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
        supported_codecs=["aac", "mp3", "ac3", "eac3", "ac4"],
        description="MPEG-4 - Universal video/audio"
    ),
    "mkv": Container(
        name="MKV",
        extension=".mkv",
        ffmpeg_format="matroska",
        supported_codecs=["aac", "mp3", "flac", "opus", "vorbis", "ac3", "eac3", "truehd", "dts", "alac", "ac4"],
        description="Matroska - Maximum codec support"
    ),
    "mka": Container(
        name="MKA",
        extension=".mka",
        ffmpeg_format="matroska",
        supported_codecs=["aac", "mp3", "flac", "opus", "vorbis", "ac3", "eac3", "truehd", "dts", "alac", "ac4"],
        description="Matroska Audio - Max codec support, audio only"
    ),
    "ac4": Container(
        name="AC-4",
        extension=".ac4",
        ffmpeg_format="ac4",
        supported_codecs=["ac4"],
        description="Dolby AC-4 raw stream - Atmos / broadcast"
    ),
    "dts": Container(
        name="DTS",
        extension=".dts",
        ffmpeg_format="dts",
        supported_codecs=["dts"],
        description="Raw DTS stream"
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


# Cache of "does this FFmpeg build ship an encoder for codec X?"
_ENCODER_CACHE: Dict[str, Optional[bool]] = {}


def is_codec_encoder_available(codec_name: str) -> Optional[bool]:
    """
    Return True/False if the installed FFmpeg has an encoder for the codec.

    Returns None if FFmpeg could not be probed. Results are cached.
    """
    codec = get_codec(codec_name)
    if not codec:
        return None
    name = codec.ffmpeg_name
    if name in _ENCODER_CACHE:
        return _ENCODER_CACHE[name]
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=20)
        # ffmpeg -encoders lines look like:  " A....D alac   ALAC (...)"
        # i.e. type char + 5 capability flags, then the encoder name.
        pattern = re.compile(r"(?m)^\s*[AV].....\s+" + re.escape(name) + r"\s")
        available = bool(pattern.search(result.stdout))
    except Exception:
        available = None
    _ENCODER_CACHE[name] = available
    return available


# Cache of "does this FFmpeg build ship a decoder for codec X?"
_DECODER_CACHE: Dict[str, Optional[bool]] = {}


def is_codec_decoder_available(codec_name: str) -> Optional[bool]:
    """
    Return True/False if the installed FFmpeg has a decoder for the codec.

    Important: some codecs (e.g. AC-4) are recognized for demuxing/muxing but
    have NO decoder in FFmpeg builds, so they can only be remuxed/passed
    through, not played or re-encoded. Returns None if FFmpeg could not be
    probed. Results are cached.
    """
    codec = get_codec(codec_name)
    if not codec:
        return None
    name = codec.ffmpeg_name
    if name in _DECODER_CACHE:
        return _DECODER_CACHE[name]
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-decoders"],
            capture_output=True, text=True, timeout=20)
        # ffmpeg -decoders lines look like:  " A....D ac3   ATSC A/52A (...)"
        # i.e. type char + 5 capability flags, then the decoder name.
        pattern = re.compile(r"(?m)^\s*[AV].....\s+" + re.escape(name) + r"\s")
        available = bool(pattern.search(result.stdout))
    except Exception:
        available = None
    _DECODER_CACHE[name] = available
    return available


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
    elif codec_name == "truehd":
        args.extend(["-strict", "experimental"])  # TrueHD encoder is experimental
    
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
    "AC-4 Atmos": {"codec": "ac4", "container": "mp4", "bitrate": "192k"},
    "TrueHD Lossless": {"codec": "truehd", "container": "mkv", "bitrate": None},
    "DTS Surround": {"codec": "dts", "container": "dts", "bitrate": "768k"},
    "ALAC Lossless": {"codec": "alac", "container": "m4a", "bitrate": None},
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
