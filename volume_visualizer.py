#!/usr/bin/env python3
"""
Volume and Sound Visualizer Module
Provides VU meters, channel levels, and waveform display for surround sound.

Features:
- Real-time VU meters for each channel
- Channel volume controls with sliders
- Peak hold indicators
- Level monitoring with color coding
"""

import tkinter as tk
from tkinter import ttk
import math
import random
from typing import Dict, List, Optional, Callable
import threading
import time


# Channel colors
CHANNEL_COLORS = {
    "FL": "#4a9eff",   # Blue - Front Left
    "FR": "#4a9eff",   # Blue - Front Right
    "FC": "#ffffff",   # White - Front Center
    "LFE": "#ff6b6b",  # Red - Subwoofer
    "BL": "#6bff6b",   # Green - Back Left
    "BR": "#6bff6b",   # Green - Back Right
    "SL": "#ffb86b",   # Orange - Side Left
    "SR": "#ffb86b",   # Orange - Side Right
}

# Default volumes (0.0 to 1.0)
DEFAULT_VOLUMES_51 = {
    "FL": 1.0, "FR": 1.0, "FC": 1.0, "LFE": 0.8, "BL": 0.8, "BR": 0.8
}
DEFAULT_VOLUMES_71 = {
    "FL": 1.0, "FR": 1.0, "FC": 1.0, "LFE": 0.8,
    "SL": 0.8, "SR": 0.8, "BL": 0.8, "BR": 0.8
}


class VUMeter(tk.Canvas):
    """Single channel VU meter with peak hold."""
    
    def __init__(self, parent, channel: str, color: str = "#4a9eff", **kwargs):
        super().__init__(parent, **kwargs)
        
        self.channel = channel
        self.color = color
        self.level = 0.0  # 0.0 to 1.0
        self.peak = 0.0
        self.peak_hold = 0.0
        self.peak_decay = 0.02
        self.width = 30
        self.height = 150
        
        self.configure(width=self.width, height=self.height, bg="#1a1a2e", highlightthickness=0)
        
    def set_level(self, level: float):
        """Set current level (0.0 to 1.0)."""
        self.level = max(0.0, min(1.0, level))
        if self.level > self.peak:
            self.peak = self.level
        self.draw()
        
    def draw(self):
        """Draw the VU meter."""
        self.delete("all")
        
        w = self.width
        h = self.height
        bar_width = w - 8
        bar_x = 4
        
        # Draw background
        self.create_rectangle(0, 0, w, h, fill="#0a0a1a", outline="")
        
        # Draw meter segments
        num_segments = 20
        segment_height = (h - 20) / num_segments
        filled_segments = int(self.level * num_segments)
        
        for i in range(num_segments):
            y = h - 15 - (i + 1) * segment_height
            segment_y = y
            
            if i < filled_segments:
                # Color based on level
                if i >= num_segments * 0.8:
                    color = "#ff4444"  # Red zone
                elif i >= num_segments * 0.6:
                    color = "#ffaa00"  # Yellow zone
                else:
                    color = self.color
            else:
                color = "#2a2a4a"  # Empty segment color
            
            self.create_rectangle(
                bar_x, segment_y,
                bar_x + bar_width, segment_y + segment_height - 2,
                fill=color, outline=""
            )
        
        # Draw peak hold indicator
        peak_y = h - 15 - self.peak * (h - 20)
        if self.peak > 0:
            self.create_rectangle(
                bar_x, peak_y - 3,
                bar_x + bar_width, peak_y,
                fill="#ffffff", outline=""
            )
        
        # Draw channel label
        self.create_text(
            w // 2, h - 8,
            text=self.channel,
            fill="#888888",
            font=("Arial", 8, "bold")
        )
    
    def decay_peak(self):
        """Decay the peak hold indicator."""
        if self.peak > self.level:
            self.peak = max(self.level, self.peak - self.peak_decay)
            self.draw()
            return True
        return False


