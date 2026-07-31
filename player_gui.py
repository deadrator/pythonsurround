#!/usr/bin/env python3
"""
Surround Suite - Audio Player Panel
====================================
A real media player that OUTPUTS sound (through your default audio device)
while doubling as a live multichannel visualizer (5.1 / 7.1 / Atmos / any
layout FFmpeg can decode).

Audio output backends:
  * ffplay (default)         - ships with FFmpeg, zero extra dependencies.
                               Handles downmix to your sound card automatically.
  * sounddevice (optional)   - `pip install sounddevice`. Precise block-level
                               playback with per-channel visualization driven
                               by the actual output stream.

Extras:
  * Playlist (next/prev/loop), seek, volume, time display
  * Real-time conversion preview: play the file through the currently
    selected converter method/filter chain (audition the binaural result).
"""

import os
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Dict

import numpy as np

from channel_visualizer import (
    DecodedAudio, analyze_file, compute_levels, level_to_meter,
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

try:
    import sounddevice as sd  # type: ignore
    HAS_SOUNDDEVICE = True
except ImportError:
    sd = None
    HAS_SOUNDDEVICE = False

try:
    from foobar_convolver import downmix_to_stereo
except ImportError:  # pragma: no cover
    def downmix_to_stereo(pcm):
        return pcm[:, :2] if pcm.ndim > 1 and pcm.shape[1] >= 2 else pcm

try:
    from audio_codecs import is_codec_decoder_available as _codec_decoder_available
except ImportError:  # pragma: no cover
    _codec_decoder_available = lambda c: True

AUDIO_EXTENSIONS = (".m4a", ".mp4", ".mkv", ".mka", ".mp3", ".flac", ".wav",
                    ".aac", ".ogg", ".opus", ".ac3", ".eac3", ".ac4", ".thd",
                    ".dts")

TICK_MS = 33
LOOP_SPIN_MS = 30


def _c(name: str, default: str) -> str:
    return PALETTE.get(name, default)


def probe_codec_metadata(file_path: str) -> Dict:
    """
    Probe codec-level metadata with ffprobe.

    Returns a dict with 'codec_name', 'codec_long_name', 'profile',
    'bit_rate' plus any AC-4 / loudness stream tags (dialog normalization,
    DRC, ...) so the player can show them.
    """
    meta = {}
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries",
             "stream=codec_name,codec_long_name,profile,bit_rate:stream_tags",
             "-of", "default=noprint_wrappers=1", file_path],
            capture_output=True, text=True, timeout=20)
        for line in result.stdout.splitlines():
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if not value:
                continue
            if key in ("codec_name", "codec_long_name", "profile", "bit_rate"):
                meta[key] = value
            else:
                kl = key.lower()
                if any(t in kl for t in ("dialog", "drc", "norm", "loud",
                                         "enhanced", "frame", "presentation")):
                    meta[key] = value
    except Exception:
        pass
    return meta


def format_codec_info(meta: Dict) -> str:
    """Pretty-print codec metadata for the player info line."""
    if not meta:
        return ""
    parts = []
    codec = meta.get("codec_name", "").upper()
    if codec:
        profile = meta.get("profile")
        if profile and profile.lower() != "unknown":
            parts.append(f"🎴 {codec} ({profile})")
        else:
            parts.append(f"🎴 {codec}")
    br = meta.get("bit_rate")
    if br:
        try:
            parts.append(f"{int(br) // 1000} kbps")
        except (ValueError, TypeError):
            pass
    extra = []
    for k, v in meta.items():
        if k in ("codec_name", "codec_long_name", "profile", "bit_rate"):
            continue
        extra.append(f"{k.replace('_', ' ').title()}: {v}")
    if extra:
        parts.append(", ".join(extra))
    return " • ".join(parts)


# ============================== output backends ==============================

class _FFplayOutput:
    """Audible output through the system default device using ffplay."""

    def __init__(self):
        self.proc = None

    @staticmethod
    def available() -> bool:
        try:
            r = subprocess.run(["ffplay", "-version"], capture_output=True,
                               text=True, timeout=10)
            return r.returncode == 0
        except Exception:
            return False

    def play(self, path, pos, volume, filter_chain=None):
        self.stop()
        cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
               "-volume", str(max(0, min(100, int(volume * 100))))]
        if filter_chain:
            cmd += ["-af", filter_chain]
        if pos > 0:
            cmd += ["-ss", f"{pos:.3f}"]
        cmd.append(path)
        try:
            kwargs = {}
            if os.name == "nt":
                kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
            self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, **kwargs)
        except Exception:
            self.proc = None

    def stop(self):
        if self.proc is not None:
            try:
                self.proc.terminate()
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None


