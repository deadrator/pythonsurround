#!/usr/bin/env python3
"""
Channel Visualizer GUI Panel
A playable per-channel visualizer for the Atmos Binaural Converter main app.

- Open any audio file (M4A/MP4/MKV/FLAC/WAV/OGG/...) and watch 5.1/7.1/Atmos
  per-channel levels with VU meters and a waveform as the playhead advances.
- Or capture and visualize live system playback (sounddevice WASAPI loopback
  on Windows / PulseAudio monitor on Linux - optional dependency).
"""

import os
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from channel_visualizer import (
    DecodedAudio, SystemCapture, analyze_file, compute_levels, level_to_meter,
    WINDOW_SECONDS
)

try:
    from volume_visualizer import VUMeter, SoundVisualizer, CHANNEL_COLORS
except ImportError:  # pragma: no cover
    VUMeter = SoundVisualizer = None
    CHANNEL_COLORS = {}

try:
    from dark_theme import PALETTE
except ImportError:  # pragma: no cover
    PALETTE = {}


def _c(name: str, default: str) -> str:
    return PALETTE.get(name, default)

TICK_MS = 33          # GUI update interval (~30 fps)
LOOP_SPIN_MS = 30     # worker loop sleep


class ChannelVisualizerPanel(ttk.Frame):
    """Visualizer panel: file playback + system capture."""

    def __init__(self, parent):
        super().__init__(parent, padding="10")
        self.audio = None
        self.pos = 0
        self.playing = False
        self.stop_event = threading.Event()
        self.worker = None
        self.capture = None
        self.updates = queue.Queue()
        self.channel_names: list = []
        self.window_samples = int(WINDOW_SECONDS * 48000)
        self._alive = True

        self._create_widgets()
        self.after(TICK_MS, self._poll)
        self.bind("<Destroy>", self._on_destroy)

    # ---------------- UI ----------------
    def _create_widgets(self):
        top = ttk.Frame(self)
        top.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(top, text="📂 Open Audio", command=self.open_file).pack(side=tk.LEFT, padx=(0, 6))
        self.file_label = ttk.Label(top, text="No file loaded", foreground=_c("muted", "gray"))
        self.file_label.pack(side=tk.LEFT, padx=(0, 10))
        self.capture_btn = ttk.Button(top, text="🎙 System Audio", command=self.toggle_capture)
        self.capture_btn.pack(side=tk.RIGHT)
        self.info_label = ttk.Label(top, text="", foreground=_c("muted", "gray"))
        self.info_label.pack(side=tk.RIGHT, padx=(0, 10))

        transport = ttk.Frame(self)
        transport.pack(fill=tk.X, pady=(0, 6))
        self.play_btn = ttk.Button(transport, text="▶ Play", command=self.play, state=tk.DISABLED)
        self.play_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.stop_btn = ttk.Button(transport, text="⏹ Stop", command=self.stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.time_label = ttk.Label(transport, text="0:00 / 0:00")
        self.time_label.pack(side=tk.LEFT, padx=(0, 8))
        self.seek_var = tk.DoubleVar(value=0)
        self.seek = ttk.Scale(transport, from_=0, to=1000, variable=self.seek_var,
                              command=self._on_seek)
        self.seek.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.hint_label = ttk.Label(self, text="Open an audio file to visualize its channels, or capture system audio.",
                                    foreground=_c("muted", "gray"), font=("Segoe UI", 9))
        self.hint_label.pack(anchor=tk.W, pady=(0, 4))

        self.meter_frame = ttk.LabelFrame(self, text="Channel Levels (VU)", padding="6")
        self.meter_frame.pack(fill=tk.X, pady=(0, 6))
        self.empty_meters = ttk.Label(self.meter_frame, text="—", foreground=_c("muted", "gray"))
        self.empty_meters.pack(pady=10)

        self.viz_frame = ttk.LabelFrame(self, text="Waveform", padding="6")
        self.viz_frame.pack(fill=tk.BOTH, expand=True)
        self.empty_viz = ttk.Label(self.viz_frame, text="Load a file to see per-channel waveforms",
                                   foreground=_c("muted", "gray"))
        self.empty_viz.pack(pady=30)

    # ---------------- File loading ----------------
    def open_file(self):
        f = filedialog.askopenfilename(
            title="Select Audio",
            filetypes=[("Audio", "*.m4a *.mp4 *.mkv *.mka *.mp3 *.flac *.wav *.aac *.ogg *.opus "
                               "*.ac3 *.eac3 *.ac4 *.thd *.dts"),
                       ("All", "*.*")])
        if f:
            self.load_file(f)

    def load_file(self, path):
        self.stop_all()
        try:
            info = analyze_file(path)
            audio = DecodedAudio(path, channel_names=info["channel_names"])
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load audio:\n{e}")
            return

        self.audio = audio
        self.channel_names = audio.channel_names
        self.window_samples = int(WINDOW_SECONDS * audio.sample_rate)
        self.pos = 0
        self.playing = False

        self.file_label.config(text=os.path.basename(path))
        self.info_label.config(
            text=f"{info['format']} • {audio.sample_rate // 1000}.{audio.sample_rate % 1000:03d} kHz • "
                 f"{audio.channels}ch {audio.channel_layout}")
        dur = audio.duration
        self.seek.config(state=tk.NORMAL)
        self.seek_var.set(0)
        self.play_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.NORMAL)
        self.time_label.config(text=f"0:00 / {self._fmt(dur)}")

        self._rebuild_visuals()

    def _rebuild_visuals(self):
        for w in self.meter_frame.winfo_children():
            w.destroy()
        for w in self.viz_frame.winfo_children():
            w.destroy()
        if VUMeter is None or SoundVisualizer is None:
            ttk.Label(self.meter_frame, text="volume_visualizer module unavailable").pack()
            return

        meter_row = ttk.Frame(self.meter_frame)
        meter_row.pack(fill=tk.X)
        self.meters = {}
        for name in self.channel_names:
            color = CHANNEL_COLORS.get(name, _c("front", "#4a9eff"))
            vu = VUMeter(meter_row, channel=name, color=color, width=34, height=170)
            vu.pack(side=tk.LEFT, padx=3)
            self.meters[name] = vu
        ttk.Label(meter_row, text="← rears/left side        front        right side/rears →",
                  foreground=_c("muted", "gray")).pack(side=tk.LEFT, padx=(10, 0))

        self.visualizer = SoundVisualizer(self.viz_frame, channels=self.channel_names,
                                          width=640, height=240)
        self.visualizer.pack(fill=tk.BOTH, expand=True)

    # ---------------- Transport ----------------
    def play(self):
        if not self.audio:
            return
        if self.playing:
            self.playing = False
            self.play_btn.config(text="▶ Play")
            return
        self.playing = True
        self.play_btn.config(text="⏸ Pause")
        if self.worker is None or not self.worker.is_alive():
            # Fresh event for the new worker; any still-exiting old worker
            # holds the previous (set) event and will stop on its own.
            self.stop_event = threading.Event()
            self.worker = threading.Thread(target=self._worker, daemon=True)
            self.worker.start()

    def stop(self):
        self.stop_event.set()
        self.playing = False
        self.pos = 0
        self.worker = None
        self.seek_var.set(0)
        self.play_btn.config(text="▶ Play")
        self.time_label.config(text=f"0:00 / {self._fmt(self.audio.duration) if self.audio else '0:00'}")

    def _on_seek(self, value):
        if self.audio:
            self.pos = int(float(value) / 1000.0 * self.audio.total_samples)

    def _worker(self):
        # Capture the event this worker was started with, so a newer worker
        # (fresh event) can never be mistaken for this one.
        evt = self.stop_event
        last = time.time()
        while not evt.is_set():
            if self.playing and self.audio:
                now = time.time()
                self.pos += int((now - last) * self.audio.sample_rate)
                last = now
                if self.pos >= self.audio.total_samples:
                    self.pos = 0
                    self.playing = False
                    self.updates.put(("eof",))
                block = self.audio.get_block(self.pos, self.window_samples)
                rms, peak = compute_levels(block)
                self.updates.put(("levels", rms, peak, self.pos))
            time.sleep(LOOP_SPIN_MS / 1000.0)

    # ---------------- System capture ----------------
    def toggle_capture(self):
        if self.capture and self.capture.stream:
            self._stop_capture()
            return
        if not SystemCapture.available():
            messagebox.showinfo("System Capture", SystemCapture.describe())
            return
        self.stop()
        self.capture = SystemCapture(callback=self._capture_cb)
        if self.capture.start():
            self.capture_btn.config(text="⏹ Stop Capture")
            self.file_label.config(text="System audio capture (live)")
            self.info_label.config(text="WASAPI loopback / monitor")
            self.info_label.config(foreground=_c("ok", "gray"))
            self.channel_names = self.capture.channel_names
            self._rebuild_visuals()
        else:
            self.capture = None
            messagebox.showerror("System Capture",
                                 "Could not start capture.\n" + SystemCapture.describe())

    def _capture_cb(self, rms, names):
        self.updates.put(("capture", rms, names))

    def _stop_capture(self):
        if self.capture:
            try:
                self.capture.stop()
            except Exception:
                pass
            self.capture = None
        # Widgets may already be destroyed when this runs during teardown
        try:
            if not self.winfo_exists():
                return
            self.capture_btn.config(text="🎙 System Audio")
            self.file_label.config(text="No file loaded")
            self.info_label.config(text="", foreground=_c("muted", "gray"))
            self.channel_names = []
            self._rebuild_visuals()
        except Exception:
            pass

    # ---------------- Update loop ----------------
    def _poll(self):
        if not self._alive:
            return
        try:
            while True:
                msg = self.updates.get_nowait()
                kind = msg[0]
                if kind == "levels":
                    _, rms, peak, pos = msg
                    self._update_levels(rms, peak)
                    if self.audio:
                        self.seek_var.set(pos / self.audio.total_samples * 1000.0)
                        self.time_label.config(
                            text=f"{self._fmt(pos / self.audio.sample_rate)} / {self._fmt(self.audio.duration)}")
                elif kind == "capture":
                    _, rms, names = msg
                    if names and hasattr(self, "meters"):
                        for i, name in enumerate(names):
                            if name in self.meters and i < len(rms):
                                self.meters[name].set_level(level_to_meter(rms[i]))
                elif kind == "eof":
                    self.playing = False
                    self.play_btn.config(text="▶ Play")
                    self.pos = 0
                    self.seek_var.set(0)
        except queue.Empty:
            pass
        self.after(TICK_MS, self._poll)

    def _update_levels(self, rms, peak):
        if not hasattr(self, "meters"):
            return
        for i, name in enumerate(self.channel_names):
            if name in self.meters and i < len(rms):
                self.meters[name].set_level(level_to_meter(rms[i]))
        if hasattr(self, "visualizer"):
            levels = {n: float(level_to_meter(r)) for n, r in zip(self.channel_names, rms)}
            self.visualizer.set_all_levels(levels)

    # ---------------- Helpers ----------------
    @staticmethod
    def _fmt(seconds):
        seconds = max(0, int(seconds or 0))
        return f"{seconds // 60}:{seconds % 60:02d}"

    def _on_destroy(self, event=None):
        self._alive = False
        try:
            self.stop_all()
        except Exception:
            pass

    def stop_all(self):
        self.stop_event.set()
        self.playing = False
        self.worker = None
        self._stop_capture()
        if self.audio:
            self.audio.cleanup()
            self.audio = None
