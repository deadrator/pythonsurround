# 🎧 Dolby 5.1 to Binaural Atmos Converter

Convert Dolby 5.1/7.1 surround sound to binaural stereo for TWS earbuds and headphones.

## ✨ Features

- **Binaural Conversion** - Convert 5.1/7.1 surround to stereo for headphones
- **HRTF/SOFA Support** - Personalized Head-Related Transfer Functions
- **3D Head Model Import** - Generate SOFA files from STL/OBJ head scans
- **HeSuVi Integration** - Import/export HeSuVi headphone virtualization profiles
- **Foobar Audio Convolver** - Use Atmos 48kHz/44.1kHz impulse response files
- **Stereo Convolver IR Workflow** - Export 44/48kHz L/R impulse responses or convert with Equalizer APO / HeSuVi exports (foobar2000 style)
- **Virtual Speaker Shifter** - Drag speakers to adjust positions with distance-based volume
- **Volume Visualizer** - Real-time VU meters and waveform display
- **Channel Visualizer** - Play any file and watch 5.1/7.1/Atmos per-channel levels (GUI tab + TUI CLI), or capture live system audio
- **Multi-Codec Support** - AAC, MP3, FLAC, Opus, Vorbis, WAV, AC3, E-AC-3, AC-4, TrueHD, DTS, ALAC
- **Multi-Container Support** - M4A, MP4, MKV, MKA, OGG, WebM, FLAC, WAV, AC-4, DTS
- **AC-4 Support** - Remux/stream-copy Dolby AC-4 (Atmos) files (stock FFmpeg builds ship no AC-4 decoder, so AC-4 is passthrough-only here)
- **Surround Suite Methods** - Stereo→5.1/7.1 upmix, 7.1→5.1 downmix, stream-copy passthrough
- **🎵 Media Player** - Play audio aloud (ffplay or sounddevice) with live multichannel VU meters, waveform, playlist & real-time conversion preview
- **Batch Processing** - Convert multiple files at once
- **Cross-Platform** - Windows (EXE), Linux (AppImage), macOS

## 📦 Installation

### Requirements
- **Python 3.8+**
- **FFmpeg** in PATH

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Windows EXE
```cmd
build_exe.bat
```

### Linux AppImage
```bash
chmod +x build_appimage.sh
./build_appimage.sh
```

## 🚀 Usage

### GUI Application
```bash
python gui_app.py
```

The GUI now includes a **🎵 Player** tab: load a playlist, play with sound output
(ffplay by default, or `pip install sounddevice` for precise block-level
playback), and watch per-channel VU meters + waveforms. Enable
**"Preview conversion"** to audition the currently selected conversion method
in real time before exporting.

### Surround Suite (CLI)
```bash
# Stereo -> 5.1 upmix
python convert_atmos.py stereo.m4a --method upmix51 --codec aac --container m4a

# Stereo -> 7.1 upmix
python convert_atmos.py stereo.m4a --method upmix71 --codec eac3 --container mkv

# 7.1 -> 5.1 downmix
python convert_atmos.py movie71.mkv --method downmix51 --codec eac3 --container mkv

# AC-4 / TrueHD / DTS passthrough (stream copy, no re-encode)
python convert_atmos.py atmos.ac4 --method passthrough --container ac4
python convert_atmos.py truehd.mkv --method passthrough --container mkv

# Lossless TrueHD encode
python convert_atmos.py input.m4a --codec truehd --container mkv
```

## 📊 Channel Visualizer

Visualize per-channel audio levels (5.1 / 7.1 / Atmos / any layout) for any
file FFmpeg can decode (M4A, MP4, MKV, FLAC, WAV, OGG, ...), or capture and
visualize live system playback.

### GUI
Open the **Visualizer** tab in the main app, click "Open Audio", pick a song,
then Play/Pause/Seek while watching the per-channel VU meters and waveforms.

### TUI / CLI
```bash
# Live per-channel visualization (playhead follows the song)
python visualize_audio.py song.m4a

# Static ASCII level chart (great for scripting)
python visualize_audio.py song.flac --snapshot

# Accelerated scanning
python visualize_audio.py song.mkv --speed 10

# Live system playback capture (needs sounddevice)
python visualize_audio.py --system
```

System capture uses the optional `sounddevice` package:
`pip install sounddevice` (WASAPI loopback on Windows, PulseAudio monitor on Linux).

### Command Line
```bash
# Basic conversion
python convert_atmos.py input.m4a

# With specific quality and method
python convert_atmos.py input.m4a --quality ultra --method spatial

# Batch convert all M4A files
python convert_atmos.py --batch /path/to/music

# With HRTF SOFA file
python convert_atmos.py input.m4a --method hrtf --sofa my_hrtf.sofa

# Custom codec and container
python convert_atmos.py input.m4a --codec flac --container flac
```

