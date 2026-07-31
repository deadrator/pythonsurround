#!/usr/bin/env python3
"""
Channel Audio Visualizer Engine
Visualizes per-channel audio levels for surround content (5.1 / 7.1 / Atmos
and any other layout FFmpeg can decode - M4A, MP4, MKV, FLAC, OGG, WAV, ...).

Provides:
    - analyze_file()      : probe channels/sample-rate/layout/duration/names
    - DecodedAudio        : FFmpeg-decode a file to float32 PCM (memory-mapped,
                            bounded memory) with random access for play/seek
    - compute_levels()    : per-channel RMS and peak for a PCM block
    - SystemCapture       : live system playback capture (sounddevice WASAPI
                            loopback on Windows, PulseAudio monitor on Linux)

The engine is used by the GUI visualizer panel (visualizer_gui.py), the TUI
CLI (visualize_audio.py) and the main GUI app.
"""

import numpy as np
import os
import shutil
import struct
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

try:
    from foobar_convolver import probe_audio_stream
except ImportError:  # pragma: no cover
    probe_audio_stream = None

# Optional system capture backend
try:
    import sounddevice as sd  # type: ignore
    HAS_SOUNDDEVICE = True
except ImportError:
    sd = None
    HAS_SOUNDDEVICE = False

# Default level analysis window in seconds
WINDOW_SECONDS = 0.5

# Channel names for common FFmpeg channel layouts (decoded channel order)
CHANNEL_NAMES = {
    "mono": ["M"],
    "stereo": ["L", "R"],
    "2.1": ["L", "R", "LFE"],
    "3.0": ["L", "R", "C"],
    "4.0": ["FL", "FR", "BL", "BR"],
    "5.0": ["FL", "FR", "FC", "BL", "BR"],
    "5.1": ["FL", "FR", "FC", "LFE", "BL", "BR"],
    "5.1(side)": ["FL", "FR", "FC", "LFE", "SL", "SR"],
    "6.1": ["FL", "FR", "FC", "LFE", "BL", "BR", "BC"],
    "7.1": ["FL", "FR", "FC", "LFE", "BL", "BR", "SL", "SR"],
    "7.1(wide)": ["FL", "FR", "FC", "LFE", "BL", "BR", "FWL", "FWR"],
    "7.1(wide-side)": ["FL", "FR", "FC", "LFE", "SL", "SR", "FWL", "FWR"],
}


def channel_names_for(layout: str, channels: int) -> List[str]:
    """Return display names for a decoded channel count."""
    if layout in CHANNEL_NAMES:
        return CHANNEL_NAMES[layout]
    # Fall back by channel count (WAV files often lack layout metadata)
    if channels == 1:
        return ["M"]
    if channels == 2:
        return ["L", "R"]
    if channels == 6:
        return CHANNEL_NAMES["5.1"]
    if channels == 8:
        return CHANNEL_NAMES["7.1"]
    return [f"Ch{i + 1}" for i in range(max(channels, 1))]


