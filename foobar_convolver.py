#!/usr/bin/env python3
"""
Foobar Audio Convolver Module
Supports HeSuVi format with Atmos impulse response files (48kHz/44.1kHz)
and the Stereo Convolver IR workflow (Equalizer APO / HeSuVi benchmark style):

    Export:   Run a stereo dirac delta through a processing chain and capture
              it as 4 impulse response files:
                  {name}_44_left.wav,  {name}_44_right.wav
                  {name}_48_left.wav,  {name}_48_right.wav
              These contain all of the processing applied to stereo content and
              can be used with foobar2000's Stereo Convolver component
              (foo_dsp_stereoconv.dll) - see export_stereo_irs().

    Convert:  Apply a stereo IR pair (44/48 kHz, L/R) to audio files with
              overlap-add convolution, matching the Stereo Convolver behavior
              (apply_stereo_convolution()). 5.1/7.1 input is downmixed to
              stereo first, exactly like the ITU-R BS.775 pans used elsewhere
              in this project.

Convolution is implemented with numpy/scipy because FFmpeg's `afir` filter is
unreliable across builds (on FFmpeg 8.x the wet/convolution path outputs
silence). FFmpeg is still used for decode, encode, dirac generation and IR
capture.
"""

import math
import numpy as np
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import wave

try:
    from scipy.io import wavfile
    from scipy.signal import fftconvolve, resample_poly
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

HESUVI_CHANNELS_51 = ["FL", "FR", "FC", "LFE", "BL", "BR"]
HESUVI_CHANNELS_71 = ["FL", "FR", "FC", "LFE", "SL", "SR", "BL", "BR"]

# Stereo IR naming convention (foobar2000 Stereo Convolver / HeSuVi benchmark)
STEREO_IR_DIR = Path("impulse_responses") / "stereo"
STEREO_IR_SUFFIXES = {
    44100: ("_44_left.wav", "_44_right.wav"),
    48000: ("_48_left.wav", "_48_right.wav"),
}
STEREO_IR_RATE_LABELS = {44100: "44", 48000: "48"}

# Overlap-add block size in samples (~21 s at 48 kHz)
CONVOLUTION_BLOCK = 1_000_000
# Export IRs are peak-normalized to this level
IR_PEAK_NORM = 0.95


def _require_scipy():
    """Raise a clear error when scipy (required for convolution) is missing."""
    if not HAS_SCIPY:
        raise RuntimeError(
            "scipy is required for convolution. Install with: pip install scipy")


def probe_audio_stream(file_path: str) -> Dict:
    """
    Probe the first audio stream with ffprobe.

    Parses key=value lines (ffprobe's CSV output uses a fixed internal field
    order, not the -show_entries order, so positional parsing is unreliable).

    Returns:
        Dict with 'channels', 'sample_rate' and 'channel_layout'.
    """
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=channels,sample_rate,channel_layout",
             "-of", "default=noprint_wrappers=1", file_path],
            capture_output=True, text=True)
        info = {"channels": 2, "sample_rate": 48000, "channel_layout": ""}
        for line in result.stdout.splitlines():
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip()
            if key == "channels" and value:
                try:
                    info["channels"] = int(value)
                except ValueError:
                    pass
            elif key == "sample_rate" and value:
                try:
                    info["sample_rate"] = int(value)
                except ValueError:
                    pass
            elif key == "channel_layout":
                info["channel_layout"] = value
        return info
    except Exception:
        return {"channels": 2, "sample_rate": 48000, "channel_layout": ""}


def _load_wav(file_path) -> Tuple[int, np.ndarray]:
    """
    Load a WAV file as float32 in [-1, 1].

    Returns:
        (sample_rate, data) where data has shape (n_samples, n_channels).
    """
    _require_scipy()
    sample_rate, data = wavfile.read(str(file_path))
    if data.dtype == np.float32:
        pass
    elif data.dtype == np.float64:
        data = data.astype(np.float32)
    elif data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        data = data.astype(np.float32) / 2147483648.0
    elif data.dtype == np.uint8:
        data = (data.astype(np.float32) - 128.0) / 128.0
    else:
        data = data.astype(np.float32)
    if data.ndim == 1:
        data = data[:, None]
    return sample_rate, data


