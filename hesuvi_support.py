#!/usr/bin/env python3
"""
HeSuVi (Headphone Surround Virtualizer) Support Module

HeSuVi uses WAV impulse responses for headphone EQ and surround virtualization.
This module provides:
- Import HeSuVi EQ profiles
- Export to HeSuVi-compatible format
- Convert between HeSuVi and SOFA formats
- Generate HesuVi-compatible impulse responses

HeSuVi Directory Structure:
    %APPDATA%/HeSuVi/impulse/
    ├── profile_name/
    │   ├── FL.wav
    │   ├── FR.wav
    │   ├── FC.wav
    │   ├── LFE.wav
    │   ├── BL.wav
    │   ├── BR.wav
    │   ├── SL.wav (7.1 only)
    │   └── SR.wav (7.1 only)
    └── ...

WAV Format: 48kHz, 32-bit float, mono
"""

import numpy as np
import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import platform
import shutil

# Try to use scipy for reliable WAV I/O, fallback to wave module
try:
    from scipy.io import wavfile
    HAS_SCIPY = True
except ImportError:
    import wave
    HAS_SCIPY = False


# HeSuVi channel labels
HESUVI_CHANNELS_51 = ["FL", "FR", "FC", "LFE", "BL", "BR"]
HESUVI_CHANNELS_71 = ["FL", "FR", "FC", "LFE", "SL", "SR", "BL", "BR"]

# Standard HeSuVi WAV format
HESUVI_SAMPLE_RATE = 48000
HESUVI_SAMPLE_WIDTH = 4  # 32-bit float
HESUVI_CHANNELS = 1  # Mono


class HeSuViProfile:
    """Represents a HeSuVi EQ/virtualization profile."""
    
    def __init__(self, name: str, layout: str = "5.1"):
        """
        Initialize HeSuVi profile.
        
        Args:
            name: Profile name
            layout: "5.1" or "7.1"
        """
        self.name = name
        self.layout = layout
        self.impulses: Dict[str, np.ndarray] = {}
        
        # Initialize empty impulses for each channel
        channels = HESUVI_CHANNELS_71 if layout == "7.1" else HESUVI_CHANNELS_51
        for ch in channels:
            self.impulses[ch] = np.zeros(1024, dtype=np.float32)
    
    def set_impulse(self, channel: str, impulse: np.ndarray):
        """Set impulse response for a channel."""
        self.impulses[channel] = impulse.astype(np.float32)
    
    def get_impulse(self, channel: str) -> Optional[np.ndarray]:
        """Get impulse response for a channel."""
        return self.impulses.get(channel)
    
    def get_sample_rate(self) -> int:
        """Get sample rate of impulses."""
        return HESUVI_SAMPLE_RATE


