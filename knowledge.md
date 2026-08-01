# Project knowledge

This file gives Freebuff context about your project: goals, commands, conventions, and gotchas.

## What this is

A surround-sound → binaural converter ("Dolby 5.1/7.1 → Binaural Atmos Converter") for TWS earbuds/headphones, with **two codebases**:

- **Desktop (Python)** — Tkinter GUI (`gui_app.py`) + CLI (`convert_atmos.py`). All DSP is shelled out to FFmpeg via `subprocess`; `numpy`/`scipy` for IR generation/convolution and HRTF work.
- **Android (Kotlin)** — native port in `android/` using Jetpack Compose + Material 3 + the maintained `dev.ffmpegkit-maintained:ffmpeg-kit-full` fork (drop-in `com.arthenica` API). The original `com.arthenica:ffmpeg-kit` was retired in 2025 and its binaries pulled from Maven Central.

## Quickstart (Python desktop)
- Setup: `pip install -r requirements.txt` (requires **Python 3.8+** and **FFmpeg in PATH**)
- Run GUI: `python gui_app.py` (tabs: Converter · Speaker Shifter · Atmos IR · 🎵 Player · Visualizer)
- Run CLI: `python convert_atmos.py input.m4a` (add `--quality ultra --method spatial`; batch: `--batch /path/to/music`)
- Surround suite CLI: `--method upmix51|upmix71|downmix51|passthrough` + `--codec`/`--container`
- Visualizer CLI: `python visualize_audio.py song.m4a` (add `--snapshot`, `--speed N`, or `--system` for live capture)
- Build: Windows EXE `build_exe.bat` (PyInstaller) · Linux `./build_appimage.sh`
- Test/Lint: none configured (no test suite, no linter/formatter)

## Quickstart (Android)
- Requires JDK 17 + Android SDK (compileSdk 35, minSdk 26, targetSdk 35)
- Build debug APK: `cd android && ./gradlew :app:assembleDebug` (on Linux/macOS use `./gradlew`, on Windows `./gradlew.bat`)
- APK output: `android/app/build/outputs/apk/debug/app-debug.apk`; install via `adb install -r <apk>`
- CI: `.github/workflows/build-android-apk.yml` builds on push to the `android` branch and on `workflow_dispatch`; uploads the APK artifact and publishes a **GitHub Release** tagged `beta_preview_v<version>_<arch>` (arch choice x64/x32, version from `versionName` in `app/build.gradle.kts` or a manual input; skips if the tag already exists)
- Versions (pinned in `android/gradle/libs.versions.toml`): AGP 8.7.3, Kotlin 2.0.21, Compose BOM 2024.12.01 (UI 1.7.6, material3 1.3.1), navigation-compose 2.8.5, coroutines 1.9.0, `dev.ffmpegkit-maintained:ffmpeg-kit-full:8.1.7`