## 🔊 HeSuVi Support

### Import HeSuVi Profiles
1. Open GUI → Converter tab
2. Click "Import SOFA" button
3. Select your SOFA file
4. Profile appears in HeSuVi dropdown

### Export to HeSuVi
1. Open GUI → Speaker Shifter tab
2. Adjust speaker positions
3. Export creates WAV files in HeSuVi format

### Foobar Audio Convolver
- Supports Atmos impulse response files (48kHz/44.1kHz)
- Place IR files in the `impulse_responses/` directory
- Select from the IR dropdown in the GUI

## 🎯 Personalized HRTF

### From 3D Head Model
1. Get your head scan as STL or OBJ file
2. Open GUI → Speaker Shifter tab
3. Click "Import 3D Model"
4. System extracts measurements automatically

### Manual Measurements
Enter these measurements for best results:
- **Head circumference** (54-62 cm typical)
- **Ear-to-ear distance** (15-20 cm typical)
- **Head width** (14-18 cm typical)

## 📁 File Structure

```
audio-atmos-converter/
├── gui_app.py              # GUI application
├── convert_atmos.py        # CLI conversion tool
├── speaker_shifter.py      # Virtual speaker positioning
├── hrtf_generator.py       # HRTF/SOFA generation
├── head_model_parser.py    # 3D STL/OBJ parsing
├── hesuvi_support.py       # HeSuVi format support
├── volume_visualizer.py    # VU meters and waveform
├── audio_codecs.py         # Codec/container config (NOT the Python stdlib codecs)
├── build_exe.bat           # Windows EXE builder
├── build_appimage.sh       # Linux AppImage builder
├── requirements.txt        # Python dependencies
└── impulse_responses/      # Atmos IR files directory
```

## 🎯 Stereo Convolver IR Workflow (Equalizer APO / HeSuVi style)

Instead of applying filter chains to every file, you can capture your processing
once as **impulse responses** and then apply it with fast convolution:

1. **Export IR files** (GUI: Atmos IR tab → "Export IR Files", or CLI):
   ```bash
   python convert_atmos.py --export-ir MyProfile --method spatial
   ```
   This runs a stereo dirac delta through the selected processing and creates
   four files in `impulse_responses/stereo/`:
   ```
   MyProfile_44_left.wav   MyProfile_44_right.wav
   MyProfile_48_left.wav   MyProfile_48_right.wav
   ```
   These contain all of the processing for stereo content and work with
   foobar2000's **Stereo Convolver** component (`foo_dsp_stereoconv.dll`).

2. **Convert with IR pairs** (GUI: "Stereo Convolver (IR)" method, or CLI):
   ```bash
   python convert_atmos.py input.m4a --convolve MyProfile
   ```
   The 44 kHz pair is used for 44.1 kHz content, the 48 kHz pair otherwise
   (audio is resampled to match). 5.1/7.1 input is downmixed to stereo first.

You can also import IR pairs exported from **HeSuVi/Equalizer APO** (the
`*_44_left/right.wav`, `*_48_left/right.wav` benchmark files) via the GUI
"Import Pair" button, or place them in `impulse_responses/stereo/`.

## 🎚️ Supported Formats

### Input
- M4A, MP4, MKV, MP3, FLAC, WAV, AAC, OGG
- Dolby 5.1, 7.1, and Atmos

### Output
| Format | Container | Quality |
|--------|-----------|---------|
| AAC | M4A/MP4 | Lossy |
| MP3 | MP3 | Lossy |
| FLAC | FLAC | Lossless |
| Opus | OGG/WebM | Lossy |
| Vorbis | OGG | Lossy |
| PCM | WAV | Lossless |
| AC-4 | AC4/MP4/MKV | Lossy (Atmos) |
| TrueHD | MKV | Lossless |
| DTS | DTS/MKV | Lossy |
| ALAC | M4A/MKV | Lossless |

## 🔧 Technical Details

### Conversion Methods
- **Standard** - ITU-R BS.775 downmix
- **Enhanced** - Downmix with bass boost
- **Spatial** - HRTF-like binaural effect
- **HRTF** - Personalized with SOFA file
- **Custom** - User-defined speaker positions
- **Upmix 5.1 / 7.1** - Surround upmix from stereo with FFmpeg's `surround` filter
- **Downmix 7.1→5.1** - Fold side channels into rears
- **Passthrough** - Stream copy / remux (AC-4, TrueHD, DTS, ...)

### Distance-Based Volume
Speakers automatically attenuate volume when moved away from center using inverse distance law.

## 📝 License

MIT License

## 🙏 Credits

- FFmpeg - Audio processing engine
- HeSuVi - Headphone virtualization format
- Foobar2000 - Audio convolver reference