class HeSuViManager:
    """Manager for HeSuVi profiles and impulse responses."""
    
    def __init__(self, hesuvi_dir: Optional[str] = None):
        """
        Initialize HeSuVi manager.
        
        Args:
            hesuvi_dir: Path to HeSuVi impulse directory.
                       If None, uses default location.
        """
        if hesuvi_dir:
            self.hesuvi_dir = Path(hesuvi_dir)
        else:
            self.hesuvi_dir = self._get_default_hesuvi_dir()
    
    def _get_default_hesuvi_dir(self) -> Path:
        """Get default HeSuVi directory based on OS."""
        if platform.system() == "Windows":
            appdata = os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
            return Path(appdata) / "HeSuVi" / "impulse"
        elif platform.system() == "Darwin":
            return Path.home() / "Library" / "Application Support" / "HeSuVi" / "impulse"
        else:
            return Path.home() / ".hesuvi" / "impulse"
    
    def get_profiles_dir(self) -> Path:
        """Get profiles directory, creating if needed."""
        self.hesuvi_dir.mkdir(parents=True, exist_ok=True)
        return self.hesuvi_dir
    
    def list_profiles(self) -> List[str]:
        """List all available HeSuVi profiles."""
        profiles_dir = self.get_profiles_dir()
        profiles = []
        
        for item in profiles_dir.iterdir():
            if item.is_dir():
                # Check if it contains WAV files
                wav_files = list(item.glob("*.wav"))
                if wav_files:
                    profiles.append(item.name)
        
        return sorted(profiles)
    
    def load_profile(self, profile_name: str) -> Optional[HeSuViProfile]:
        """
        Load a HeSuVi profile.
        
        Args:
            profile_name: Name of the profile
        
        Returns:
            HeSuViProfile or None if not found
        """
        profile_dir = self.get_profiles_dir() / profile_name
        
        if not profile_dir.exists():
            return None
        
        # Determine layout based on available channels
        has_side = (profile_dir / "SL.wav").exists()
        layout = "7.1" if has_side else "5.1"
        
        profile = HeSuViProfile(profile_name, layout)
        
        # Load each channel's impulse response
        channels = HESUVI_CHANNELS_71 if layout == "7.1" else HESUVI_CHANNELS_51
        
        for ch in channels:
            wav_path = profile_dir / f"{ch}.wav"
            if wav_path.exists():
                impulse = self._load_wav(wav_path)
                if impulse is not None:
                    profile.set_impulse(ch, impulse)
        
        return profile
    
    def save_profile(self, profile: HeSuViProfile):
        """
        Save a HeSuVi profile.
        
        Args:
            profile: HeSuViProfile to save
        """
        profile_dir = self.get_profiles_dir() / profile.name
        profile_dir.mkdir(parents=True, exist_ok=True)
        
        # Save each channel
        for ch, impulse in profile.impulses.items():
            wav_path = profile_dir / f"{ch}.wav"
            self._save_wav(wav_path, impulse)
        
        # Save profile metadata
        metadata = {
            "name": profile.name,
            "layout": profile.layout,
            "sample_rate": profile.get_sample_rate(),
            "created_by": "Atmos Binaural Converter"
        }
        
        metadata_path = profile_dir / "profile.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
    
    def _load_wav(self, wav_path: Path) -> Optional[np.ndarray]:
        """Load a WAV file and return as numpy array."""
        try:
            if HAS_SCIPY:
                # Use scipy for reliable WAV reading
                sample_rate, data = wavfile.read(str(wav_path))
                
                # Convert to float32 if needed
                if data.dtype == np.int16:
                    data = data.astype(np.float32) / 32768.0
                elif data.dtype == np.int32:
                    data = data.astype(np.float32) / 2147483648.0
                elif data.dtype != np.float32:
                    data = data.astype(np.float32)
                
                # Handle stereo by taking first channel
                if len(data.shape) > 1:
                    data = data[:, 0]
                
                # Warn if sample rate mismatch
                if sample_rate != HESUVI_SAMPLE_RATE:
                    print(f"Warning: WAV sample rate {sample_rate} != expected {HESUVI_SAMPLE_RATE}")
                
                return data
            else:
                # Fallback to wave module (16-bit PCM only)
                with wave.open(str(wav_path), 'rb') as wav_file:
                    n_channels = wav_file.getnchannels()
                    sample_width = wav_file.getsampwidth()
                    n_frames = wav_file.getnframes()
                    
                    raw_data = wav_file.readframes(n_frames)
                    
                    if sample_width == 2:  # 16-bit PCM
                        data = np.frombuffer(raw_data, dtype=np.int16)
                        data = data.astype(np.float32) / 32768.0
                    else:
                        print(f"Warning: Unsupported sample width {sample_width} (install scipy for float WAV support)")
                        return None
                    
                    if n_channels > 1:
                        data = data[::n_channels]
                    
                    return data
                    
        except Exception as e:
            print(f"Error loading WAV {wav_path}: {e}")
            return None
    
    def _save_wav(self, wav_path: Path, data: np.ndarray, sample_rate: int = HESUVI_SAMPLE_RATE):
        """Save numpy array as WAV file."""
        try:
            if HAS_SCIPY:
                # Use scipy for reliable WAV writing (32-bit float)
                wavfile.write(str(wav_path), sample_rate, data.astype(np.float32))
            else:
                # Fallback: Save as 16-bit PCM
                with wave.open(str(wav_path), 'wb') as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)  # 16-bit PCM
                    wav_file.setframerate(sample_rate)
                    
                    # Convert float32 to int16
                    data_int16 = (data * 32767).astype(np.int16)
                    wav_file.writeframes(data_int16.tobytes())
                    
        except Exception as e:
            print(f"Error saving WAV {wav_path}: {e}")
    
    def delete_profile(self, profile_name: str) -> bool:
        """Delete a HeSuVi profile."""
        profile_dir = self.get_profiles_dir() / profile_name
        
        if profile_dir.exists():
            shutil.rmtree(profile_dir)
            return True
        return False