class _SoundOutput:
    """Precise sounddevice backend: playback and visualization in lockstep."""

    def __init__(self, callback):
        # callback(rms, peak, pos_seconds, finished)
        self.callback = callback
        self.stream = None
        self._stop = False

    def play(self, audio, pos, volume_getter, device_index=None):
        """
        Play `audio` (an existing DecodedAudio) from sample position `pos`
        (in samples). `volume_getter` is a callable returning the current
        volume (0..1), read live so volume changes apply during playback.
        `device_index` selects a specific sounddevice output; None = system
        default.

        NB: the conversion-preview chain is handled by the ffplay backend;
        the sounddevice backend always plays the raw decoded file.
        """
        self.stop()
        if not HAS_SOUNDDEVICE or audio is None:
            return False
        self._stop = False
        self._volume_getter = volume_getter
        self._volume = max(0.0, min(1.0, volume_getter()))
        self._pos = max(0, int(pos))
        self._audio = audio
        self._rate = audio.sample_rate
        self._channels = audio.channels

        # Pick a device that can handle the channel count (downmix otherwise)
        out_channels = self._channels
        try:
            dev = device_index if device_index is not None else sd.default.device[1]
            if dev is not None and dev >= 0:
                info = sd.query_devices(dev)
                max_ch = int(info.get("max_output_channels", 2) or 2)
                if self._channels > max_ch:
                    out_channels = max_ch
        except Exception:
            out_channels = min(2, self._channels)

        self._out_channels = out_channels
        try:
            self.stream = sd.OutputStream(
                samplerate=self._rate, channels=out_channels,
                dtype="float32", callback=self._sd_callback)
            self.stream.start()
            return True
        except Exception:
            self.stop()
            return False

    def _sd_callback(self, outdata, frames, time_info, status):
        if self._stop or self._audio is None:
            outdata.fill(0)
            return
        try:
            vol = self._volume_getter()
            self._volume = max(0.0, min(1.0, vol))
        except Exception:
            pass  # keep last volume if the getter misbehaves
        full = self._audio.get_block(self._pos, frames)
        got = len(full)
        if got < frames:
            pad = np.zeros((frames - got, full.shape[1]), dtype=np.float32)
            full = np.vstack([full, pad])

        # Levels are computed on the FULL source block (all channels) so the
        # meters always reflect every surround channel, even when the output
        # device is stereo and we must downmix.
        try:
            rms, peak = compute_levels(full)
            pos_s = self._pos / self._rate
            finished = self._pos + frames >= self._audio.total_samples
            if finished:
                self._stop = True
            self.callback(rms, peak, pos_s, finished)
        except Exception:
            pass

        # Downmix only what we write to the device
        out = full
        if self._out_channels < full.shape[1]:
            try:
                out = downmix_to_stereo(full)[:, :self._out_channels]
            except Exception:
                out = full[:, :self._out_channels]
        outdata[:] = out * self._volume
        self._pos += frames
        if self._pos >= self._audio.total_samples:
            outdata.fill(0)

    def stop(self):
        self._stop = True
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        # NOTE: we do NOT clean up self._audio here - it is the panel's
        # DecodedAudio instance (owned by the panel), shared across backends.
        self._audio = None

    def is_running(self) -> bool:
        return self.stream is not None


# ============================== main panel ==============================

