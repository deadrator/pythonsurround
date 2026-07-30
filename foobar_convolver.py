#!/usr/bin/env python3
"""
Foobar Audio Convolver Module
Supports HeSuVi format with Atmos impulse response files (48kHz/44.1kHz).
"""

import numpy as np
from pathlib import Path
from typing import Dict, List, Optional
import wave
import subprocess
import shutil

try:
    from scipy.io import wavfile
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

HESUVI_CHANNELS_51 = ["FL", "FR", "FC", "LFE", "BL", "BR"]
HESUVI_CHANNELS_71 = ["FL", "FR", "FC", "LFE", "SL", "SR", "BL", "BR"]


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
    
    def generate_convolution_filter(self, channel: str, profile: Optional[str] = None) -> Optional[str]:
        ir = self.get_ir_for_channel(channel, profile)
        if not ir or not ir.is_valid:
            return None
        ir_path = ir.filepath.replace("\\", "/").replace(":", "\\:")
        return f"afir=ir='{ir_path}':length=1.0:type=l:gain=1.0"
    
    def apply_convolution(self, input_file: str, output_file: str, layout: str = "5.1",
                          sample_rate: int = 48000, profile: Optional[str] = None,
                          quality: str = "256k") -> bool:
        filters = {}
        channels = HESUVI_CHANNELS_71 if layout == "7.1" else HESUVI_CHANNELS_51
        for ch in channels:
            if ch == "LFE":
                continue
            f = self.generate_convolution_filter(ch, profile)
            if f:
                filters[ch] = f
        
        if not filters:
            print("No impulse responses found")
            return False
        
        parts = []
        for i, ch in enumerate(channels):
            parts.append(f"[0:a]pan=mono|c0=c{i}[ch{i}]")
            if ch in filters:
                parts.append(f"[ch{i}]{filters[ch]}[conv{i}]")
            else:
                parts.append(f"[ch{i}]acopy[conv{i}]")
        
        fl = channels.index("FL") if "FL" in channels else 0
        fr = channels.index("FR") if "FR" in channels else 1
        fc = channels.index("FC") if "FC" in channels else 2
        
        if layout == "5.1":
            bl = channels.index("BL") if "BL" in channels else 4
            br = channels.index("BR") if "BR" in channels else 5
            parts.append(
                f"[conv{fl}]volume=1.0[vfl];"
                f"[conv{fr}]volume=1.0[vfr];"
                f"[conv{fc}]volume=0.707[vfc];"
                f"[conv{bl}]volume=0.707[vbl];"
                f"[conv{br}]volume=0.707[vbr];"
                f"[vfl][vfc][vbl]amix=inputs=3:duration=first[left];"
                f"[vfr][vfc][vbr]amix=inputs=3:duration=first[right];"
                f"[left][right]amerge=inputs=2[out]"
            )
        else:
            sl = channels.index("SL") if "SL" in channels else 4
            sr = channels.index("SR") if "SR" in channels else 5
            bl = channels.index("BL") if "BL" in channels else 6
            br = channels.index("BR") if "BR" in channels else 7
            parts.append(
                f"[conv{fl}]volume=1.0[vfl];"
                f"[conv{fr}]volume=1.0[vfr];"
                f"[conv{fc}]volume=0.707[vfc];"
                f"[conv{sl}]volume=0.707[vsl];"
                f"[conv{sr}]volume=0.707[vsr];"
                f"[conv{bl}]volume=0.707[vbl];"
                f"[conv{br}]volume=0.707[vbr];"
                f"[vfl][vfc][vsl][vbl]amix=inputs=4:duration=first[left];"
                f"[vfr][vfc][vsr][vbr]amix=inputs=4:duration=first[right];"
                f"[left][right]amerge=inputs=2[out]"
            )
        
        fc_str = ";".join(parts)
        cmd = ["ffmpeg", "-i", input_file, "-filter_complex", fc_str,
               "-map", "[out]", "-c:a", "aac", "-b:a", quality,
               "-ar", str(sample_rate), "-movflags", "+faststart", "-y", output_file]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"FFmpeg error: {result.stderr[-500:]}")
            return result.returncode == 0
        except Exception as e:
            print(f"Error: {e}")
            return False
    
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