class HeSuViConverter:
    """Convert between HeSuVi and other formats."""
    
    def __init__(self, sample_rate: int = HESUVI_SAMPLE_RATE):
        self.sample_rate = sample_rate
    
    def hesuvi_to_sofa(
        self, 
        profile: HeSuViProfile, 
        output_path: str
    ) -> bool:
        """
        Convert HeSuVi profile to SOFA format.
        
        Args:
            profile: HeSuVi profile to convert
            output_path: Output SOFA file path
        
        Returns:
            True if successful
        """
        try:
            import h5py
            
            # Get channels and their impulses
            channels = list(profile.impulses.keys())
            n_channels = len(channels)
            
            # Determine positions based on channel names
            positions = self._get_channel_positions(channels)
            
            # Stack impulses into array: [n_channels, 1, n_samples]
            n_samples = max(len(imp) for imp in profile.impulses.values())
            ir_data = np.zeros((n_channels, 1, n_samples), dtype=np.float32)
            
            for i, ch in enumerate(channels):
                imp = profile.impulses[ch]
                ir_data[i, 0, :len(imp)] = imp
            
            # Write SOFA file
            with h5py.File(output_path, 'w') as f:
                # Root attributes
                f.attrs['Conventions'] = 'SOFA'
                f.attrs['Version'] = '1.0'
                f.attrs['DataType'] = 'SimpleFreeFieldHRTF'
                f.attrs['Title'] = f'HeSuVi Profile: {profile.name}'
                
                # Source positions
                source = f.create_group('Source')
                source.create_dataset('Position', data=positions)
                
                # Receiver
                receiver = f.create_group('Receiver')
                receiver.attrs['Description'] = 'Left and Right ears'
                
                # Data
                data = f.create_group('Data')
                data.create_dataset('IR', data=ir_data)
                data.attrs['SamplingRate'] = self.sample_rate
                data.attrs['IRLength'] = n_samples
            
            return True
            
        except ImportError:
            print("h5py required for SOFA export. Install with: pip install h5py")
            return False
        except Exception as e:
            print(f"Error converting to SOFA: {e}")
            return False
    
    def sofa_to_hesuvi(
        self, 
        sofa_path: str, 
        profile_name: str,
        output_dir: Optional[str] = None
    ) -> Optional[HeSuViProfile]:
        """
        Convert SOFA file to HeSuVi profile.
        
        Args:
            sofa_path: Path to SOFA file
            profile_name: Name for the new profile
            output_dir: Output directory (uses default if None)
        
        Returns:
            HeSuViProfile or None if failed
        """
        try:
            import h5py
            
            with h5py.File(sofa_path, 'r') as f:
                # Read IR data
                ir_data = f['Data']['IR'][:]
                sample_rate = f['Data'].attrs.get('SamplingRate', self.sample_rate)
                
                # Create profile
                n_channels = ir_data.shape[0]
                layout = "7.1" if n_channels > 6 else "5.1"
                profile = HeSuViProfile(profile_name, layout)
                
                # Map channels to HeSuVi labels
                channels = HESUVI_CHANNELS_71 if layout == "7.1" else HESUVI_CHANNELS_51
                
                for i, ch in enumerate(channels):
                    if i < n_channels:
                        profile.set_impulse(ch, ir_data[i, 0, :])
                
                # Save if output directory specified
                if output_dir:
                    manager = HeSuViManager(output_dir)
                    manager.save_profile(profile)
                
                return profile
                
        except ImportError:
            print("h5py required for SOFA import. Install with: pip install h5py")
            return None
        except Exception as e:
            print(f"Error converting from SOFA: {e}")
            return None
    
    def _get_channel_positions(self, channels: List[str]) -> np.ndarray:
        """Get 3D positions for channel labels."""
        # Default speaker positions (azimuth, elevation, distance)
        position_map = {
            "FL": [-30, 0, 1],
            "FR": [30, 0, 1],
            "FC": [0, 0, 1],
            "LFE": [0, 0, 0],
            "BL": [-110, 0, 1],
            "BR": [110, 0, 1],
            "SL": [-90, 0, 1],
            "SR": [90, 0, 1],
        }
        
        positions = []
        for ch in channels:
            if ch in position_map:
                az, el, dist = position_map[ch]
                # Convert to Cartesian (simplified)
                x = dist * np.cos(np.radians(el)) * np.sin(np.radians(az))
                y = dist * np.cos(np.radians(el)) * np.cos(np.radians(az))
                z = dist * np.sin(np.radians(el))
                positions.append([x, y, z])
            else:
                positions.append([0, 0, 1])
        
        return np.array(positions, dtype=np.float32)
    
    def generate_hesuvi_from_hrtf(
        self,
        hrtf_set: Dict[str, Tuple[np.ndarray, np.ndarray]],
        profile_name: str,
        output_dir: Optional[str] = None
    ) -> Optional[HeSuViProfile]:
        """
        Generate HeSuVi profile from HRTF set.
        
        Args:
            hrtf_set: Dict of channel -> (left_ir, right_ir)
            profile_name: Name for the profile
            output_dir: Output directory
        
        Returns:
            HeSuViProfile or None if failed
        """
        # Determine layout
        has_side = "SL" in hrtf_set or "SR" in hrtf_set
        layout = "7.1" if has_side else "5.1"
        
        profile = HeSuViProfile(profile_name, layout)
        
        # For HeSuVi, we average left and right IRs or use a combined response
        for ch, (left_ir, right_ir) in hrtf_set.items():
            if ch in profile.impulses:
                # Combine left and right for HeSuVi (simplified)
                # In practice, you might want to keep them separate
                combined = (left_ir + right_ir) / 2
                profile.set_impulse(ch, combined)
        
        # Save if output directory specified
        if output_dir:
            manager = HeSuViManager(output_dir)
            manager.save_profile(profile)
        
        return profile