def _probe_duration(file_path: str) -> float:
    """Probe stream duration in seconds with ffprobe (0.0 on failure)."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", file_path],
            capture_output=True, text=True)
        return float(result.stdout.strip()) or 0.0
    except (ValueError, Exception):
        return 0.0


def analyze_file(file_path: str) -> Dict:
    """
    Analyze an audio file and return metadata.

    Returns:
        Dict with 'file', 'sample_rate', 'channels', 'channel_layout',
        'channel_names', 'duration' (seconds), 'format'.
    """
    info = probe_audio_stream(file_path) if probe_audio_stream else {}
    channels = int(info.get("channels", 2) or 2)
    sample_rate = int(info.get("sample_rate", 48000) or 48000)
    layout = str(info.get("channel_layout", "") or "unknown")
    if layout.lower() in ("unknown", ""):
        # Fall back by channel count (WAV files often lack layout metadata)
        layout = {1: "mono", 2: "stereo", 6: "5.1", 8: "7.1"}.get(channels, "unknown")
    names = channel_names_for(layout, channels)
    return {
        "file": file_path,
        "sample_rate": sample_rate,
        "channels": channels,
        "channel_layout": layout,
        "channel_names": names,
        "duration": _probe_duration(file_path),
        "format": Path(file_path).suffix.lstrip(".").upper() or "AUDIO",
    }


def _parse_wav_header(path: str) -> Tuple[int, int, int, int]:
    """
    Parse a WAV header and return (sample_rate, channels, data_offset, data_bytes).

    Handles PCM (1), IEEE float (3) and extensible (0xFFFE) format chunks.
    """
    with open(path, "rb") as f:
        riff = f.read(12)
        if len(riff) < 12 or riff[:4] != b"RIFF" or riff[8:12] != b"WAVE":
            raise ValueError("Not a RIFF/WAVE file")
        sample_rate = channels = data_offset = data_bytes = 0
        while True:
            hdr = f.read(8)
            if len(hdr) < 8:
                break
            chunk_id, size = struct.unpack("<4sI", hdr)
            pos = f.tell()
            if chunk_id == b"fmt ":
                fmt = f.read(min(size, 40))
                if len(fmt) >= 16:
                    format_tag, channels, sample_rate, _ = struct.unpack("<HHII", fmt[:12])
                    if format_tag == 0xFFFE and len(fmt) >= 40:
                        # extensible: subformat GUID first 2 bytes = real format
                        format_tag = struct.unpack("<H", fmt[24:26])[0]
                # Only float32 (3) and 16-bit PCM (1) are expected here
            elif chunk_id == b"data":
                data_offset = pos
                data_bytes = size
                break
            f.seek(pos + size + (size & 1))
    if not data_offset:
        raise ValueError("No data chunk found in WAV")
    return sample_rate, channels, data_offset, data_bytes


class DecodedAudio:
    """
    An FFmpeg-decoded audio file as float32 PCM, memory-mapped from a temp WAV.

    Provides random access blocks so visualization can play/seek without
    loading the whole file into RAM.
    """

    def __init__(self, file_path: str, sample_rate: Optional[int] = None,
                 channel_names: Optional[List[str]] = None):
        self.source = file_path
        self.tmp_dir = tempfile.mkdtemp(prefix="vis_audio_")
        self.wav_path = os.path.join(self.tmp_dir, "audio.wav")
        self._mmap = None

        cmd = ["ffmpeg", "-y", "-i", file_path, "-c:a", "pcm_f32le"]
        if sample_rate:
            cmd += ["-ar", str(sample_rate)]
        cmd += [self.wav_path]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(
                    f"Failed to decode audio: {(result.stderr or '')[-300:]}")

            self.sample_rate, self.channels, offset, nbytes = _parse_wav_header(self.wav_path)
            self.total_samples = nbytes // (4 * self.channels)
            self.duration = self.total_samples / self.sample_rate if self.sample_rate else 0.0

            layout = ""
            if probe_audio_stream:
                info = probe_audio_stream(file_path)
                layout = str(info.get("channel_layout", "") or "")
            self.channel_layout = layout or ("unknown" if channel_names is None else "custom")
            self.channel_names = channel_names or channel_names_for(self.channel_layout, self.channels)

            self._mmap = np.memmap(
                self.wav_path, dtype=np.float32, mode="r",
                offset=offset, shape=(self.total_samples, self.channels))
        except Exception:
            # Clean up the temp dir on any failure so nothing leaks
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
            raise

    def get_block(self, start_sample: int, count: int) -> np.ndarray:
        """Return a (n, channels) float32 block starting at start_sample."""
        if self._mmap is None or self.total_samples <= 0:
            return np.zeros((0, self.channels), dtype=np.float32)
        start = max(0, min(int(start_sample), self.total_samples))
        end = min(start + int(count), self.total_samples)
        if end <= start:
            return np.zeros((0, self.channels), dtype=np.float32)
        # Copy: blocks are small, and a view would keep the temp file locked
        # on Windows until released, breaking cleanup()
        return np.array(self._mmap[start:end], copy=True)

    def cleanup(self):
        """Close the memory map and remove the temp WAV."""
        if self._mmap is not None:
            try:
                del self._mmap
            except Exception:
                pass
            self._mmap = None
        try:
            import shutil
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
        except Exception:
            pass

    def __enter__(self) -> 'DecodedAudio':
        return self

    def __exit__(self, *exc):
        self.cleanup()
        return False


def compute_levels(pcm_block: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute per-channel RMS and peak levels for a PCM block.

    Args:
        pcm_block: (n_samples, n_channels) float32 array.

    Returns:
        (rms_per_channel, peak_per_channel) float32 arrays.
    """
    block = np.asarray(pcm_block, dtype=np.float32)
    n_channels = block.shape[1] if block.ndim > 1 else 1
    if block.ndim == 1:
        block = block[:, None]
    if len(block) == 0:
        return np.zeros(n_channels, dtype=np.float32), np.zeros(n_channels, dtype=np.float32)
    rms = np.sqrt(np.mean(np.square(block), axis=0)).astype(np.float32)
    peak = np.max(np.abs(block), axis=0).astype(np.float32)
    return rms, peak