## Architecture (Python)
- `gui_app.py` — Tkinter GUI: Converter tab, Virtual Speaker Shifter tab (drag-able `SpeakerCanvas` ring with distance-based volume), Atmos IR Convolver & HeSuVi tab, Visualizer tab. Main class `AtmosConverterGUI`; supports a dark theme via `dark_theme.py`.
- `convert_atmos.py` — CLI entry point. Wraps FFmpeg `-af pan=stereo` downmix filter chains (`FILTER_PRESETS`: standard/enhanced/spatial) + optional `sofalizer` HRTF via SOFA file, and stereo-convolver IR mode (`--export-ir`, `--convolve`).
- `audio_codecs.py` — codec/container/preset registry used for FFmpeg encode args (named `audio_codecs`, NOT `codecs`, because Python loads the stdlib `codecs` at interpreter startup and a local `codecs.py` would silently never import). Includes AC-4/TrueHD/DTS/ALAC codecs, ac4/dts raw containers, and `is_codec_encoder_available()` (probes `ffmpeg -encoders`; AC-4 is usually decode-only).
- `player_gui.py` — `MediaPlayerPanel`: real audio player (ffplay backend by default, sounddevice for precise playback) with playlist, multichannel VU meters + waveform, and real-time conversion preview via `get_preview_filter`. Includes an output-device picker (sounddevice), codec/AC-4 metadata line (`probe_codec_metadata` → dialog normalization/DRC tags via ffprobe), a clear "no decoder" error when loading undecodable codecs (e.g. AC-4), and `save_prefs()`/`restore_prefs()` for persisting the selected device + volume in the app settings file.
- `speaker_shifter.py` — speaker position/angle/distance model (`SpeakerConfig`), distance → volume attenuation.
- `hrtf_generator.py` / `head_model_parser.py` — HRTF/SOFA generation, STL/OBJ head-scan measurement extraction.
- `hesuvi_support.py` — HeSuVi profile import/export (WAV format).
- `foobar_convolver.py` — exports/applies 44/48kHz stereo IR pairs for foobar2000 Stereo Convolver (`impulse_responses/stereo/`). Contains the reusable `downmix_to_stereo` helper.
- `volume_visualizer.py` — `VUMeter` + `SoundVisualizer` Tk canvases.
- `visualizer_gui.py` / `visualize_audio.py` — GUI panel + TUI CLI channel-level visualizer; optional WASAPI/PulseAudio capture via `sounddevice`.
- `dark_theme.py` — shared `PALETTE` dict (keys: bg, canvas_bg, surface3, border, text, muted, ok, err, warn, front, rear, side, lfe, head) + `apply_dark_theme()` / `style_listbox()`.
- `channel_visualizer.py` — non-GUI channel split/analysis used by the visualizer.
- Data files: `default_51.sofa` / `default_71.sofa` (fallback HRTFs), `impulse_responses/` (user IR WAVs).