def export_hesuvi_from_speaker_config(
    speaker_config,
    profile_name: str = "Custom Profile",
    output_dir: Optional[str] = None
) -> Optional[HeSuViProfile]:
    """
    Export speaker configuration as HeSuVi profile.
    
    Args:
        speaker_config: SpeakerConfig object with positions
        profile_name: Name for the profile
        output_dir: Output directory
    
    Returns:
        HeSuViProfile or None if failed
    """
    try:
        from hrtf_generator import HRTFGenerator
    except ImportError:
        print("Error: hrtf_generator module not found")
        return None
    
    generator = HRTFGenerator()
    
    # Generate HRTFs from speaker positions
    hrtf_set = {}
    for label, angle in speaker_config.positions.items():
        if label != "LFE":
            left_ir, right_ir = generator.generate_simple_hrtf(angle)
            hrtf_set[label] = (left_ir, right_ir)
    
    # Convert to HeSuVi
    converter = HeSuViConverter()
    return converter.generate_hesuvi_from_hrtf(hrtf_set, profile_name, output_dir)


# Example usage
if __name__ == "__main__":
    print("HeSuVi Support Module")
    print("=" * 50)
    
    # Create manager
    manager = HeSuViManager()
    print(f"HeSuVi directory: {manager.hesuvi_dir}")
    
    # List existing profiles
    profiles = manager.list_profiles()
    print(f"\nExisting profiles: {len(profiles)}")
    for p in profiles:
        print(f"  - {p}")
    
    # Create a test profile
    print("\nCreating test profile...")
    profile = HeSuViProfile("Test Profile", "5.1")
    
    # Generate simple impulse for each channel
    generator = HRTFGenerator()
    positions = {"FL": -30, "FR": 30, "FC": 0, "BL": -110, "BR": 110}
    
    for ch, angle in positions.items():
        left_ir, right_ir = generator.generate_simple_hrtf(angle)
        profile.set_impulse(ch, (left_ir + right_ir) / 2)
    
    print(f"Profile created with {len(profile.impulses)} channels")
    print("Use manager.save_profile(profile) to save to HeSuVi directory")
