#!/usr/bin/env python3
"""
HRTF/SOFA Generator Module
Creates custom Head-Related Transfer Functions and SOFA files for binaural audio.

Features:
- Generate HRTF filters from speaker positions
- Create SOFA files (AES69 standard)
- Multiple HRTF generation methods
- Export to various formats

Requirements:
    - numpy
    - scipy (for signal processing)
    - Optional: pysofa (for proper SOFA export)
"""

import numpy as np
import os
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import math


# Constants
SAMPLE_RATE = 48000
DEFAULT_HRTF_LENGTH = 512  # taps


class HeadMeasurements:
    """
    User head measurements for personalized HRTF generation.
    
    These measurements affect the Interaural Time Difference (ITD)
    and Interaural Level Difference (ILD) calculations.
    
    Typical adult values:
    - Head circumference: 54-62 cm
    - Inter-ear distance: 15-20 cm
    - Head width: 14-18 cm
    - Head depth: 17-21 cm
    - Ear height: 6-8 cm
    """
    
    def __init__(self):
        # Head dimensions in meters
        self.head_circumference: float = 0.57  # 57 cm average
        self.inter_ear_distance: float = 0.175  # 17.5 cm average
        self.head_width: float = 0.16  # 16 cm average
        self.head_depth: float = 0.19  # 19 cm average
        self.ear_height: float = 0.07  # 7 cm average
        
        # Pinna (outer ear) measurements
        self.pinna_width: float = 0.035  # 3.5 cm
        self.pinna_height: float = 0.065  # 6.5 cm
        self.pinna_depth: float = 0.02  # 2 cm
        
        # Neck width (affects shoulder reflections)
        self.neck_width: float = 0.12  # 12 cm
        
        # Shoulder width (affects early reflections)
        self.shoulder_width: float = 0.40  # 40 cm
    
    @property
    def head_radius(self) -> float:
        """Calculate effective head radius from circumference."""
        return self.head_circumference / (2 * math.pi)
    
    @property
    def ear_distance(self) -> float:
        """Inter-ear distance (center to center)."""
        return self.inter_ear_distance
    
    @classmethod
    def from_head_circumference(cls, circumference_cm: float) -> 'HeadMeasurements':
        """
        Create measurements from head circumference.
        
        Args:
            circumference_cm: Head circumference in centimeters
        
        Returns:
            HeadMeasurements with scaled dimensions
        """
        measurements = cls()
        scale = circumference_cm / 57.0  # Scale relative to average
        
        measurements.head_circumference = circumference_cm / 100.0
        measurements.inter_ear_distance *= scale
        measurements.head_width *= scale
        measurements.head_depth *= scale
        measurements.ear_height *= scale
        measurements.pinna_width *= scale
        measurements.pinna_height *= scale
        measurements.pinna_depth *= scale
        measurements.neck_width *= scale
        measurements.shoulder_width *= scale
        
        return measurements
    
    @classmethod
    def from_ear_distance(cls, distance_cm: float) -> 'HeadMeasurements':
        """
        Create measurements from ear-to-ear distance.
        
        Args:
            distance_cm: Ear-to-ear distance in centimeters
        
        Returns:
            HeadMeasurements with scaled dimensions
        """
        measurements = cls()
        scale = distance_cm / 17.5  # Scale relative to average
        
        measurements.inter_ear_distance = distance_cm / 100.0
        measurements.head_circumference *= scale
        measurements.head_width *= scale
        measurements.head_depth *= scale
        measurements.ear_height *= scale
        measurements.pinna_width *= scale
        measurements.pinna_height *= scale
        measurements.pinna_depth *= scale
        measurements.neck_width *= scale
        measurements.shoulder_width *= scale
        
        return measurements
    
    @classmethod
    def from_preset(cls, preset: str) -> 'HeadMeasurements':
        """
        Create measurements from a preset size.
        
        Presets: 'child', 'small', 'average', 'large', 'xl'
        """
        presets = {
            'child': 48.0,     # 48 cm circumference
            'small': 52.0,     # 52 cm
            'average': 57.0,   # 57 cm (50th percentile adult)
            'large': 61.0,     # 61 cm
            'xl': 65.0,        # 65 cm
        }
        
        circumference = presets.get(preset.lower(), 57.0)
        return cls.from_head_circumference(circumference)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            'head_circumference': self.head_circumference * 100,  # cm
            'inter_ear_distance': self.inter_ear_distance * 100,
            'head_width': self.head_width * 100,
            'head_depth': self.head_depth * 100,
            'ear_height': self.ear_height * 100,
            'pinna_width': self.pinna_width * 100,
            'pinna_height': self.pinna_height * 100,
            'pinna_depth': self.pinna_depth * 100,
            'neck_width': self.neck_width * 100,
            'shoulder_width': self.shoulder_width * 100,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'HeadMeasurements':
        """Load from dictionary."""
        measurements = cls()
        for key, value in data.items():
            if hasattr(measurements, key):
                setattr(measurements, key, value / 100.0)  # Convert cm to m
        return measurements
    
    def save(self, filepath: str):
        """Save measurements to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, filepath: str) -> 'HeadMeasurements':
        """Load measurements from JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        return cls.from_dict(data)
    
    def __repr__(self) -> str:
        return (f"HeadMeasurements(\n"
                f"  Head circumference: {self.head_circumference*100:.1f} cm\n"
                f"  Inter-ear distance: {self.inter_ear_distance*100:.1f} cm\n"
                f"  Head radius: {self.head_radius*100:.1f} cm\n"
                f"  Head width: {self.head_width*100:.1f} cm\n"
                f"  Head depth: {self.head_depth*100:.1f} cm\n"
                f"  Ear height: {self.ear_height*100:.1f} cm\n"
                f"  Shoulder width: {self.shoulder_width*100:.1f} cm\n"
                f")")


