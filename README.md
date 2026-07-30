# 🎧 Dolby 5.1 to Binaural Atmos Converter

Convert Dolby 5.1/7.1 surround sound to binaural stereo for TWS earbuds and headphones.

## ✨ Features

- **Binaural Conversion** - Convert 5.1/7.1 surround to stereo for headphones
- **HRTF/SOFA Support** - Personalized Head-Related Transfer Functions
- **3D Head Model Import** - Generate SOFA files from STL/OBJ head scans
- **HeSuVi Integration** - Import/export HeSuVi headphone virtualization profiles
- **Foobar Audio Convolver** - Use Atmos 48kHz/44.1kHz impulse response files
- **Virtual Speaker Shifter** - Drag speakers to adjust positions with distance-based volume
- **Volume Visualizer** - Real-time VU meters and waveform display
- **Multi-Codec Support** - AAC, MP3, FLAC, Opus, Vorbis, WAV
- **Multi-Container Support** - M4A, MP4, MKV, OGG, WebM, FLAC
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
├── codecs.py               # Codec/container config
├── build_exe.bat           # Windows EXE builder
├── build_appimage.sh       # Linux AppImage builder
├── requirements.txt        # Python dependencies
└── impulse_responses/      # Atmos IR files directory
```

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

## 🔧 Technical Details

### Conversion Methods
- **Standard** - ITU-R BS.775 downmix
- **Enhanced** - Downmix with bass boost
- **Spatial** - HRTF-like binaural effect
- **HRTF** - Personalized with SOFA file
- **Custom** - User-defined speaker positions

### Distance-Based Volume
Speakers automatically attenuate volume when moved away from center using inverse distance law.

## 📝 License

MIT License

## 🙏 Credits

- FFmpeg - Audio processing engine
- HeSuVi - Headphone virtualization format
- Foobar2000 - Audio convolver reference