class MediaPlayerPanel(ttk.Frame):
    """
    Playlist-based audio player with audible output and live multichannel
    VU meters + waveform. Optionally previews the active converter method.
    """

    def __init__(self, parent, get_preview_filter=None, on_pref_change=None):
        super().__init__(parent, padding="10")
        # get_preview_filter(): returns the current ffmpeg filter chain, or
        # None, so "preview" plays the file through the active conversion.
        # on_pref_change(): called when a persisted preference changes
        # (e.g. output device) so the host can save settings immediately.
        self.get_preview_filter = get_preview_filter
        self.on_pref_change = on_pref_change

        self.playlist = []            # list of absolute file paths
        self.current_index = -1
        self.audio = None             # DecodedAudio of the current track
        self.pos = 0                  # playhead in samples
        self.playing = False
        self.paused = False
        self.stop_event = threading.Event()
        self.worker = None
        self.updates = queue.Queue()
        self.channel_names = []
        self.window_samples = int(WINDOW_SECONDS * 48000)
        self.codec_meta: Dict = {}
        self._alive = True

        # Output backend preference: sounddevice is nicer, ffplay always works.
        self.sound_output = _SoundOutput(self._sd_cb) if HAS_SOUNDDEVICE else None
        self.ffplay_output = _FFplayOutput()
        self._ffplay_ok = self.ffplay_output.available()
        self._restart_job = None
        self._filter_job = None
        self._master_volume = 0.8

        # Explicit sounddevice output device (None = system default)
        self._device_index = None
        self._devices = []
        if HAS_SOUNDDEVICE:
            self._devices = self._query_devices()

        self._create_widgets()
        self.after(TICK_MS, self._poll)
        self.bind("<Destroy>", self._on_destroy)

    # ---------------- UI ----------------
    def _create_widgets(self):
        top = ttk.Frame(self)
        top.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(top, text="🎵 Surround Player",
                  font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(top, text="📂 Open Files", command=self.add_files).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(top, text="📁 Folder", command=self.add_folder).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(top, text="🗑 Remove", command=self.remove_selected).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(top, text="Clear", command=self.clear_playlist).pack(side=tk.LEFT)
        self.backend_label = ttk.Label(top, text=self._backend_text(), foreground=_c("muted", "gray"))
        self.backend_label.pack(side=tk.RIGHT)

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True)

        # Left: playlist
        pl = ttk.LabelFrame(body, text="Playlist", padding="6")
        pl.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        self.playlist_box = tk.Listbox(pl, width=34, height=14, font=("Consolas", 9),
                                       selectmode=tk.SINGLE)
        sb = ttk.Scrollbar(pl, orient=tk.VERTICAL, command=self.playlist_box.yview)
        self.playlist_box.configure(yscrollcommand=sb.set,
                                    bg=_c("canvas_bg", "#0a0e17"),
                                    fg=_c("text", "#e8edf6"),
                                    selectbackground=_c("accent", "#4f8cff"),
                                    selectforeground="#ffffff",
                                    highlightbackground=_c("border", "#33415e"),
                                    highlightthickness=1, bd=0, activestyle="none")
        self.playlist_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.playlist_box.bind("<Double-Button-1>", lambda e: self.play_selected())

        # Right: player + visualizer
        right = ttk.Frame(body)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Track info
        self.track_label = ttk.Label(right, text="No track loaded", font=("Segoe UI", 10, "bold"))
        self.track_label.pack(anchor=tk.W, pady=(0, 2))
        self.info_label = ttk.Label(right, text="", foreground=_c("muted", "gray"))
        self.info_label.pack(anchor=tk.W, pady=(0, 2))
        self.codec_label = ttk.Label(right, text="", foreground=_c("muted", "gray"))
        self.codec_label.pack(anchor=tk.W, pady=(0, 4))

        # Transport
        transport = ttk.Frame(right)
        transport.pack(fill=tk.X, pady=(0, 4))
        self.prev_btn = ttk.Button(transport, text="⏮", width=3, command=self.prev_track,
                                   state=tk.DISABLED)
        self.prev_btn.pack(side=tk.LEFT, padx=(0, 3))
        self.play_btn = ttk.Button(transport, text="▶ Play", command=self.toggle_play,
                                   state=tk.DISABLED, style="Accent.TButton")
        self.play_btn.pack(side=tk.LEFT, padx=(0, 3))
        self.next_btn = ttk.Button(transport, text="⏭", width=3, command=self.next_track,
                                   state=tk.DISABLED)
        self.next_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.stop_btn = ttk.Button(transport, text="⏹ Stop", command=self.stop,
                                   state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.time_label = ttk.Label(transport, text="0:00 / 0:00")
        self.time_label.pack(side=tk.LEFT)

        # Seek
        seek_row = ttk.Frame(right)
        seek_row.pack(fill=tk.X, pady=(0, 4))
        self.seek_var = tk.DoubleVar(value=0)
        self.seek = ttk.Scale(seek_row, from_=0, to=1000, variable=self.seek_var,
                              command=self._on_seek)
        self.seek.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.seek.config(state=tk.DISABLED)

        # Volume + options
        opt = ttk.Frame(right)
        opt.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(opt, text="🔊").pack(side=tk.LEFT, padx=(0, 3))
        self.volume_var = tk.DoubleVar(value=80)
        self.volume = ttk.Scale(opt, from_=0, to=100, variable=self.volume_var,
                                orient=tk.HORIZONTAL, length=120,
                                command=self._on_volume)
        self.volume.pack(side=tk.LEFT, padx=(0, 10))
        self.volume_label = ttk.Label(opt, text="80%", width=4)
        self.volume_label.pack(side=tk.LEFT, padx=(0, 10))
        self.loop_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="🔁 Loop", variable=self.loop_var).pack(side=tk.LEFT, padx=(0, 10))
        self.preview_var = tk.BooleanVar(value=False)
        self.preview_chk = ttk.Checkbutton(opt, text="🎧 Preview conversion", variable=self.preview_var,
                                           command=self._on_preview_toggle)
        self.preview_chk.pack(side=tk.LEFT)
        if HAS_SOUNDDEVICE:
            # Output device picker (sounddevice backend)
            self.device_var = tk.StringVar(value=self._current_device_name() or "System default")
            self.device_combo = ttk.Combobox(opt, textvariable=self.device_var,
                                             values=[n for _, n in self._devices] or ["System default"],
                                             state="readonly", width=26,
                                             postcommand=self._refresh_devices)
            self.device_combo.pack(side=tk.LEFT, padx=(10, 0))
            self.device_combo.bind("<<ComboboxSelected>>", self._on_device_change)

        # VU meters
        self.meter_frame = ttk.LabelFrame(right, text="Channel Levels (VU)", padding="6")
        self.meter_frame.pack(fill=tk.X, pady=(0, 6))
        self.empty_meters = ttk.Label(self.meter_frame, text="Load a track to see per-channel levels",
                                      foreground=_c("muted", "gray"))
        self.empty_meters.pack(pady=10)

        # Waveform
        self.viz_frame = ttk.LabelFrame(right, text="Waveform", padding="6")
        self.viz_frame.pack(fill=tk.BOTH, expand=True)
        self.empty_viz = ttk.Label(self.viz_frame, text="Load a track to see per-channel waveforms",
                                   foreground=_c("muted", "gray"))
        self.empty_viz.pack(pady=30)

    def _backend_text(self) -> str:
        if HAS_SOUNDDEVICE:
            name = self._current_device_name()
            return f"🔊 {name}" if name else "🔊 sounddevice (system default)"
        if self._ffplay_ok:
            return "🔊 ffplay (system device)"
        return "⚠ no audio backend (install sounddevice or ffmpeg)"

    def _query_devices(self):
        """List (device_index, label) for all usable output devices."""
        devices = []
        try:
            for i, d in enumerate(sd.query_devices()):
                if int(d.get("max_output_channels", 0) or 0) > 0:
                    devices.append((i, f"{d.get('name', 'Device')} "
                                       f"({d.get('max_output_channels', '?')}ch)"))
        except Exception:
            pass
        return devices

    def _current_device_name(self):
        """Label of the active output device (explicit pick or system default)."""
        if not HAS_SOUNDDEVICE:
            return None
        dev = self._device_index
        if dev is None:
            try:
                dev = sd.default.device[1]
            except Exception:
                return None
        if dev is None or dev < 0:
            return None
        try:
            info = sd.query_devices(dev)
            return f"{info.get('name', 'Device')} ({info.get('max_output_channels', '?')}ch)"
        except Exception:
            return None

    def _refresh_devices(self):
        """Re-query devices when the dropdown opens (hot-plug friendly)."""
        if not HAS_SOUNDDEVICE or not hasattr(self, "device_combo"):
            return
        devices = self._query_devices()
        if devices != self._devices:
            self._devices = devices
            labels = [n for _, n in devices] or ["System default"]
            self.device_combo["values"] = labels
            current = self._current_device_name()
            if current and current in labels:
                self.device_var.set(current)

    def _on_device_change(self, e=None):
        name = self.device_var.get()
        self._device_index = None
        for i, n in self._devices:
            if n == name:
                self._device_index = i
                break
        self.backend_label.config(text=self._backend_text())
        if self.playing:
            self._start_output()  # restart playback on the new device
        if self.on_pref_change:
            try:
                self.on_pref_change()
            except Exception:
                pass

    # ---------------- preferences ----------------
    def save_prefs(self) -> Dict:
        """Return persistable player preferences (device by name, volume)."""
        return {
            "player_device": self._current_device_name() or "",
            "player_volume": self._master_volume,
        }

    def restore_prefs(self, prefs: Dict):
        """Restore a persisted device + volume, falling back gracefully."""
        try:
            name = prefs.get("player_device", "")
            if name and HAS_SOUNDDEVICE:
                for i, n in self._devices:
                    if n == name:
                        self._device_index = i
                        break
                else:
                    # older settings may have stored a raw index
                    try:
                        idx = int(name)
                        if idx in {i for i, _ in self._devices}:
                            self._device_index = idx
                    except (TypeError, ValueError):
                        pass
                if hasattr(self, "device_combo"):
                    cur = self._current_device_name()
                    if cur:
                        self.device_var.set(cur)
            vol = float(prefs.get("player_volume", self._master_volume))
            vol = max(0.0, min(1.0, vol))
            self._master_volume = vol
            self.volume_var.set(round(vol * 100))
            self.volume_label.config(text=f"{round(vol * 100)}%")
        except Exception:
            pass
        self.backend_label.config(text=self._backend_text())

    # ---------------- playlist ----------------
    def add_files(self):
        files = filedialog.askopenfilenames(
            title="Select Audio",
            filetypes=[("Audio", "*.m4a *.mp4 *.mkv *.mka *.mp3 *.flac *.wav *.aac *.ogg *.opus "
                              "*.ac3 *.eac3 *.ac4 *.thd *.dts"),
                       ("All", "*.*")])
        added = False
        for f in files:
            if f not in self.playlist:
                self.playlist.append(f)
                self.playlist_box.insert(tk.END, os.path.basename(f))
                added = True
        if added:
            self._update_nav_state()
            if self.current_index == -1:
                self.load_track(0)

    def add_folder(self):
        folder = filedialog.askdirectory(title="Select Folder")
        if not folder:
            return
        added = False
        for p in sorted(os.scandir(folder), key=lambda e: e.name.lower()):
            if p.is_file() and os.path.splitext(p.name)[1].lower() in AUDIO_EXTENSIONS:
                if p.path not in self.playlist:
                    self.playlist.append(p.path)
                    self.playlist_box.insert(tk.END, p.name)
                    added = True
        if added:
            self._update_nav_state()
            if self.current_index == -1:
                self.load_track(0)

    def remove_selected(self):
        sel = self.playlist_box.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx == self.current_index:
            self.stop()
        self.playlist.pop(idx)
        self.playlist_box.delete(idx)
        if self.current_index >= len(self.playlist):
            self.current_index = len(self.playlist) - 1
        self._update_nav_state()
        self._update_track_label()

    def clear_playlist(self):
        self.stop()
        self.playlist.clear()
        self.playlist_box.delete(0, tk.END)
        self.current_index = -1
        self._update_nav_state()
        self._update_track_label()

    def play_selected(self):
        sel = self.playlist_box.curselection()
        if sel:
            self.load_track(sel[0])

    def _update_nav_state(self):
        state = tk.NORMAL if self.playlist else tk.DISABLED
        self.play_btn.config(state=state)
        self.stop_btn.config(state=state)
        self.prev_btn.config(state=state)
        self.next_btn.config(state=state)

    # ---------------- track loading ----------------
    def load_track(self, index):
        if not 0 <= index < len(self.playlist):
            return
        self.stop()
        path = self.playlist[index]
        self.current_index = index
        self.playlist_box.selection_clear(0, tk.END)
        self.playlist_box.selection_set(index)
        self.playlist_box.see(index)
        # Some codecs (e.g. Dolby AC-4) have no decoder in this FFmpeg build:
        # they can only be REMUXED via the Converter's passthrough method,
        # never played or decoded. Catch it before the raw ffmpeg error.
        self.codec_meta = probe_codec_metadata(path)
        codec = (self.codec_meta.get("codec_name") or "").lower()
        if codec and _codec_decoder_available(codec) is False:
            self.audio = None
            self.channel_names = []
            label = "AC-4 (Dolby)" if codec == "ac4" else codec
            messagebox.showerror(
                "Cannot Play This File",
                f"This FFmpeg build has no decoder for {label} audio, so the file\n"
                "can't be played or decoded.\n\n"
                "Such streams can only be REMUXED with the Converter's\n"
                "'Passthrough (Stream Copy)' method - they can't be converted\n"
                "to another format either.")
            self._update_track_label()
            return
        try:
            info = analyze_file(path)
            self.audio = DecodedAudio(path, channel_names=info["channel_names"])
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load audio:\n{e}")
            self.audio = None
            return
        self.channel_names = self.audio.channel_names
        self.window_samples = int(WINDOW_SECONDS * self.audio.sample_rate)
        self.pos = 0
        self.playing = False
        self.paused = False
        self._rebuild_visuals()
        self.seek.config(state=tk.NORMAL)
        self.seek_var.set(0)
        self._update_track_label()
        self.time_label.config(text=f"0:00 / {self._fmt(self.audio.duration)}")
        self._update_nav_state()

    def _update_track_label(self):
        if 0 <= self.current_index < len(self.playlist):
            self.track_label.config(text=os.path.basename(self.playlist[self.current_index]))
            if self.audio:
                self.info_label.config(
                    text=f"{self.audio.channels}ch {self.audio.channel_layout} • "
                         f"{self.audio.sample_rate // 1000}.{self.audio.sample_rate % 1000:03d} kHz • "
                         f"{self.audio.channel_names}")
                self.codec_label.config(text=format_codec_info(self.codec_meta))
            else:
                self.info_label.config(text="")
                self.codec_label.config(text="")
        else:
            self.track_label.config(text="No track loaded")
            self.info_label.config(text="")
            self.codec_label.config(text="")

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
            color = CHANNEL_COLORS.get(name, _c("front", "#4f8cff"))
            vu = VUMeter(meter_row, channel=name, color=color, width=30, height=160)
            vu.pack(side=tk.LEFT, padx=3)
            self.meters[name] = vu
        ttk.Label(meter_row, text="← rears / sides        front        rears / sides →",
                  foreground=_c("muted", "gray")).pack(side=tk.LEFT, padx=(10, 0))
        self.visualizer = SoundVisualizer(self.viz_frame, channels=self.channel_names,
                                          width=480, height=200)
        self.visualizer.pack(fill=tk.BOTH, expand=True)

    # ---------------- transport ----------------
    def toggle_play(self):
        if self.playing:
            self.pause()
        else:
            self.play()

    def play(self):
        if not self.audio:
            return
        if self.paused:
            self.paused = False
        self.playing = True
        self.play_btn.config(text="⏸ Pause")
        sd_active = self._start_output()
        if not sd_active:
            # ffplay backend: drive the playhead from the wall clock
            self._ensure_worker()

    def pause(self):
        self.playing = False
        self.paused = True
        self.play_btn.config(text="▶ Resume")
        self._stop_output()

    def stop(self):
        self.playing = False
        self.paused = False
        self.stop_event.set()
        if getattr(self, "_filter_job", None) is not None:
            try:
                self.after_cancel(self._filter_job)
            except Exception:
                pass
            self._filter_job = None
        self._stop_output()
        if self.worker is not None:
            self.worker = None
        self.pos = 0
        self.seek_var.set(0)
        self.play_btn.config(text="▶ Play")
        if self.audio:
            self.time_label.config(text=f"0:00 / {self._fmt(self.audio.duration)}")

    def next_track(self):
        if not self.playlist:
            return
        self.load_track((self.current_index + 1) % len(self.playlist))
        self.play()

    def prev_track(self):
        if not self.playlist:
            return
        self.load_track((self.current_index - 1) % len(self.playlist))
        self.play()

    def _on_seek(self, value):
        if not self.audio:
            return
        self.pos = int(float(value) / 1000.0 * self.audio.total_samples)
        self.time_label.config(text=f"{self._fmt(self.pos / self.audio.sample_rate)} / "
                                    f"{self._fmt(self.audio.duration)}")
        if not self.playing:
            return
        if HAS_SOUNDDEVICE and self.sound_output is not None \
                and self.sound_output.is_running():
            self._start_output()  # restart precise backend at the new position
        elif self.ffplay_output.is_running():
            self._schedule_restart()  # ffplay needs a restart to seek

    def _on_volume(self, value):
        vol = float(value)
        self._master_volume = vol / 100.0
        self.volume_label.config(text=f"{int(vol)}%")
        if self.playing and self.ffplay_output.is_running():
            # ffplay needs a restart to change volume - debounced while dragging
            self._schedule_restart()

    def _on_preview_toggle(self):
        if self.playing:
            # Switch backends cleanly: _start_output stops the current one and
            # picks sounddevice-vs-ffplay based on the preview chain.
            sd_active = self._start_output()
            if not sd_active:
                # ffplay backend: keep the wall-clock playhead driving
                self._ensure_worker()

    def _get_volume(self):
        """Plain-float volume getter (safe to call from audio threads)."""
        return self._master_volume

    # ---------------- live filter changes ----------------
    def on_filter_changed(self):
        """
        Called when the active conversion filter chain may have changed while
        playing (e.g. the user dragged a speaker in the Speaker Shifter tab).

        Turns the conversion preview on (if it was off, since the filter is
        only audible through preview) and restarts the output so the new
        filter is heard immediately.
        """
        if not self.playing or not self.audio:
            return
        if not self.preview_var.get():
            self.preview_var.set(True)
        self._schedule_filter_restart()

    def _schedule_filter_restart(self):
        """Debounce filter restarts so dragging a speaker doesn't spawn a
        stream of ffplay processes."""
        if getattr(self, "_filter_job", None) is not None:
            try:
                self.after_cancel(self._filter_job)
            except Exception:
                pass
        self._filter_job = self.after(180, self._restart_output)

    def _restart_output(self):
        """Restart the active backend so a newly-changed filter chain is used."""
        self._filter_job = None
        if not self.playing or not self.audio:
            return
        sd_active = self._start_output()
        if not sd_active:
            self._ensure_worker()

    def _ensure_worker(self):
        """Start the wall-clock playhead worker if it isn't running (ffplay mode)."""
        if self.worker is None or not self.worker.is_alive():
            self.stop_event = threading.Event()
            self.worker = threading.Thread(target=self._worker, daemon=True)
            self.worker.start()

    # ---------------- output management ----------------
    def _preview_chain(self):
        if not self.preview_var.get() or not self.get_preview_filter:
            return None
        try:
            chain = self.get_preview_filter()
            chain = chain if isinstance(chain, str) and chain else None
        except Exception:
            return None
        if chain is None:
            return None
        # The speaker-shifter / surround pan filters need a real multichannel
        # source - feeding them a stereo file makes ffmpeg's pan filter error
        # out (c2/c4/... don't exist in a 2ch layout). Play stereo files raw,
        # except the surround upmix filters, which are designed for stereo.
        if self.audio is not None and self.audio.channels <= 2:
            if "surround=" not in chain:
                return None
        # A custom 5.1/7.1 pan chain references up to c5/c7 - a quad (4ch) or
        # 5.0 file would make ffmpeg error out too. Only surround= (upmix)
        # chains are safe on sources with fewer than 6 channels.
        if self.audio is not None and self.audio.channels < 6:
            if "pan=" in chain:
                return None
        return chain

    def _start_output(self):
        self._stop_output()
        if not self.audio:
            return False
        path = self.playlist[self.current_index]
        vol = self.volume_var.get() / 100.0
        chain = self._preview_chain()
        pos_s = self.pos / self.audio.sample_rate
        if not self._ffplay_ok and not (HAS_SOUNDDEVICE and chain is None):
            # No audible backend available - nothing to do, still visualize
            return False
        # sounddevice backend (raw playback, no preview chain)
        if HAS_SOUNDDEVICE and chain is None:
            ok = self.sound_output.play(self.audio, self.pos,
                                        self._get_volume,
                                        device_index=self._device_index)
            if ok:
                return True
        # ffplay backend (handles preview chain + downmix)
        self.ffplay_output.play(path, pos_s, vol, filter_chain=chain)
        return False

    def _restart_ffplay(self):
        if not self.playing or not self.audio:
            return
        path = self.playlist[self.current_index]
        vol = self.volume_var.get() / 100.0
        chain = self._preview_chain()
        pos_s = self.pos / self.audio.sample_rate
        self.ffplay_output.play(path, pos_s, vol, filter_chain=chain)

    def _schedule_restart(self):
        """Debounce ffplay restarts so dragging the seek/volume doesn't spawn
        a stream of processes."""
        if hasattr(self, "_restart_job") and self._restart_job is not None:
            try:
                self.after_cancel(self._restart_job)
            except Exception:
                pass
        self._restart_job = self.after(180, self._restart_ffplay)

    def _stop_output(self):
        if HAS_SOUNDDEVICE and self.sound_output is not None:
            self.sound_output.stop()
        self.ffplay_output.stop()

    # ---------------- worker (wall-clock playhead, ffplay backend) ----------------
    def _sd_cb(self, rms, peak, pos_s, finished):
        self.updates.put(("levels", rms, peak, pos_s, finished))

    def _worker(self):
        evt = self.stop_event
        last = time.time()
        while not evt.is_set():
            now = time.time()
            # Always refresh 'last' so a pause doesn't cause a big jump on resume
            if self.playing and self.audio:
                self.pos += int((now - last) * self.audio.sample_rate)
                if self.pos >= self.audio.total_samples:
                    self.pos = self.audio.total_samples
                    self.updates.put(("eof",))
                block = self.audio.get_block(self.pos, self.window_samples)
                rms, peak = compute_levels(block)
                self.updates.put(("levels", rms, peak, self.pos / self.audio.sample_rate, False))
            last = now
            time.sleep(LOOP_SPIN_MS / 1000.0)

    # ---------------- UI update loop ----------------
    def _poll(self):
        if not self._alive:
            return
        try:
            while True:
                msg = self.updates.get_nowait()
                kind = msg[0]
                if kind == "levels":
                    _, rms, peak, pos_s, finished = msg
                    self._update_levels(rms, peak)
                    if self.audio:
                        self.pos = int(pos_s * self.audio.sample_rate)
                        self.seek_var.set(pos_s / self.audio.duration * 1000.0)
                        self.time_label.config(text=f"{self._fmt(pos_s)} / "
                                                    f"{self._fmt(self.audio.duration)}")
                    if finished:
                        self._on_track_end()
                elif kind == "eof":
                    self._on_track_end()
        except queue.Empty:
            pass
        self.after(TICK_MS, self._poll)

    def _on_track_end(self):
        self.playing = False
        self._stop_output()
        if self.loop_var.get():
            self.next_track()
        elif self.current_index < len(self.playlist) - 1:
            self.next_track()
        else:
            self.pos = 0
            self.seek_var.set(0)
            self.play_btn.config(text="▶ Play")
            self.time_label.config(text=f"0:00 / {self._fmt(self.audio.duration) if self.audio else '0:00'}")

    def _update_levels(self, rms, peak):
        if not hasattr(self, "meters"):
            return
        for i, name in enumerate(self.channel_names):
            if name in self.meters and i < len(rms):
                self.meters[name].set_level(level_to_meter(rms[i]))
        if hasattr(self, "visualizer"):
            levels = {n: float(level_to_meter(r)) for n, r in zip(self.channel_names, rms)}
            self.visualizer.set_all_levels(levels)

    # ---------------- helpers ----------------
    @staticmethod
    def _fmt(seconds):
        seconds = max(0, int(seconds or 0))
        return f"{seconds // 60}:{seconds % 60:02d}"

    def stop_all(self):
        self.playing = False
        self.stop_event.set()
        self.worker = None
        if getattr(self, "_filter_job", None) is not None:
            try:
                self.after_cancel(self._filter_job)
            except Exception:
                pass
            self._filter_job = None
        self._stop_output()
        if self.audio:
            try:
                self.audio.cleanup()
            except Exception:
                pass
            self.audio = None

    def _on_destroy(self, event=None):
        self._alive = False
        try:
            self.stop_all()
        except Exception:
            pass