## Architecture (Android) — `android/app/src/main/java/com/deadrator/atmosconverter/`
- `MainActivity.kt` — Compose app shell: `AtmosTheme` + bottom `NavigationBar` with 4 tabs (Converter, Speaker Shifter, Player, Visualizer); a shared `SpeakerConfig` is remembered at app level so Converter's "Custom Speaker Layout" method uses what the Speaker Shifter tab edits.
- `engine/FfmpegEngine.kt` — FFmpegKit wrapper: `executeAsync` with return-code + statistics callbacks (real 0..100 progress from `stats.time`), filter-chain builder per method, `convert()` guard that only applies `-af` for multichannel input or upmix methods, plus `copyToCache` (content:// → cache file) and `saveOutput` (external Music dir).
- `engine/AudioProbe.kt` — FFprobeKit wrapper producing `AudioMeta` (codec, channels, sample rate, duration, bitrate). **Written against the maintained fork's API** (see gotchas below); uses `getMediaInformationAsync` with a session callback + `invokeOnCancellation`, and parses `DURATION-*` tags via the JSONObject when `duration` is absent.
- `dsp/SpeakerConfig.kt`, `dsp/SpeakerFilterGenerator.kt` — speaker layout/positions + pan-filter generation (port of `speaker_shifter.py`).
- `dsp/CodecRegistry.kt`, `dsp/FilterPresets.kt` — codec/container/preset registry + filter chain strings (ports of `audio_codecs.py` / `convert_atmos.py` filters).
- `ui/ConverterScreen.kt`, `ui/SpeakerShifterScreen.kt`, `ui/PlayerScreen.kt`, `ui/VisualizerScreen.kt` — the four tabs; `ui/theme/Theme.kt` — dark palette.
- Assets: `default_51.sofa` / `default_71.sofa` bundled under `src/main/assets/` for HRTF fallbacks.
- `app/build.gradle.kts` — `packaging { jniLibs { useLegacyPackaging = false } }` keeps FFmpegKit's `.so` files uncompressed (required for 16 KB page alignment on Android 15/16).

## Conventions
- **Optional-import pattern is required (Python):** every GUI/feature module must import optional deps inside `try/except ImportError` with graceful fallbacks (e.g. `ChannelVisualizerPanel`, `PALETTE`, `HRTFGenerator`) so the app never crashes without them.
- **Dark theme:** use `PALETTE.get(key, default)` for any hardcoded color instead of literal hex strings; keep default fallbacks so standalone module use still works.
- Styling uses `Segoe UI` fonts; UI strings use emoji icons (🎧 🔄 🔊 🎛️ etc.) and ✓/✗/→ glyphs.
- Paths use `Path`/`os.path`; keep Windows+Linux portability (build scripts for both exist).
- CLI prints to stdout with `stream.reconfigure(errors="replace")` at entry to avoid Unicode crashes on cp1252 Windows.

## Gotchas
- **FFmpeg is required (Python)** — the CLI exits with an install hint if `ffmpeg`/`ffprobe` aren't in PATH; most conversion logic is FFmpeg filter strings.
- **AC-4**: stock FFmpeg builds (incl. this 8.1.1 gyan.dev build) have NO AC-4 **decoder** and no encoder — `ffmpeg -codecs` shows ac4 with `..A.L.` (no D/E flags), so AC-4 is demux/mux-only. It can only be **remuxed** via `--method passthrough`; it can't be played or re-encoded. `is_codec_encoder_available()` / `is_codec_decoder_available()` probe at runtime and the GUI/CLI/player warn clearly when a codec isn't decodable.
- **Player (Python)**: `sounddevice` (now installed, v0.5.5) enables precise block-level playback + downmix to the device's channel count; without it, playback falls back to `ffplay` (ships with FFmpeg). The `downmix_to_stereo` helper from `foobar_convolver` is reused for device downmix. Note: `pip install` on a fresh machine is required — it's uncommented in requirements.txt.
- Optional deps are commented out in `requirements.txt` (soundfile, sounddevice, pyinstaller) — install explicitly when needed, don't assume they're present.
- `downmix51` requires 7.1 (8-channel) input; upmix methods apply the filter even to stereo input. Passthrough auto-picks a container from the input codec when none is given.
- `impulse_responses/` holds user-provided IR WAVs; the directory must exist / be populated for convolver modes (defaults under `impulse_responses/stereo/`).
- SOFA default files (`default_51.sofa`, `default_71.sofa`) are referenced as fallbacks; Windows path escaping for `sofalizer` (`:`, `\`) is handled in `convert_atmos.py`.
- **ffmpeg-kit maintained fork renames the API** (Android): `StreamInformation` uses `getCodec()`/`getCodecLong()`/`getType()`/`getBitrate()` — NOT `getCodecName()`/`getCodecLongName()`/`getCodecType()`/`getBitRate()`; `tags` is an `org.json.JSONObject` (not a Map), and arbitrary stream fields come from `getStringProperty(key)` / `getNumberProperty(key)` (Long). There is no `FFprobeKit.getMediaInformation(path, callback)` overload — use `getMediaInformationAsync(path) { session -> session.mediaInformation }`. Do not "fix" AudioProbe.kt back to the old names; it was rewritten against the verified 8.1.7 bytecode.
- **Player "Preview conversion" is hardcoded to the Enhanced chain** (Android) — it does not reflect the active Converter method/speaker layout; wiring it up is a known next step.
- **Compose `nativeCanvas` needs an import** (Android): `Canvas.nativeCanvas` is a top-level extension in `androidx.compose.ui.graphics` (not a member of the `Canvas` interface), so any file using `drawContext.canvas.nativeCanvas` must `import androidx.compose.ui.graphics.nativeCanvas` or it fails with "Unresolved reference 'nativeCanvas'" — this was a real CI failure.
- **GitHub Actions Kotlin daemon flakiness**: `android/gradle.properties` sets `kotlin.daemon.jvmargs=-Xmx3072m` to avoid "The daemon has terminated unexpectedly" compile noise on the 7 GB runner. If it recurs, fallback is `kotlin.compiler.execution.strategy=in-process`.
- **Release publishing**: the workflow skips creating a release when the tag already exists (`gh release view` guard) — bump `versionName` in `app/build.gradle.kts` (or pass the version input) to republish. The ffmpeg-kit AAR ships only 64-bit ABIs (arm64-v8a, x86_64), so the x32 release name is a label, not a true 32-bit build.
- **No automated tests** (either codebase) — validate changes by building (`./gradlew :app:assembleDebug`) and running the CLI/GUI against a real audio file.