def level_to_meter(value: float) -> float:
    """Map a linear amplitude to a 0..1 meter level (60 dB dynamic range)."""
    db = 20.0 * np.log10(max(float(value), 1e-9))
    return float(np.clip((db + 60.0) / 60.0, 0.0, 1.0))


class SystemCapture:
    """
    Live capture of system playback audio.

    Windows: WASAPI loopback of the selected output device.
    Linux:   PulseAudio/PipeWire monitor source.
    macOS:   any input device (e.g. BlackHole loopback).

    Requires the optional `sounddevice` package.
    """

    def __init__(self, callback: Callable[[np.ndarray, List[str]], None],
                 sample_rate: Optional[int] = None,
                 device_index: Optional[int] = None):
        """
        Args:
            callback: Called with (rms_per_channel, channel_names) per block.
            sample_rate: Desired capture rate (default: device default).
            device_index: Explicit device index (auto-detected if None).
        """
        self.callback = callback
        self.sample_rate = sample_rate
        self.device_index = device_index
        self.stream = None
        self.channel_names: List[str] = []

    @staticmethod
    def available() -> bool:
        return HAS_SOUNDDEVICE

    @staticmethod
    def describe() -> str:
        if not HAS_SOUNDDEVICE:
            return ("System capture requires the optional 'sounddevice' package.\n"
                    "Install with: pip install sounddevice")
        return "sounddevice available"

    @staticmethod
    def find_loopback_device() -> Tuple[Optional[int], int, int, List[str]]:
        """
        Find a loopback-capable device.

        Returns:
            (device_index, default_samplerate, channels, channel_names)
            with device_index None if none found.
        """
        if not HAS_SOUNDDEVICE:
            return None, 48000, 2, ["L", "R"]
        devices = sd.query_devices()
        hostapi_names = [h["name"] for h in sd.query_hostapis()]

        # Windows: WASAPI output devices can be captured with loopback
        for idx, dev in enumerate(devices):
            host = hostapi_names[dev["hostapi"]] if dev["hostapi"] < len(hostapi_names) else ""
            if "WASAPI" in host and dev["max_output_channels"] > 0:
                channels = max(2, min(8, int(dev["max_output_channels"])))
                names = ["L", "R"] if channels == 2 else \
                    [f"Ch{i + 1}" for i in range(channels)]
                return idx, int(dev["default_samplerate"] or 48000), channels, names

        # Linux: PulseAudio/PipeWire monitor sources
        for idx, dev in enumerate(devices):
            if dev["max_input_channels"] > 0 and "monitor" in dev["name"].lower():
                channels = max(2, min(8, int(dev["max_input_channels"])))
                names = ["L", "R"] if channels == 2 else \
                    [f"Ch{i + 1}" for i in range(channels)]
                return idx, int(dev["default_samplerate"] or 48000), channels, names

        # Fallback: default input device
        idx = sd.default.device[0]
        if idx is not None and idx >= 0:
            dev = devices[idx]
            channels = max(2, min(8, int(dev["max_input_channels"] or 2)))
            return idx, int(dev["default_samplerate"] or 48000), channels, ["L", "R"]
        return None, 48000, 2, ["L", "R"]

    def start(self) -> bool:
        """Start capturing. Returns True on success (False if unavailable/failed)."""
        if not HAS_SOUNDDEVICE:
            return False
        try:
            idx, rate, channels, names = self.find_loopback_device()
            if idx is None:
                return False
            self.device_index = idx
            self.sample_rate = self.sample_rate or rate
            self.channel_names = names

            def _cb(indata, frames, time_info, status):
                rms, _ = compute_levels(indata)
                try:
                    self.callback(rms, self.channel_names)
                except Exception:
                    pass

            is_wasapi = False
            try:
                host = sd.query_hostapis(sd.query_devices(idx)["hostapi"])["name"]
                is_wasapi = "WASAPI" in host
            except Exception:
                pass

            kwargs = dict(device=idx, channels=channels,
                          samplerate=self.sample_rate, callback=_cb)
            if is_wasapi:
                kwargs["extra_settings"] = sd.WasapiSettings(loopback=True)
            self.stream = sd.InputStream(**kwargs)
            self.stream.start()
            return True
        except Exception as e:
            print(f"System capture error: {e}")
            return False

    def stop(self):
        """Stop capturing."""
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
