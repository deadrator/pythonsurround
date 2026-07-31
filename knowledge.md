# Project knowledge

This file gives Freebuff context about your project: goals, commands, conventions, and gotchas.

## What this is

A Python audio tool ("Dolby 5.1/7.1 → Binaural Atmos Converter") that converts surround-sound audio to binaural stereo for TWS earbuds/headphones. Has a Tkinter GUI (`gui_app.py`) and a CLI (`convert_atmos.py`). All DSP is shelled out to FFmpeg via `subprocess`; `numpy`/`scipy` are used for IR generation/convolution and HRTF work.

## Quickstart
- Setup: `pip install -r requirements.txt` (requires **Python 3.8+** and **FFmpeg in PATH**)
- Run GUI: `python gui_app.py` (tabs: Converter · Speaker Shifter · Atmos IR · 🎵 Player · Visualizer)
- Run CLI: `python convert_atmos.py input.m4a` (add `--quality ultra --method spatial`; batch: `--batch /path/to/music`)
- Surround suite CLI: `--method upmix51|upmix71|downmix51|passthrough` + `--codec`/`--container`
- Visualizer CLI: `python visualize_audio.py song.m4a` (add `--snapshot`, `--speed N`, or `--system` for live capture)
- Build: Windows EXE `build_exe.bat` (PyInstaller) · Linux `./build_appimage.sh`
- Test/Lint: none configured (no test suite, no linter/formatter)

## Architecture
- `gui_app.py` — Tkinter GUI: Converter tab, Virtual Speaker Shifter tab (drag-able `SpeakerCanvas` ring with distance-based volume), Atmos IR Convolver & HeSuVi tab, Visualizer tab. Main class `AtmosConverterGUI`; supports a dark theme via `dark_theme.py`.
- `convert_atmos.py` — CLI entry point. Wraps FFmpeg `-af pan=stereo` downmix filter chains (`FILTER_PRESETS`: standard/enhanced/spatial) + optional `sofalizer` HRTF via SOFA file, and stereo-convolver IR mode (`--export-ir`, `--convolve`).
- `audio_codecs.py` — codec/container/preset registry used for FFmpeg encode args (named `audio_codecs`, NOT `codecs`, because Python loads the stdlib `codecs` at interpreter startup and a local `codecs.py` would silently never import). Includes AC-4/TrueHD/DTS/ALAC codecs, ac4/dts raw containers, and `is_codec_encoder_available()` (probes `ffmpeg -encoders`; AC-4 is usually decode-only).
- `player_gui.py` — `MediaPlayerPanel`: real audio player (ffplay backend by default, sounddevice for precise playback) with playlist, multichannel VU meters + waveform, and real-time conversion preview via `get_preview_filter`. Includes an output-device picker (sounddevice), codec/AC-4 metadata line (`probe_codec_metadata` → dialog normalization/DRC tags via ffprobe), a clear "no decoder" error when loading undecodable codecs (e.g. AC-4), and `save_prefs()`/`restore_prefs()` for persisting the selected device + volume in the app settings file.
- `speaker_shifter.py` — speaker position/angle/distance model (`SpeakerConfig`), distance → volume attenuation.
- `hrtf_generator.py` / `head_model_parser.py` — HRTF/SOFA generation, STL/OBJ head-scan measurement extraction.
- `hesuvi_support.py` — HeSuVi profile import/export (WAV format).
- `foobar_convolver.py` — exports/applies 44/48kHz stereo IR pairs for foobar2000 Stereo Convolver (`impulse_responses/stereo/`).
- `volume_visualizer.py` — `VUMeter` + `SoundVisualizer` Tk canvases.
- `visualizer_gui.py` / `visualize_audio.py` — GUI panel + TUI CLI channel-level visualizer; optional WASAPI/PulseAudio capture via `sounddevice`.
- `dark_theme.py` — shared `PALETTE` dict (keys: bg, canvas_bg, surface3, border, text, muted, ok, err, warn, front, rear, side, lfe, head) + `apply_dark_theme()` / `style_listbox()`.
- `channel_visualizer.py` — non-GUI channel split/analysis used by the visualizer.
- Data files: `default_51.sofa` / `default_71.sofa` (fallback HRTFs), `impulse_responses/` (user IR WAVs).

## Conventions
- **Optional-import pattern is required:** every GUI/feature module must import optional deps inside `try/except ImportError` with graceful fallbacks (e.g. `ChannelVisualizerPanel`, `PALETTE`, `HRTFGenerator`) so the app never crashes without them.
- **Dark theme:** use `PALETTE.get(key, default)` for any hardcoded color instead of literal hex strings; keep default fallbacks so standalone module use still works.
- Styling uses `Segoe UI` fonts; UI strings use emoji icons (🎧 🔄 🔊 🎛️ etc.) and ✓/✗/→ glyphs.
- Paths use `Path`/`os.path`; keep Windows+Linux portability (build scripts for both exist).
- CLI prints to stdout with `stream.reconfigure(errors="replace")` at entry to avoid Unicode crashes on cp1252 Windows.

## Gotchas
- **FFmpeg is required** — the CLI exits with an install hint if `ffmpeg`/`ffprobe` aren't in PATH; most conversion logic is FFmpeg filter strings.
- **AC-4**: stock FFmpeg builds (incl. this 8.1.1 gyan.dev build) have NO AC-4 **decoder** and no encoder — `ffmpeg -codecs` shows ac4 with `..A.L.` (no D/E flags), so AC-4 is demux/mux-only. It can only be **remuxed** via `--method passthrough`; it can't be played or re-encoded. `is_codec_encoder_available()` / `is_codec_decoder_available()` probe at runtime and the GUI/CLI/player warn clearly when a codec isn't decodable.
- **Player**: `sounddevice` (now installed, v0.5.5) enables precise block-level playback + downmix to the device's channel count; without it, playback falls back to `ffplay` (ships with FFmpeg). The `downmix_to_stereo` helper from `foobar_convolver` is reused for device downmix. Note: `pip install` on a fresh machine is required — it's uncommented in requirements.txt.
- Optional deps are commented out in `requirements.txt` (soundfile, sounddevice, pyinstaller) — install explicitly when needed, don't assume they're present.
- `downmix51` requires 7.1 (8-channel) input; upmix methods apply the filter even to stereo input. Passthrough auto-picks a container from the input codec when none is given.
- `impulse_responses/` holds user-provided IR WAVs; the directory must exist / be populated for convolver modes (defaults under `impulse_responses/stereo/`).
- SOFA default files (`default_51.sofa`, `default_71.sofa`) are referenced as fallbacks; Windows path escaping for `sofalizer` (`:`, `\`) is handled in `convert_atmos.py`.
- No automated tests — validate changes by running the CLI/GUI against a real audio file.