class ChannelVolumeControl(ttk.Frame):
    """Volume control for a single channel."""
    
    def __init__(self, parent, channel: str, color: str = "#4a9eff", 
                 initial_volume: float = 1.0, on_change: Optional[Callable] = None, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.channel = channel
        self.color = color
        self.on_change = on_change
        
        # Volume variable
        self.volume = tk.DoubleVar(value=initial_volume * 100)
        
        # Channel label
        label = ttk.Label(self, text=channel, width=4, font=("Arial", 9, "bold"))
        label.pack(side=tk.LEFT, padx=(0, 5))
        
        # Volume slider
        self.slider = ttk.Scale(
            self,
            from_=0, to=100,
            variable=self.volume,
            orient=tk.HORIZONTAL,
            length=120,
            command=self._on_slider_change
        )
        self.slider.pack(side=tk.LEFT, padx=(0, 5))
        
        # Volume percentage
        self.percent_label = ttk.Label(self, text=f"{int(initial_volume * 100)}%", width=4)
        self.percent_label.pack(side=tk.LEFT)
        
        # Mute button
        self.muted = False
        self.mute_btn = ttk.Button(
            self, text="🔊", width=3,
            command=self.toggle_mute
        )
        self.mute_btn.pack(side=tk.LEFT, padx=(5, 0))
    
    def _on_slider_change(self, value):
        """Handle slider value change."""
        vol = float(value) / 100.0
        self.percent_label.config(text=f"{int(value)}%")
        if self.on_change:
            self.on_change(self.channel, vol)
    
    def toggle_mute(self):
        """Toggle mute state."""
        self.muted = not self.muted
        self.mute_btn.config(text="🔇" if self.muted else "🔊")
        vol = 0.0 if self.muted else self.volume.get() / 100.0
        if self.on_change:
            self.on_change(self.channel, vol)
    
    def get_volume(self) -> float:
        """Get current volume (0.0 to 1.0)."""
        if self.muted:
            return 0.0
        return self.volume.get() / 100.0
    
    def set_volume(self, volume: float):
        """Set volume (0.0 to 1.0)."""
        self.volume.set(volume * 100)
        self.percent_label.config(text=f"{int(volume * 100)}%")


class SoundVisualizer(tk.Canvas):
    """Multi-channel sound visualizer with waveform display."""
    
    def __init__(self, parent, channels: List[str], **kwargs):
        super().__init__(parent, **kwargs)
        
        self.channels = channels
        self.channel_data: Dict[str, List[float]] = {ch: [0.0] * 64 for ch in channels}
        self.width = 400
        self.height = 200
        
        self.configure(width=self.width, height=self.height, bg="#0a0a1a", highlightthickness=0)
        
    def add_data(self, channel: str, value: float):
        """Add a new data point for a channel."""
        if channel in self.channel_data:
            self.channel_data[channel].append(value)
            if len(self.channel_data[channel]) > 64:
                self.channel_data[channel].pop(0)
            self.draw()
    
    def set_all_levels(self, levels: Dict[str, float]):
        """Set levels for all channels at once."""
        for channel, level in levels.items():
            if channel in self.channel_data:
                # Add to waveform data
                self.channel_data[channel].append(level)
                if len(self.channel_data[channel]) > 64:
                    self.channel_data[channel].pop(0)
        self.draw()
    
    def draw(self):
        """Draw the visualizer."""
        self.delete("all")
        
        w = self.width
        h = self.height
        
        # Background
        self.create_rectangle(0, 0, w, h, fill="#0a0a1a", outline="")
        
        # Draw grid lines
        for i in range(1, 4):
            y = i * h // 4
            self.create_line(0, y, w, y, fill="#1a1a3a", dash=(2, 4))
        
        # Draw waveforms for each channel
        num_channels = len(self.channels)
        if num_channels == 0:
            return
            
        channel_height = h // num_channels
        
        for idx, channel in enumerate(self.channels):
            data = self.channel_data.get(channel, [])
            if not data:
                continue
            
            color = CHANNEL_COLORS.get(channel, "#ffffff")
            base_y = idx * channel_height + channel_height // 2
            
            # Draw waveform
            points = []
            step_x = w / (len(data) - 1) if len(data) > 1 else w
            
            for i, value in enumerate(data):
                x = i * step_x
                y = base_y - value * (channel_height // 2 - 5)
                points.extend([x, y])
            
            if len(points) >= 4:
                self.create_line(
                    points,
                    fill=color,
                    width=1.5,
                    smooth=True
                )
            
            # Channel label on the left
            self.create_text(
                5, idx * channel_height + 10,
                text=channel,
                fill=color,
                font=("Arial", 8, "bold"),
                anchor="w"
            )
            
            # Separator line
            if idx < num_channels - 1:
                self.create_line(
                    0, (idx + 1) * channel_height,
                    w, (idx + 1) * channel_height,
                    fill="#2a2a4a"
                )


class VolumeVisualizerPanel(ttk.Frame):
    """Complete volume visualizer panel with VU meters and controls."""
    
    def __init__(self, parent, layout: str = "5.1", **kwargs):
        super().__init__(parent, **kwargs)
        
        self.layout = layout
        self.channels = self._get_channels(layout)
        
        # Volume controls
        self.volume_controls: Dict[str, ChannelVolumeControl] = {}
        self.vu_meters: Dict[str, VUMeter] = {}
        self.levels: Dict[str, float] = {ch: 0.0 for ch in self.channels}
        
        # Simulation running flag
        self.simulating = False
        self.sim_thread: Optional[threading.Thread] = None
        
        self._create_widgets()
    
    def _get_channels(self, layout: str) -> List[str]:
        """Get channel list for layout."""
        if layout == "7.1":
            return ["FL", "FR", "FC", "LFE", "SL", "SR", "BL", "BR"]
        return ["FL", "FR", "FC", "LFE", "BL", "BR"]
    
    def _create_widgets(self):
        """Create all widgets."""
        # Main layout
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left side: VU Meters
        vu_frame = ttk.LabelFrame(main_frame, text="Channel Levels", padding="5")
        vu_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        
        vu_container = ttk.Frame(vu_frame)
        vu_container.pack(fill=tk.BOTH, expand=True)
        
        for idx, channel in enumerate(self.channels):
            color = CHANNEL_COLORS.get(channel, "#ffffff")
            
            vu = VUMeter(
                vu_container,
                channel=channel,
                color=color,
                width=30,
                height=150
            )
            vu.pack(side=tk.LEFT, padx=2)
            self.vu_meters[channel] = vu
        
        # Center: Visualizer
        viz_frame = ttk.LabelFrame(main_frame, text="Waveform", padding="5")
        viz_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        self.visualizer = SoundVisualizer(
            viz_frame,
            channels=self.channels,
            width=350,
            height=200
        )
        self.visualizer.pack(fill=tk.BOTH, expand=True)
        
        # Right side: Volume controls
        ctrl_frame = ttk.LabelFrame(main_frame, text="Volume Controls", padding="5")
        ctrl_frame.pack(side=tk.RIGHT, fill=tk.Y)
        
        for channel in self.channels:
            color = CHANNEL_COLORS.get(channel, "#ffffff")
            vol = ChannelVolumeControl(
                ctrl_frame,
                channel=channel,
                color=color,
                initial_volume=1.0,
                on_change=self._on_volume_change
            )
            vol.pack(fill=tk.X, pady=2)
            self.volume_controls[channel] = vol
        
        # Master volume
        ttk.Separator(ctrl_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)
        
        master_frame = ttk.Frame(ctrl_frame)
        master_frame.pack(fill=tk.X)
        
        ttk.Label(master_frame, text="Master", width=6).pack(side=tk.LEFT)
        self.master_volume = tk.DoubleVar(value=100)
        ttk.Scale(
            master_frame,
            from_=0, to=100,
            variable=self.master_volume,
            orient=tk.HORIZONTAL,
            length=120,
            command=self._on_master_change
        ).pack(side=tk.LEFT)
        
        # Control buttons
        btn_frame = ttk.Frame(ctrl_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(btn_frame, text="▶ Simulate", command=self.start_simulation).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="⏹ Stop", command=self.stop_simulation).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Reset", command=self.reset_volumes).pack(side=tk.LEFT, padx=(5, 0))
    
    def _on_volume_change(self, channel: str, volume: float):
        """Handle individual channel volume change."""
        pass  # Can be extended to update filters
    
    def _on_master_change(self, value):
        """Handle master volume change."""
        master = float(value) / 100.0
        for channel, control in self.volume_controls.items():
            # Scale individual volumes
            pass
    
    def set_level(self, channel: str, level: float):
        """Set level for a channel (for external updates)."""
        if channel in self.levels:
            self.levels[channel] = level
            if channel in self.vu_meters:
                self.vu_meters[channel].set_level(level)
            self.visualizer.set_all_levels(self.levels)
    
    def set_all_levels(self, levels: Dict[str, float]):
        """Set levels for all channels."""
        for channel, level in levels.items():
            self.set_level(channel, level)
    
    def reset_volumes(self):
        """Reset all volumes to default."""
        default_vol = DEFAULT_VOLUMES_71 if self.layout == "7.1" else DEFAULT_VOLUMES_51
        for channel, vol in default_vol.items():
            if channel in self.volume_controls:
                self.volume_controls[channel].set_volume(vol)
    
    def start_simulation(self):
        """Start level simulation for testing."""
        if self.simulating:
            return
        
        self.simulating = True
        self.sim_thread = threading.Thread(target=self._simulate_levels, daemon=True)
        self.sim_thread.start()
    
    def stop_simulation(self):
        """Stop level simulation."""
        self.simulating = False
    
    def _simulate_levels(self):
        """Simulate varying levels for testing."""
        phase = {ch: random.uniform(0, 2 * math.pi) for ch in self.channels}
        
        while self.simulating:
            levels = {}
            for channel in self.channels:
                # Generate smooth random levels
                phase[channel] += random.uniform(0.1, 0.3)
                base = 0.3 + 0.3 * math.sin(phase[channel])
                noise = random.uniform(-0.1, 0.1)
                level = max(0.0, min(1.0, base + noise))
                
                # LFE has different behavior (lower frequency content)
                if channel == "LFE":
                    level *= 0.7
                
                levels[channel] = level
            
            # Update on main thread
            try:
                self.after(0, lambda l=levels: self.set_all_levels(l))
            except Exception:
                break
            
            time.sleep(0.05)  # ~20 FPS
    
    def update_layout(self, layout: str):
        """Update to a new channel layout."""
        self.layout = layout
        self.channels = self._get_channels(layout)
        
        # Clear existing widgets
        for widget in self.winfo_children():
            widget.destroy()
        
        # Recreate
        self.volume_controls.clear()
        self.vu_meters.clear()
        self.levels = {ch: 0.0 for ch in self.channels}
        self._create_widgets()
    
    def get_volumes(self) -> Dict[str, float]:
        """Get current volumes for all channels."""
        return {
            channel: control.get_volume()
            for channel, control in self.volume_controls.items()
        }
