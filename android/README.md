# Atmos Binaural Converter — Android (Kotlin)

Native Android port of the desktop Atmos Binaural Converter, built with
**Kotlin + Jetpack Compose + Material 3** and the maintained
[`dev.ffmpegkit-maintained:ffmpeg-kit-full`](https://github.com/ffmpegkit/ffmpeg-kit)
fork (drop-in `com.arthenica` API, prebuilt 16 KB-page-aligned `.so` libraries
on Maven Central — required for Android 15/16).

The original `com.arthenica:ffmpeg-kit` was retired in 2025 and its binaries
were pulled; this port uses the community-maintained replacement.

## Features

A deliberately simple 3-tab app:

- **🎧 Converter** — pick any surround file (M4A/MP4/MKV/AC3/E-AC-3/AC-4/
  TrueHD/DTS/FLAC/WAV/OGG), choose method / preset / codec / container / bitrate,
  convert to binaural stereo, share the result.
  Methods: Standard, Enhanced (Bass Boost), Spatial Binaural, HRTF (SOFA),
  Custom Speaker Layout, Surround Upmix 5.1/7.1, Downmix 7.1→5.1, Passthrough.
- **🔊 Speaker Shifter** — drag speakers on a ring (rotates them; drag in/out
  for NEAR/FAR distance-based volume), angle sliders, presets, and a live
  preview of the generated pan filter (feeds the Converter's Custom method).
- **🎵 AC3 Music Player** — playlist, play/pause/seek, per-channel VU meters,
  and waveform. Plays AC3/E-AC-3/DTS/TrueHD by transcoding through FFmpeg
  when the platform MediaPlayer can't decode them.

## Requirements

- Android Studio (Ladybug or newer), JDK 17
- minSdk 26, targetSdk 35

## Build

```bash
# From the repo root (or open android/ in Android Studio)
cd android
./gradlew :app:assembleDebug
```

The APK lands in `android/app/build/outputs/apk/debug/app-debug.apk`.
Install it with `adb install -r app/build/outputs/apk/debug/app-debug.apk`.

> The first Gradle sync downloads the ~100 MB FFmpeg artifact from Maven
> Central. On Android 15/16 devices the `.so` libraries must stay
> uncompressed — this is handled via `useLegacyPackaging = false` in
> `app/build.gradle.kts`.

## Architecture

| Desktop (Python)          | Android (Kotlin)                                          |
|---------------------------|-----------------------------------------------------------|
| `gui_app.py` / `convert_atmos.py` | `ui/*` screens + `engine/FfmpegEngine.kt`         |
| `speaker_shifter.py`      | `dsp/SpeakerConfig.kt`, `dsp/SpeakerFilterGenerator.kt`   |
| `audio_codecs.py`         | `dsp/CodecRegistry.kt`                                    |
| `dark_theme.py`           | `ui/theme/Theme.kt` (dark palette)                        |
| ffmpeg subprocess         | FFmpegKit (maintained fork)                               |
| `default_51/71.sofa`      | bundled in `src/main/assets/` (HRTF fallbacks)            |

## Notes & limitations

- **AC-4**: stock FFmpeg has no AC-4 decoder/encoder — AC-4 files can only be
  *remuxed* via the Passthrough method, exactly like the desktop app.
- **Preview conversion** in the Player currently uses the Enhanced chain;
  wiring it to the active Converter method + speaker layout is a natural next
  step.
- **Full parity**: share/save uses the app's external Music dir + FileProvider.
- **Scope**: the Android app intentionally has just the 3 tabs above (the
  desktop app has more, e.g. a channel Visualizer). A system-wide "make every
  app sound Atmos" service is NOT feasible on Android without root — there is
  no public API to reprocess other apps' audio output.
