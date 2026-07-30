#!/usr/bin/env python3
"""
3D Head Model Parser Module
Parses STL and OBJ 3D model files to extract head measurements for HRTF generation.

Features:
- Parse binary and ASCII STL files
- Parse OBJ vertex data
- Extract head measurements from 3D mesh
- Convert to HeadMeasurements for personalized SOFA generation
"""

import numpy as np
import struct
import re
from pathlib import Path
from typing import Optional, Tuple, List, Dict
import math


class HeadModelParser:
    """Parse 3D head models and extract measurements."""
    
    def __init__(self):
        self.vertices: Optional[np.ndarray] = None
        self.normals: Optional[np.ndarray] = None
        self.source_file: Optional[str] = None
        self.units: str = "mm"  # Default assumption for medical/scanning data
    
    def parse(self, filepath: str) -> bool:
        """
        Parse a 3D model file (STL or OBJ).
        
        Args:
            filepath: Path to STL or OBJ file
        
        Returns:
            True if successful, False otherwise
        """
        path = Path(filepath)
        
        if not path.exists():
            print(f"File not found: {filepath}")
            return False
        
        self.source_file = str(path)
        ext = path.suffix.lower()
        
        if ext == '.stl':
            return self._parse_stl(filepath)
        elif ext == '.obj':
            return self._parse_obj(filepath)
        else:
            print(f"Unsupported file format: {ext}")
            return False
    
    def _parse_stl(self, filepath: str) -> bool:
        """Parse STL file (binary or ASCII)."""
        try:
            with open(filepath, 'rb') as f:
                # Read first 80 bytes (header)
                header = f.read(80)
                
                # Check if it's ASCII STL (starts with "solid")
                if header[:6].decode('ascii', errors='ignore').strip().lower() == 'solid':
                    # Try to read as ASCII first
                    f.seek(0)
                    if self._parse_stl_ascii(filepath):
                        return True
                
                # Parse as binary STL
                f.seek(0)
                header = f.read(80)  # Skip header
                
                # Read number of triangles
                num_triangles = struct.unpack('<I', f.read(4))[0]
                
                vertices = []
                normals = []
                
                for _ in range(num_triangles):
                    # Normal vector (12 bytes)
                    normal = struct.unpack('<3f', f.read(12))
                    normals.append(normal)
                    
                    # 3 vertices (36 bytes)
                    for _ in range(3):
                        vertex = struct.unpack('<3f', f.read(12))
                        vertices.append(vertex)
                    
                    # Attribute byte count (2 bytes)
                    f.read(2)
                
                self.vertices = np.array(vertices, dtype=np.float64)
                self.normals = np.array(normals, dtype=np.float64)
                
                # Auto-detect units
                self._detect_units()
                
                return True
                
        except Exception as e:
            print(f"Error parsing STL file: {e}")
            return False
    
    def _parse_stl_ascii(self, filepath: str) -> bool:
        """Parse ASCII STL file."""
        try:
            vertices = []
            normals = []
            
            with open(filepath, 'r') as f:
                content = f.read()
            
            # Extract normals
            normal_pattern = r'facet\s+normal\s+([-\d.e+]+)\s+([-\d.e+]+)\s+([-\d.e+]+)'
            normals = [tuple(map(float, m)) for m in re.findall(normal_pattern, content)]
            
            # Extract vertices
            vertex_pattern = r'vertex\s+([-\d.e+]+)\s+([-\d.e+]+)\s+([-\d.e+]+)'
            vertices = [tuple(map(float, v)) for v in re.findall(vertex_pattern, content)]
            
            if vertices:
                self.vertices = np.array(vertices, dtype=np.float64)
                self.normals = np.array(normals, dtype=np.float64) if normals else None
                self._detect_units()
                return True
            
            return False
            
        except Exception as e:
            print(f"Error parsing ASCII STL: {e}")
            return False
    
    def _parse_obj(self, filepath: str) -> bool:
        """Parse OBJ file (vertices only)."""
        try:
            vertices = []
            
            with open(filepath, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('v '):
                        parts = line.split()
                        if len(parts) >= 4:
                            x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                            vertices.append((x, y, z))
            
            if vertices:
                self.vertices = np.array(vertices, dtype=np.float64)
                self._detect_units()
                return True
            
            return False
            
        except Exception as e:
            print(f"Error parsing OBJ file: {e}")
            return False
    
    def _detect_units(self):
        """Auto-detect units based on bounding box size."""
        if self.vertices is None or len(self.vertices) == 0:
            return
        
        bbox = self.get_bounding_box()
        max_dim = max(bbox['width'], bbox['height'], bbox['depth'])
        
        # Typical human head is 15-25cm
        if max_dim > 1000:  # Likely millimeters
            self.units = "mm"
        elif max_dim > 100:  # Could be mm or cm, assume mm for head models
            self.units = "mm"
        elif max_dim > 10:  # Likely centimeters
            self.units = "cm"
        else:  # Likely meters
            self.units = "m"
    
    def get_bounding_box(self) -> Dict[str, float]:
        """Get bounding box of the mesh."""
        if self.vertices is None or len(self.vertices) == 0:
            return {'min': (0,0,0), 'max': (0,0,0), 'width': 0, 'height': 0, 'depth': 0}
        
        min_coords = np.min(self.vertices, axis=0)
        max_coords = np.max(self.vertices, axis=0)
        
        return {
            'min': tuple(min_coords),
            'max': tuple(max_coords),
            'width': max_coords[0] - min_coords[0],   # X axis (left-right)
            'height': max_coords[2] - min_coords[2],   # Z axis (up-down)
            'depth': max_coords[1] - min_coords[1],    # Y axis (front-back)
        }
    
    def get_volume(self) -> float:
        """Calculate approximate volume of the mesh."""
        if self.vertices is None or len(self.vertices) < 3:
            return 0.0
        
        # Use convex hull for volume estimation
        try:
            from scipy.spatial import ConvexHull
            hull = ConvexHull(self.vertices)
            return hull.volume
        except:
            # Fallback: use bounding box volume * packing factor
            bbox = self.get_bounding_box()
            return bbox['width'] * bbox['height'] * bbox['depth'] * 0.5
    
    def get_centroid(self) -> Tuple[float, float, float]:
        """Get centroid of the mesh."""
        if self.vertices is None or len(self.vertices) == 0:
            return (0.0, 0.0, 0.0)
        
        centroid = np.mean(self.vertices, axis=0)
        return tuple(centroid)
    
    def get_ear_positions(self) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
        """
        Estimate ear positions from the mesh.
        
        Returns:
            Tuple of (left_ear, right_ear) positions
        """
        if self.vertices is None or len(self.vertices) == 0:
            return ((0, 0, 0), (0, 0, 0))
        
        centroid = self.get_centroid()
        
        # Find leftmost and rightmost points (approximately ear positions)
        x_coords = self.vertices[:, 0]
        
        # Left ear: most negative X
        left_idx = np.argmin(x_coords)
        left_ear = tuple(self.vertices[left_idx])
        
        # Right ear: most positive X
        right_idx = np.argmax(x_coords)
        right_ear = tuple(self.vertices[right_idx])
        
        return (left_ear, right_ear)
    
    def extract_head_measurements(self):
        """
        Extract head measurements from the 3D model.
        
        Returns:
            HeadMeasurements object with extracted dimensions
        """
        from hrtf_generator import HeadMeasurements
        
        measurements = HeadMeasurements()
        
        if self.vertices is None or len(self.vertices) == 0:
            return measurements
        
        bbox = self.get_bounding_box()
        
        # Convert units to meters
        unit_scale = {
            'mm': 0.001,
            'cm': 0.01,
            'm': 1.0
        }
        scale = unit_scale.get(self.units, 0.001)
        
        # Extract measurements
        head_width = bbox['width'] * scale   # X axis
        head_depth = bbox['depth'] * scale   # Y axis
        head_height = bbox['height'] * scale # Z axis
        
        # Estimate head circumference (elliptical approximation)
        # C ≈ π * sqrt(2(a² + b²)) for ellipse with semi-axes a, b
        a = head_width / 2
        b = head_depth / 2
        circumference = math.pi * math.sqrt(2 * (a**2 + b**2))
        
        # Update measurements
        measurements.head_width = head_width
        measurements.head_depth = head_depth
        measurements.head_circumference = circumference
        
        # Estimate inter-ear distance (should be close to head width)
        left_ear, right_ear = self.get_ear_positions()
        ear_distance = math.sqrt(
            (right_ear[0] - left_ear[0])**2 +
            (right_ear[1] - left_ear[1])**2 +
            (right_ear[2] - left_ear[2])**2
        ) * scale
        
        measurements.inter_ear_distance = ear_distance
        
        # Estimate pinna size (roughly 10% of head height)
        measurements.ear_height = head_height * 0.1
        measurements.pinna_width = head_width * 0.05
        measurements.pinna_height = head_height * 0.1
        measurements.pinna_depth = head_depth * 0.03
        
        # Estimate shoulder width (roughly 2.5x head width)
        measurements.shoulder_width = head_width * 2.5
        
        # Neck width (roughly 0.75x head width)
        measurements.neck_width = head_width * 0.75
        
        return measurements
    
    def get_info(self) -> Dict:
        """Get summary information about the parsed model."""
        if self.vertices is None:
            return {'status': 'No model loaded'}
        
        bbox = self.get_bounding_box()
        measurements = self.extract_head_measurements()
        
        return {
            'source': self.source_file,
            'units': self.units,
            'vertices': len(self.vertices),
            'bounding_box': bbox,
            'head_width_cm': measurements.head_width * 100,
            'head_depth_cm': measurements.head_depth * 100,
            'head_circumference_cm': measurements.head_circumference * 100,
            'ear_distance_cm': measurements.inter_ear_distance * 100,
        }


def parse_head_model(filepath: str) -> Optional[Dict]:
    """
    Convenience function to parse a head model and get measurements.
    
    Args:
        filepath: Path to STL or OBJ file
    
    Returns:
        Dict with measurements or None if failed
    """
    parser = HeadModelParser()
    
    if parser.parse(filepath):
        return parser.get_info()
    
    return None


# Example usage
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        print(f"Parsing: {filepath}")
        
        info = parse_head_model(filepath)
        
        if info:
            print("\nHead Model Information:")
            print(f"  Source: {info['source']}")
            print(f"  Units: {info['units']}")
            print(f"  Vertices: {info['vertices']}")
            print(f"  Head width: {info['head_width_cm']:.1f} cm")
            print(f"  Head depth: {info['head_depth_cm']:.1f} cm")
            print(f"  Head circumference: {info['head_circumference_cm']:.1f} cm")
            print(f"  Ear distance: {info['ear_distance_cm']:.1f} cm")
        else:
            print("Failed to parse head model")
    else:
        print("Usage: python head_model_parser.py <stl_or_obj_file>")