def _save_wav(file_path, sample_rate: int, data_float32: np.ndarray):
    """Save float32 data as a 32-bit float WAV file."""
    _require_scipy()
    wavfile.write(str(file_path), sample_rate, data_float32.astype(np.float32))


def _resample_ir(ir: np.ndarray, ir_sample_rate: int, target_sample_rate: int) -> np.ndarray:
    """Resample an impulse response to a target sample rate (if needed)."""
    if ir_sample_rate == target_sample_rate or len(ir) == 0:
        return ir
    g = math.gcd(int(ir_sample_rate), int(target_sample_rate))
    return resample_poly(
        ir, target_sample_rate // g, ir_sample_rate // g).astype(np.float32)


def downmix_to_stereo(pcm: np.ndarray) -> np.ndarray:
    """
    Downmix multi-channel PCM (n_samples, n_channels) to stereo float32.

    Uses ITU-R BS.775 style pans consistent with the rest of the app:
        5.1: L = FL + 0.707*FC + 0.707*BL   R = FR + 0.707*FC + 0.707*BR
        7.1: adds 0.707*SL/0.707*SR (side channels)
    LFE is dropped, matching the app's other conversion methods.
    """
    n_channels = pcm.shape[1]
    if n_channels == 1:
        return np.repeat(pcm, 2, axis=1)
    if n_channels == 2:
        return np.ascontiguousarray(pcm[:, :2])
    if n_channels >= 6:
        rear_l = pcm[:, 4] + (pcm[:, 6] if n_channels >= 8 else 0)
        rear_r = pcm[:, 5] + (pcm[:, 7] if n_channels >= 8 else 0)
        left = pcm[:, 0] + 0.707 * pcm[:, 2] + 0.707 * rear_l
        right = pcm[:, 1] + 0.707 * pcm[:, 2] + 0.707 * rear_r
        return np.stack([left, right], axis=1)
    # 3-5 channels: front L/R + center
    center = pcm[:, 2] if n_channels > 2 else 0
    return np.stack([pcm[:, 0] + 0.707 * center,
                     pcm[:, 1] + 0.707 * center], axis=1)


class _StreamingConvolver:
    """
    Streaming overlap-add convolver.

    Processes a long signal chunk by chunk while keeping the inter-chunk
    convolution tail, so the result is identical to a single full convolution
    but with bounded memory usage.
    """

    def __init__(self, ir: np.ndarray):
        self.ir = ir.astype(np.float64)
        self.ir_len = len(ir)
        self.tail = np.zeros(max(self.ir_len - 1, 0), dtype=np.float64)

    def process(self, chunk: np.ndarray) -> np.ndarray:
        """Convolve one chunk (1D float array). Returns len(chunk) samples."""
        chunk = np.asarray(chunk, dtype=np.float64)
        if self.ir_len == 0 or not np.any(self.ir):
            # An all-zero IR convolves to silence
            return np.zeros(len(chunk), dtype=np.float32)
        conv = fftconvolve(chunk, self.ir)  # length = len(chunk) + ir_len - 1
        out = conv[:len(chunk)].copy()
        add = min(self.ir_len - 1, len(out))
        if add > 0:
            out[:add] += self.tail[:add]
        new_tail = conv[len(chunk):]
        if len(new_tail) < self.ir_len - 1:
            new_tail = np.pad(new_tail, (0, self.ir_len - 1 - len(new_tail)))
        self.tail = new_tail
        return out.astype(np.float32)

    def flush(self) -> np.ndarray:
        """Return the remaining convolution tail (the IR tail after the signal)."""
        out = self.tail.copy()
        self.tail = np.zeros(max(self.ir_len - 1, 0), dtype=np.float64)
        return out.astype(np.float32)


# ==================== Stereo IR pair management ====================

def sanitize_ir_name(name: str) -> str:
    """Sanitize a profile name for use in IR file names."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(name)).strip("_")
    return cleaned or "Profile"


def _detect_layout_from_chain(filter_chain: str) -> str:
    """Return the channel layout covering every channel referenced in a chain."""
    max_idx = -1
    for m in re.finditer(r"(?<![A-Za-z0-9])c(\d)", filter_chain):
        max_idx = max(max_idx, int(m.group(1)))
    if max_idx >= 6:
        return "7.1"
    if max_idx >= 2:
        return "5.1"
    return "stereo"


def scan_stereo_ir_pairs(directory=None) -> List[str]:
    """List stereo IR pair base names found in a directory."""
    if directory is None:
        directory = STEREO_IR_DIR
    d = Path(directory)
    if not d.exists():
        return []
    bases = set()
    for suffix in ("_44_left.wav", "_48_left.wav"):
        for p in d.glob(f"*{suffix}"):
            bases.add(p.name[:-len(suffix)])
    return sorted(bases)


def resolve_stereo_ir_pair(base_name: str, directory=None) -> Dict[int, Dict[str, str]]:
    """
    Resolve a stereo IR pair base name to available file paths.

    Returns:
        {sample_rate: {"left": path, "right": path}} for rates where both
        files exist (44100 and/or 48000).
    """
    if directory is None:
        directory = STEREO_IR_DIR
    d = Path(directory)
    pairs = {}
    for rate, (left_suffix, right_suffix) in STEREO_IR_SUFFIXES.items():
        left = d / f"{base_name}{left_suffix}"
        right = d / f"{base_name}{right_suffix}"
        if left.exists() and right.exists():
            pairs[rate] = {"left": str(left), "right": str(right)}
    return pairs


def import_stereo_ir_pair(file_path: str, dest_dir=None) -> Optional[str]:
    """
    Import a Stereo Convolver IR pair.

    The user selects any one of the 4 files ({base}_44_left/right.wav or
    {base}_48_left/right.wav) and this copies all matching files found next
    to it into dest_dir.

    Returns:
        The sanitized base name, or None if nothing was copied.
    """
    if dest_dir is None:
        dest_dir = STEREO_IR_DIR
    src = Path(file_path)
    if not src.exists():
        return None
    stem = src.stem
    base = stem
    for suffix in ("_44_left", "_44_right", "_48_left", "_48_right"):
        if stem.endswith(suffix):
            base = stem[:-len(suffix)]
            break
    base = sanitize_ir_name(base)

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    copied = 0
    for suffix in ("_44_left", "_44_right", "_48_left", "_48_right"):
        candidate = src.parent / f"{base}{suffix}.wav"
        if candidate.exists():
            shutil.copy2(candidate, dest / candidate.name)
            copied += 1
    return base if copied else None


# ==================== IR export (dirac capture) ====================

def export_stereo_irs(
    filter_chain: str,
    name: str,
    output_dir=None,
    sample_rates: Tuple[int, ...] = (44100, 48000),
    ir_seconds: float = 1.0,
    normalize: bool = True
) -> List[str]:
    """
    Run a stereo dirac delta through a processing chain and capture it as IRs.

    Creates 4 files per the foobar2000 Stereo Convolver convention:
        {name}_44_left.wav, {name}_44_right.wav
        {name}_48_left.wav, {name}_48_right.wav

    The captured IRs contain all of the chain's processing as applied to
    stereo content (surround-only paths are zeroed), so they can be used to
    reproduce the same processing via convolution on any stereo file.

    Args:
        filter_chain: FFmpeg audio filter chain (e.g. the app's "enhanced").
        name: Profile name used in the file names.
        output_dir: Destination directory (default: impulse_responses/stereo).
        sample_rates: Sample rates to capture (44100/48000).
        ir_seconds: Length of the dirac/capture window in seconds.
        normalize: Peak-normalize each IR channel to 0.95.

    Returns:
        List of created file paths (empty on failure).
    """
    _require_scipy()
    if output_dir is None:
        output_dir = STEREO_IR_DIR
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    base = sanitize_ir_name(name)

    # Pad the stereo dirac to the layout the chain expects, so surround
    # channels are silence and only the stereo content path is captured.
    layout = _detect_layout_from_chain(filter_chain)
    pad = "" if layout == "stereo" else f"aformat=channel_layouts={layout},"
    chain = pad + filter_chain

    created = []
    tmp_dir = tempfile.mkdtemp(prefix="atmos_irs_")
    try:
        for sr in sample_rates:
            label = STEREO_IR_RATE_LABELS.get(sr, str(sr))
            dirac = os.path.join(tmp_dir, f"dirac_{sr}.wav")
            captured = os.path.join(tmp_dir, f"captured_{sr}.wav")

            # Single-sample stereo impulse via lavfi (escaped commas)
            expr = "if(eq(n\\,0)\\,1\\,0)"
            r = subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i",
                 f"aevalsrc={expr}|{expr}:s={sr}:d={ir_seconds}",
                 "-c:a", "pcm_f32le", dirac],
                capture_output=True, text=True)
            if r.returncode != 0:
                print(f"Dirac generation failed: {r.stderr[-300:]}")
                return []

            # Run the chain on the dirac and capture the impulse response
            r = subprocess.run(
                ["ffmpeg", "-y", "-i", dirac, "-af", chain,
                 "-ar", str(sr), "-ac", "2", "-c:a", "pcm_f32le", captured],
                capture_output=True, text=True)
            if r.returncode != 0:
                print(f"IR capture failed: {r.stderr[-300:]}")
                return []

            _, data = _load_wav(captured)
            if data.shape[1] < 2:
                print(f"IR capture produced non-stereo output ({data.shape[1]}ch)")
                return []
            left = data[:, 0].copy()
            right = data[:, 1].copy()

            for arr in (left, right):
                peak = float(np.max(np.abs(arr))) if len(arr) else 0.0
                if normalize and peak > 0:
                    arr *= IR_PEAK_NORM / peak

            left_path = output_dir / f"{base}_{label}_left.wav"
            right_path = output_dir / f"{base}_{label}_right.wav"
            _save_wav(left_path, sr, left)
            _save_wav(right_path, sr, right)
            created.append(str(left_path))
            created.append(str(right_path))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return created


# ==================== Stereo convolution (Stereo Convolver) ====================

def apply_stereo_convolution(
    input_file: str,
    output_file: str,
    ir_pairs: Dict[int, Dict[str, str]],
    output_sample_rate: int = 48000,
    codec_args: Optional[List[str]] = None,
    output_args: Optional[List[str]] = None
) -> bool:
    """
    Convolve audio with a stereo IR pair (foobar2000 Stereo Convolver style).

    The input is downmixed to stereo if it has more than 2 channels, then each
    stereo channel is convolved with its own IR (left/right) using overlap-add
    FFT convolution. The 44 kHz pair is used for 44.1 kHz content, otherwise
    the 48 kHz pair (the audio is resampled to match, if needed).

    Args:
        input_file: Source audio file.
        output_file: Destination file.
        ir_pairs: {sample_rate: {"left": path, "right": path}} as returned by
                  resolve_stereo_ir_pair().
        output_sample_rate: Final output sample rate.
        codec_args: FFmpeg encode arguments (default: AAC 256k).
        output_args: Additional output arguments (e.g. ["-movflags", "+faststart"]).

    Returns:
        True on success.
    """
    _require_scipy()
    if not ir_pairs:
        print("No impulse response pair selected")
        return False

    probe = probe_audio_stream(input_file)
    in_rate = probe["sample_rate"]
    in_channels = probe["channels"]

    # Pick the convolution rate: match 44.1 kHz content with the 44 pair when
    # available, otherwise prefer the 48 kHz pair.
    if in_rate == 44100 and 44100 in ir_pairs:
        ir_rate = 44100
    elif 48000 in ir_pairs:
        ir_rate = 48000
    elif 44100 in ir_pairs:
        ir_rate = 44100
    else:
        print("No usable IR pair (need _44 or _48 left/right files)")
        return False

    left_ir = _load_wav(ir_pairs[ir_rate]["left"])[1][:, 0]
    right_ir = _load_wav(ir_pairs[ir_rate]["right"])[1][:, 0]

    tmp_dir = tempfile.mkdtemp(prefix="atmos_conv_")
    try:
        raw_in = os.path.join(tmp_dir, "input.f32")
        raw_out = os.path.join(tmp_dir, "output.f32")

        # Decode at the convolution rate, keeping native channels. Exotic
        # layouts fall back to FFmpeg's own stereo downmix.
        decode_cmd = ["ffmpeg", "-y", "-i", input_file, "-ar", str(ir_rate)]
        if in_channels not in (1, 2, 6, 8):
            decode_cmd += ["-ac", "2"]
        decode_cmd += ["-c:a", "pcm_f32le", "-f", "f32le", raw_in]

        r = subprocess.run(decode_cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"Decode error: {r.stderr[-400:]}")
            return False

        n_channels = 2 if in_channels not in (1, 2, 6, 8) else in_channels
        n_bytes = os.path.getsize(raw_in)
        n_samples = n_bytes // (4 * n_channels)
        pcm = np.memmap(raw_in, dtype=np.float32, mode="r",
                        shape=(n_samples, n_channels))

        conv_left = _StreamingConvolver(left_ir)
        conv_right = _StreamingConvolver(right_ir)

        with open(raw_out, "wb") as f:
            pos = 0
            while pos < n_samples:
                end = min(pos + CONVOLUTION_BLOCK, n_samples)
                block = np.asarray(pcm[pos:end])
                stereo = downmix_to_stereo(block)
                out = np.empty((len(stereo), 2), dtype=np.float32)
                out[:, 0] = conv_left.process(stereo[:, 0])
                out[:, 1] = conv_right.process(stereo[:, 1])
                np.clip(out, -1.0, 1.0, out=out)
                f.write(out.tobytes())
                pos = end

            # IR tail after the end of the signal
            tail_l = conv_left.flush()
            tail_r = conv_right.flush()
            if np.any(tail_l) or np.any(tail_r):
                n = max(len(tail_l), len(tail_r))
                out = np.zeros((n, 2), dtype=np.float32)
                out[:len(tail_l), 0] = tail_l
                out[:len(tail_r), 1] = tail_r
                np.clip(out, -1.0, 1.0, out=out)
                f.write(out.tobytes())

        if codec_args is None:
            codec_args = ["-c:a", "aac", "-b:a", "256k"]
        if output_args is None:
            output_args = []

        enc_cmd = (["ffmpeg", "-y", "-f", "f32le", "-ar", str(ir_rate), "-ac", "2",
                    "-i", raw_out]
                   + codec_args + ["-ar", str(output_sample_rate)]
                   + output_args + [output_file])
        r = subprocess.run(enc_cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"Encode error: {r.stderr[-400:]}")
            return False
        return True
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


class ImpulseResponse:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.filename = Path(filepath).name
        self.data: Optional[np.ndarray] = None
        self.sample_rate: int = 48000
        self.channels: int = 1
        self.duration_ms: float = 0.0
        self._load()

    def _load(self):
        try:
            if HAS_SCIPY:
                self.sample_rate, self.data = wavfile.read(self.filepath)
                if len(self.data.shape) > 1:
                    self.channels = self.data.shape[1]
                    self.data = self.data[:, 0]
                if self.data.dtype == np.int16:
                    self.data = self.data.astype(np.float32) / 32768.0
                elif self.data.dtype == np.int32:
                    self.data = self.data.astype(np.float32) / 2147483648.0
            else:
                with wave.open(self.filepath, 'rb') as wf:
                    self.sample_rate = wf.getframerate()
                    self.channels = wf.getnchannels()
                    raw = wf.readframes(wf.getnframes())
                    self.data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                    if self.channels > 1:
                        self.data = self.data[::self.channels]
            self.duration_ms = len(self.data) / self.sample_rate * 1000
        except Exception as e:
            print(f"Error loading IR: {e}")

    @property
    def is_valid(self) -> bool:
        return self.data is not None and len(self.data) > 0

    @property
    def is_atmos_compatible(self) -> bool:
        return self.sample_rate in [44100, 48000]


class FoobarConvolver:
    def __init__(self, ir_directory: Optional[str] = None):
        self.ir_directory = Path(ir_directory) if ir_directory else Path.cwd() / "impulse_responses"
        self.impulse_responses: Dict[str, ImpulseResponse] = {}
        self._scan_ir_files()

    def _scan_ir_files(self):
        if not self.ir_directory.exists():
            self.ir_directory.mkdir(parents=True, exist_ok=True)
            return
        for wav_file in self.ir_directory.glob("*.wav"):
            ir = ImpulseResponse(str(wav_file))
            if ir.is_valid:
                channel = self._guess_channel(wav_file.stem)
                self.impulse_responses[channel] = ir
        for subdir in self.ir_directory.iterdir():
            if subdir.is_dir():
                for wav_file in subdir.glob("*.wav"):
                    ir = ImpulseResponse(str(wav_file))
                    if ir.is_valid:
                        channel = self._guess_channel(wav_file.stem)
                        self.impulse_responses[f"{subdir.name}/{channel}"] = ir

    def _guess_channel(self, filename: str) -> str:
        name = filename.upper()
        for ch in ["FL", "FR", "FC", "LFE", "BL", "BR", "SL", "SR"]:
            if ch in name:
                return ch
        return filename

    def get_available_profiles(self) -> List[str]:
        profiles = []
        if self.ir_directory.exists():
            for item in self.ir_directory.iterdir():
                if item.is_dir() and any(item.glob("*.wav")):
                    profiles.append(item.name)
        return sorted(profiles)

    def get_ir_for_channel(self, channel: str, profile: Optional[str] = None) -> Optional[ImpulseResponse]:
        key = f"{profile}/{channel}" if profile else channel
        return self.impulse_responses.get(key)

    def apply_convolution(self, input_file: str, output_file: str, layout: str = "5.1",
                          sample_rate: int = 48000, profile: Optional[str] = None,
                          quality: str = "256k") -> bool:
        """
        Apply per-channel Atmos impulse responses (HeSuVi style) with FFT
        convolution: each 5.1/7.1 channel is convolved with its own IR, then
        mixed down to stereo using ITU-R BS.775 coefficients.
        """
        _require_scipy()
        channels = HESUVI_CHANNELS_71 if layout == "7.1" else HESUVI_CHANNELS_51

        # Load the impulse response for every non-LFE channel
        loaded: Dict[str, Tuple[int, np.ndarray]] = {}
        for ch in channels:
            if ch == "LFE":
                continue
            ir_obj = self.get_ir_for_channel(ch, profile)
            if ir_obj and ir_obj.is_valid:
                sr_ir, data = _load_wav(ir_obj.filepath)
                mono = (data[:, 0] if data.ndim > 1 else data).astype(np.float32)
                loaded[ch] = (sr_ir, mono)

        if not loaded:
            print("No impulse responses found")
            return False

        # Convolve at the sample rate of the first IR; resample the others
        ir_rate = next(iter(loaded.values()))[0]
        irs: Dict[str, np.ndarray] = {
            ch: _resample_ir(mono, sr_ir, ir_rate) for ch, (sr_ir, mono) in loaded.items()
        }

        probe = probe_audio_stream(input_file)
        in_channels = probe["channels"]

        tmp_dir = tempfile.mkdtemp(prefix="atmos_ir_")
        try:
            raw_in = os.path.join(tmp_dir, "input.f32")
            raw_out = os.path.join(tmp_dir, "output.f32")

            decode_cmd = ["ffmpeg", "-y", "-i", input_file, "-ar", str(ir_rate)]
            if in_channels not in (1, 2, 6, 8):
                decode_cmd += ["-ac", "2"]
            decode_cmd += ["-c:a", "pcm_f32le", "-f", "f32le", raw_in]

            r = subprocess.run(decode_cmd, capture_output=True, text=True)
            if r.returncode != 0:
                print(f"Decode error: {r.stderr[-400:]}")
                return False

            n_channels = 2 if in_channels not in (1, 2, 6, 8) else in_channels
            n_bytes = os.path.getsize(raw_in)
            n_samples = n_bytes // (4 * n_channels)
            pcm = np.memmap(raw_in, dtype=np.float32, mode="r",
                            shape=(n_samples, n_channels))

            convs = {ch: _StreamingConvolver(ir) for ch, ir in irs.items()}

            def mix(buffers: Dict[str, np.ndarray], length: int) -> np.ndarray:
                """Mix convolved channels to stereo with ITU-R BS.775 coefficients."""
                left = np.zeros(length, dtype=np.float32)
                right = np.zeros(length, dtype=np.float32)
                for ch, buf in buffers.items():
                    if len(buf) < length:
                        buf = np.pad(buf, (0, length - len(buf)))
                    if ch == "FL":
                        left += buf
                    elif ch == "FR":
                        right += buf
                    elif ch == "FC":
                        left += 0.707 * buf
                        right += 0.707 * buf
                    elif ch in ("SL", "BL"):
                        left += 0.707 * buf
                    elif ch in ("SR", "BR"):
                        right += 0.707 * buf
                return np.stack([left, right], axis=1)

            with open(raw_out, "wb") as f:
                pos = 0
                while pos < n_samples:
                    end = min(pos + CONVOLUTION_BLOCK, n_samples)
                    block = np.asarray(pcm[pos:end])
                    res = {}
                    for idx, ch in enumerate(channels):
                        if ch == "LFE" or ch not in convs:
                            continue
                        col = block[:, idx] if idx < block.shape[1] else np.zeros(len(block), np.float32)
                        res[ch] = convs[ch].process(col)
                    out = mix(res, len(block))
                    np.clip(out, -1.0, 1.0, out=out)
                    f.write(out.tobytes())
                    pos = end

                # Flush and mix the trailing IR tails
                flushed = {ch: c.flush() for ch, c in convs.items()}
                if any(np.any(t) for t in flushed.values()):
                    max_len = max(len(t) for t in flushed.values())
                    out = mix(flushed, max_len)
                    np.clip(out, -1.0, 1.0, out=out)
                    f.write(out.tobytes())

            enc_cmd = (["ffmpeg", "-y", "-f", "f32le", "-ar", str(ir_rate), "-ac", "2",
                        "-i", raw_out,
                        "-c:a", "aac", "-b:a", quality,
                        "-ar", str(sample_rate), "-movflags", "+faststart",
                        output_file])
            r = subprocess.run(enc_cmd, capture_output=True, text=True)
            if r.returncode != 0:
                print(f"Encode error: {r.stderr[-400:]}")
                return False
            return True
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def import_atmos_ir(self, filepath: str, channel: str, profile: Optional[str] = None) -> bool:
        ir = ImpulseResponse(filepath)
        if not ir.is_valid:
            return False
        target_dir = self.ir_directory / profile if profile else self.ir_directory
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{channel}.wav"
        try:
            shutil.copy2(filepath, target_path)
            ir_loaded = ImpulseResponse(str(target_path))
            if ir_loaded.is_valid:
                key = f"{profile}/{channel}" if profile else channel
                self.impulse_responses[key] = ir_loaded
            return True
        except Exception as e:
            print(f"Error importing IR: {e}")
            return False

    def get_info(self) -> Dict:
        return {
            'ir_directory': str(self.ir_directory),
            'total_ir_files': len(self.impulse_responses),
            'profiles': self.get_available_profiles(),
        }


def get_convolver(ir_directory: Optional[str] = None) -> FoobarConvolver:
    return FoobarConvolver(ir_directory)