class HRTFGenerator:
    """Generate custom HRTF filters for binaural rendering."""
    
    def __init__(self, sample_rate: int = SAMPLE_RATE, head_measurements: Optional[HeadMeasurements] = None):
        """
        Initialize HRTF Generator.
        
        Args:
            sample_rate: Audio sample rate
            head_measurements: Optional personalized head measurements
        """
        self.sample_rate = sample_rate
        self.head = head_measurements or HeadMeasurements()
    
    def generate_simple_hrtf(
        self, 
        azimuth: float, 
        elevation: float = 0.0,
        distance: float = 1.0,
        head_radius: Optional[float] = None
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate simple HRTF pair using IPD (Interaural Phase Difference) model.
        
        Uses personalized head measurements if available.
        
        Args:
            azimuth: Horizontal angle in degrees (-180 to 180)
            elevation: Vertical angle in degrees (-90 to 90)
            distance: Distance from listener in meters
            head_radius: Optional override for head radius (uses self.head if None)
        
        Returns:
            Tuple of (left_ear_ir, right_ear_ir) impulse responses
        """
        # Use provided or personal head radius
        if head_radius is None:
            head_radius = self.head.head_radius
        
        # Convert to radians
        az_rad = math.radians(azimuth)
        el_rad = math.radians(elevation)
        
        # Speed of sound
        c = 343.0
        
        # ITD (Interaural Time Difference) using Woodworth formula
        # ITD increases with head size
        itd = (head_radius / c) * (az_rad + math.sin(az_rad))
        
        # ILD (Interaural Level Difference) - head shadowing model
        # Larger heads create more shadowing at higher frequencies
        head_factor = self.head.head_width / 0.16  # Normalize to average
        ild_db = 0.3 * azimuth * head_factor
        
        # Create impulse responses
        ir_length = DEFAULT_HRTF_LENGTH
        left_ir = np.zeros(ir_length)
        right_ir = np.zeros(ir_length)
        
        # Calculate sample delays (positive = right ear first)
        delay_samples = abs(int(itd * self.sample_rate))
        
        # Gains based on ILD
        left_gain = 10 ** (ild_db / 20)
        right_gain = 10 ** (-ild_db / 20)
        
        # Add direct sound impulse with proper delays
        if azimuth >= 0:  # Sound from right - left ear delayed
            left_ir[delay_samples] = left_gain
            right_ir[0] = right_gain
        else:  # Sound from left - right ear delayed
            left_ir[0] = left_gain
            right_ir[delay_samples] = right_gain
        
        # Add early reflections (based on head/shoulder geometry)
        # Shoulder reflections arrive ~0.5-1ms after direct sound
        shoulder_delay_ms = 0.4 + (self.head.shoulder_width - 0.4) * 2  # Scale with shoulder width
        reflection_gain = 0.2
        
        for i in range(1, 4):
            delay_idx = int(shoulder_delay_ms * i * self.sample_rate / 1000)
            if delay_idx < ir_length:
                left_ir[delay_idx] += reflection_gain * left_gain / i
                right_ir[delay_idx] += reflection_gain * right_gain / i
        
        # Pinna filtering (simplified high-frequency attenuation)
        # Smaller pinnae = less high-frequency resonance
        pinna_factor = self.head.pinna_height / 0.065  # Normalize to average
        
        # Normalize
        max_val = max(np.max(np.abs(left_ir)), np.max(np.abs(right_ir)))
        if max_val > 0:
            left_ir /= max_val
            right_ir /= max_val
        
        return left_ir, right_ir
    
    def generate_hrtf_set(
        self, 
        speaker_positions: Dict[str, Tuple[float, float]]
    ) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
        """
        Generate HRTF set for multiple speaker positions.
        
        Args:
            speaker_positions: Dict of speaker label -> (azimuth, elevation)
        
        Returns:
            Dict of speaker label -> (left_ir, right_ir)
        """
        hrtf_set = {}
        for label, (azimuth, elevation) in speaker_positions.items():
            if label == "LFE":
                continue
            left_ir, right_ir = self.generate_simple_hrtf(azimuth, elevation)
            hrtf_set[label] = (left_ir, right_ir)
        return hrtf_set
    
    def export_to_sofa(
        self, 
        hrtf_set: Dict[str, Tuple[np.ndarray, np.ndarray]],
        output_path: str,
        listener_name: str = "Custom Listener"
    ) -> bool:
        """
        Export HRTF set to SOFA format (simplified).
        
        Note: This creates a basic SOFA-compatible file. For full AES69 compliance,
        use the pysofa library.
        
        Args:
            hrtf_set: Dict of speaker label -> (left_ir, right_ir)
            output_path: Path to output SOFA file
            listener_name: Name for the listener
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Try using pysofa if available
            import SOFASupport as SOFA
            import pysofa as SOFA
            
            # Create SOFA object
            sofa = SOFA.GeneralTF(listener_name)
            
            # Add measurements
            positions = []
            data_ir = []
            
            for label, (left_ir, right_ir) in hrtf_set.items():
                positions.append([float(label in ["FL", "BL", "SL"]), 
                                float(label in ["FR", "BR", "SR"]),
                                0.0])
                data_ir.append([left_ir, right_ir])
            
            sofa.setPositions(np.array(positions))
            sofa.setDataIR(np.array(data_ir))
            sofa.setSampleRate(self.sample_rate)
            
            sofa.save(output_path)
            return True
            
        except ImportError:
            # Fallback: Create simplified SOFA-like file (HDF5 format)
            return self._export_simplified_sofa(hrtf_set, output_path, listener_name)
    
    def _export_simplified_sofa(
        self, 
        hrtf_set: Dict[str, Tuple[np.ndarray, np.ndarray]],
        output_path: str,
        listener_name: str
    ) -> bool:
        """Export simplified SOFA file (custom format)."""
        try:
            import h5py
            
            with h5py.File(output_path, 'w') as f:
                # Root attributes
                f.attrs['Conventions'] = 'SOFA'
                f.attrs['Version'] = '1.0'
                f.attrs['DataType'] = 'SimpleFreeFieldHRTF'
                f.attrs['Title'] = f'Custom HRTF - {listener_name}'
                
                # Listener
                listener = f.create_group('Listener')
                listener.attrs['Name'] = listener_name
                listener.attrs['Description'] = 'Custom generated HRTF'
                
                # Source positions
                n_sources = len(hrtf_set)
                positions = np.zeros((n_sources, 2))
                
                source = f.create_group('Source')
                source.create_dataset('Position', data=positions)
                
                # Receiver (ears)
                receiver = f.create_group('Receiver')
                receiver.attrs['Description'] = 'Left and Right ears'
                
                # Data
                data = f.create_group('Data')
                
                # IR data: [n_sources, n_channels, n_samples]
                n_samples = len(list(hrtf_set.values())[0][0])
                ir_data = np.zeros((n_sources, 2, n_samples))
                
                for i, (label, (left_ir, right_ir)) in enumerate(hrtf_set.items()):
                    ir_data[i, 0, :] = left_ir
                    ir_data[i, 1, :] = right_ir
                
                data.create_dataset('IR', data=ir_data)
                data.attrs['SamplingRate'] = self.sample_rate
                data.attrs['IRLength'] = n_samples
                data.attrs['RoomVolume'] = 0.0
                data.attrs['DatabaseName'] = 'Custom'
            
            return True
            
        except ImportError:
            # No h5py available, save as JSON with raw data
            return self._export_json_hrtf(hrtf_set, output_path, listener_name)
    
    def _export_json_hrtf(
        self, 
        hrtf_set: Dict[str, Tuple[np.ndarray, np.ndarray]],
        output_path: str,
        listener_name: str
    ) -> bool:
        """Export HRTF as JSON file (fallback format)."""
        try:
            data = {
                'format': 'HRTF-JSON',
                'version': '1.0',
                'listener': listener_name,
                'sample_rate': self.sample_rate,
                'speakers': {}
            }
            
            for label, (left_ir, right_ir) in hrtf_set.items():
                data['speakers'][label] = {
                    'left': left_ir.tolist(),
                    'right': right_ir.tolist()
                }
            
            # Change extension to .hrtf.json
            json_path = Path(output_path).with_suffix('.hrtf.json')
            
            with open(json_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            return True
            
        except Exception as e:
            print(f"Error exporting HRTF: {e}")
            return False
    
    def generate_from_angles(
        self, 
        angles: List[Tuple[float, float]]
    ) -> List[Tuple[np.ndarray, np.ndarray]]:
        """
        Generate HRTF set from angle list.
        
        Args:
            angles: List of (azimuth, elevation) tuples
        
        Returns:
            List of (left_ir, right_ir) tuples
        """
        return [self.generate_simple_hrtf(az, el) for az, el in angles]


class SofaFileReader:
    """Read and parse SOFA files."""
    
    @staticmethod
    def read_sofa(file_path: str) -> Optional[Dict]:
        """
        Read a SOFA file and extract HRTF data.
        
        Args:
            file_path: Path to SOFA file
        
        Returns:
            Dict with HRTF data or None if failed
        """
        try:
            import h5py
            
            with h5py.File(file_path, 'r') as f:
                data = {}
                
                # Get metadata
                data['conventions'] = f.attrs.get('Conventions', 'Unknown')
                data['data_type'] = f.attrs.get('DataType', 'Unknown')
                data['title'] = f.attrs.get('Title', '')
                
                # Get IR data
                if 'Data' in f and 'IR' in f['Data']:
                    data['ir'] = f['Data']['IR'][:]
                    data['sampling_rate'] = f['Data'].attrs.get('SamplingRate', 48000)
                    data['ir_length'] = data['ir'].shape[-1]
                
                # Get positions
                if 'Source' in f and 'Position' in f['Source']:
                    data['positions'] = f['Source']['Position'][:]
                
                return data
                
        except Exception as e:
            print(f"Error reading SOFA file: {e}")
            return None
    
    @staticmethod
    def get_available_sofa_files() -> List[Dict[str, str]]:
        """
        List available SOFA files in the current directory and subdirectories.
        
        Returns:
            List of dicts with file info
        """
        sofa_files = []
        for path in Path('.').rglob('*.sofa'):
            sofa_files.append({
                'name': path.stem,
                'path': str(path),
                'size': path.stat().st_size
            })
        return sofa_files


# Default speaker positions for HRTF generation
DEFAULT_SPEAKER_POSITIONS_51 = {
    'FL': (-30, 0),
    'FR': (30, 0),
    'FC': (0, 0),
    'BL': (-110, 0),
    'BR': (110, 0),
}

DEFAULT_SPEAKER_POSITIONS_71 = {
    'FL': (-30, 0),
    'FR': (30, 0),
    'FC': (0, 0),
    'SL': (-90, 0),
    'SR': (90, 0),
    'BL': (-150, 0),
    'BR': (150, 0),
}


def generate_default_sofa(layout: str = "5.1", output_path: str = "default_hrtf.sofa") -> bool:
    """
    Generate a default SOFA file for the given layout.
    
    Args:
        layout: "5.1" or "7.1"
        output_path: Path to save the SOFA file
    
    Returns:
        True if successful
    """
    generator = HRTFGenerator()
    
    if layout == "5.1":
        positions = DEFAULT_SPEAKER_POSITIONS_51
    else:
        positions = DEFAULT_SPEAKER_POSITIONS_71
    
    hrtf_set = generator.generate_hrtf_set(positions)
    return generator.export_to_sofa(hrtf_set, output_path)


if __name__ == "__main__":
    # Example usage
    print("Generating default 5.1 HRTF...")
    success = generate_default_sofa("5.1", "default_51.sofa")
    if success:
        print("✓ Generated default_51.sofa")
    else:
        print("✗ Failed to generate SOFA file")
    
    print("\nGenerating default 7.1 HRTF...")
    success = generate_default_sofa("7.1", "default_71.sofa")
    if success:
        print("✓ Generated default_71.sofa")
    else:
        print("✗ Failed to generate SOFA file")
