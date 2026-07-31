#!/usr/bin/env python3
"""
Dolby 5.1 to Binaural Atmos Converter
Converts surround sound to stereo binaural for TWS earbuds/headphones

Requirements:
    - Python 3.6+
    - FFmpeg in PATH

Usage:
    python convert_atmos.py input.m4a
    python convert_atmos.py input.m4a -o output.m4a
    python convert_atmos.py input.m4a --quality ultra --method spatial
    python convert_atmos.py --batch /path/to/folder
"""

import argparse
import os
import subprocess
import sys
import glob
import time
from pathlib import Path
from typing import Optional, Tuple, Dict, List

# Import codec support
try:
    from codecs import (
        CODECS, CONTAINERS, PRESETS,
        get_codec, get_container, get_compatible_containers,
        get_ffmpeg_encode_args, get_output_args, get_preset
    )
except ImportError:
    # Fallback if codecs module not available
    CODECS = {}
    CONTAINERS = {}
    PRESETS = {}
    get_codec = lambda x: None
    get_container = lambda x: None
    get_compatible_containers = lambda x: []
    get_ffmpeg_encode_args = lambda c, b=None, s=48000: ["-c:a", "aac", "-b:a", b or "256k", "-ar", str(s)]
    get_output_args = lambda c: ["-f", "ipod", "-movflags", "+faststart"]
    get_preset = lambda x: None

# Import HRTF support
try:
    from hrtf_generator import HRTFGenerator, SofaFileReader
except ImportError:
    HRTFGenerator = None
    SofaFileReader = None

# Import stereo convolver IR support
try:
    from foobar_convolver import (
        export_stereo_irs, resolve_stereo_ir_pair, apply_stereo_convolution,
        STEREO_IR_DIR
    )
except ImportError:
    export_stereo_irs = resolve_stereo_ir_pair = None
    apply_stereo_convolution = None
    STEREO_IR_DIR = None

# Quality presets
QUALITY_PRESETS = {
    "low": "128k",
    "medium": "192k",
    "high": "256k",
    "ultra": "320k"
}

# Filter presets
FILTER_PRESETS = {
    "standard": {
        "name": "Standard Downmix",
        "filter": (
            "aresample=48000,"
            "pan=stereo|c0=c0+0.707*c2|c1=c1+0.707*c2"
        )
    },
    "enhanced": {
        "name": "Enhanced with Bass",
        "filter": (
            "aresample=48000,"
            "pan=stereo|c0=c0+0.634*c2+0.447*c4|c1=c1+0.634*c2+0.447*c5,"
            "anequalizer=c0 f=80 w=200 g=4 t=1|c1 f=80 w=200 g=4 t=1,"
            "equalizer=f=2500:t=q:w=1:g=2,"
            "equalizer=f=8000:t=q:w=1:g=1"
        )
    },
    "spatial": {
        "name": "Spatial Binaural",
        "filter": (
            "aresample=48000,"
            "aformat=channel_layouts=5.1,"
            "pan=stereo|"
            "c0=0.87*c0+0.63*c2+0.45*c4+0.25*c5|"
            "c1=0.87*c1+0.63*c2+0.45*c5+0.25*c4,"
            "anequalizer=c0 f=60 w=150 g=5 t=1|c1 f=60 w=150 g=5 t=1,"
            "equalizer=f=2000:t=q:w=1.5:g=3,"
            "equalizer=f=6000:t=q:w=1:g=2,"
            "equalizer=f=10000:t=q:w=1:g=1.5,"
            "volume=0.95"
        )
    }
}


def check_ffmpeg() -> bool:
    """Check if FFmpeg is available in PATH."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def get_audio_info(file_path: str) -> Optional[str]:
    """Get audio stream information from file."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-i", file_path],
            capture_output=True,
            text=True
        )
        # FFmpeg outputs media info to stderr
        output = result.stderr or result.stdout
        for line in output.split("\n"):
            if "Audio:" in line:
                return line.strip()
    except Exception:
        pass
    return None


def get_channel_count(file_path: str) -> int:
    """Get the number of audio channels in the file."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=channels",
             "-of", "csv=p=0", file_path],
            capture_output=True,
            text=True
        )
        channels = int(result.stdout.strip())
        return channels
    except (ValueError, Exception):
        return 2  # Default to stereo if detection fails


def convert_to_binaural(
    input_file: str,
    output_file: str,
    quality: str = "high",
    method: str = "enhanced",
    codec: str = "aac",
    container: str = "m4a",
    sofa_file: Optional[str] = None,
    ir_base: Optional[str] = None,
    ir_dir: Optional[str] = None
) -> bool:
    """
    Convert multi-channel audio to binaural stereo.
    
    Args:
        input_file: Path to input audio file
        output_file: Path to output file
        quality: Output quality (low/medium/high/ultra)
        method: Conversion method (standard/enhanced/spatial/hrtf)
        codec: Output codec name
        container: Output container name
        sofa_file: Path to SOFA file for HRTF processing
        ir_base: Stereo convolver IR pair base name ({name}_44_left.wav etc.)
        ir_dir: Directory containing the IR pair
    
    Returns:
        True if successful, False otherwise
    """
    bitrate = QUALITY_PRESETS.get(quality, "256k")
    
    # Stereo convolver IR mode (44/48 kHz L/R impulse responses)
    if ir_base:
        if not apply_stereo_convolution or not resolve_stereo_ir_pair:
            print("  ✗ foobar_convolver/scipy module not available")
            return False
        ir_dir = ir_dir or (str(STEREO_IR_DIR) if STEREO_IR_DIR else "impulse_responses/stereo")
        pairs = resolve_stereo_ir_pair(ir_base, ir_dir)
        if not pairs:
            print(f"  ✗ IR pair '{ir_base}' not found in {ir_dir}")
            print(f"    Expected files like {ir_base}_44_left.wav / {ir_base}_48_right.wav")
            return False
        codec_args = get_ffmpeg_encode_args(codec, bitrate, 48000)
        output_args = get_output_args(container)
        print(f"\n  Method:   Stereo Convolver (IR pair: {ir_base})")
        print(f"  IR Dir:   {ir_dir}")
        print(f"  Rates:    {', '.join(str(r) for r in sorted(pairs))}")
        print(f"\n  Converting...")
        ok = apply_stereo_convolution(input_file, output_file, pairs, 48000,
                                      codec_args, output_args)
        if ok:
            input_size = os.path.getsize(input_file) / (1024 * 1024)
            output_size = os.path.getsize(output_file) / (1024 * 1024)
            print(f"\n  ✓ Conversion successful!")
            print(f"  Size: {input_size:.1f}MB → {output_size:.1f}MB")
        return ok
    
    # Get filter based on method
    if method == "hrtf" and sofa_file:
        # Use SOFA-based HRTF processing - escape path for FFmpeg
        escaped_path = sofa_file.replace("\\", "/").replace(":", "\\:")
        filter_str = f"sofalizer=sofa='{escaped_path}':radius=1.0"
        method_name = f"HRTF (SOFA: {Path(sofa_file).stem})"
    elif method in FILTER_PRESETS:
        filter_str = FILTER_PRESETS[method]["filter"]
        method_name = FILTER_PRESETS[method]["name"]
    else:
        filter_str = FILTER_PRESETS["enhanced"]["filter"]
        method_name = "Enhanced"
    
    # Get codec and container info
    codec_obj = get_codec(codec)
    container_obj = get_container(container)
    
    codec_name = codec_obj.name if codec_obj else codec.upper()
    container_name = container_obj.name if container_obj else container.upper()
    
    print(f"\n{'='*60}")
    print(f"  Input:    {input_file}")
    print(f"  Output:   {output_file}")
    print(f"  Method:   {method_name}")
    print(f"  Codec:    {codec_name}")
    print(f"  Container:{container_name}")
    print(f"  Quality:  {quality} ({bitrate})")
    if sofa_file:
        print(f"  SOFA:     {sofa_file}")
    print(f"{'='*60}\n")
    
    # Get input info
    audio_info = get_audio_info(input_file)
    channels = get_channel_count(input_file)
    if audio_info:
        print(f"  Input Info: {audio_info}")
    print(f"  Channels: {channels}")
    
    # Skip downmix if already stereo or mono
    if channels <= 2:
        print(f"\n  ✓ Already stereo/mono - re-encoding...")
        encode_args = get_ffmpeg_encode_args(codec, bitrate, 48000)
        output_args = get_output_args(container)
        try:
            result = subprocess.run(
                ["ffmpeg", "-i", input_file] + encode_args + output_args + ["-y", output_file],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                print(f"  ✓ Re-encoding successful!")
                return True
            else:
                print(f"  ✗ Re-encoding failed")
                return False
        except Exception as e:
            print(f"  ✗ Error: {e}")
            return False
    
    # Build FFmpeg command (only apply downmix if >2 channels)
    encode_args = get_ffmpeg_encode_args(codec, bitrate, 48000)
    output_args = get_output_args(container)
    
    if channels > 2:
        cmd = ["ffmpeg", "-i", input_file, "-af", filter_str] + encode_args + output_args + ["-y", output_file]
    else:
        cmd = ["ffmpeg", "-i", input_file] + encode_args + output_args + ["-y", output_file]
    
    print(f"\n  Converting...")
    start_time = time.time()
    
    try:
        # Run FFmpeg
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        
        elapsed = time.time() - start_time
        
        if result.returncode == 0:
            print(f"\n  ✓ Conversion successful! ({elapsed:.1f}s)")
            
            # Show output info
            output_info = get_audio_info(output_file)
            if output_info:
                print(f"  Output: {output_info}")
            
            # Show file sizes
            input_size = os.path.getsize(input_file) / (1024 * 1024)
            output_size = os.path.getsize(output_file) / (1024 * 1024)
            print(f"  Size: {input_size:.1f}MB → {output_size:.1f}MB")
            
            return True
        else:
            print(f"\n  ✗ Conversion failed!")
            if result.stderr:
                # Extract error message
                for line in result.stderr.split("\n"):
                    if "error" in line.lower():
                        print(f"    {line.strip()}")
            return False
            
    except Exception as e:
        print(f"\n  ✗ Error: {e}")
        return False


def process_batch(
    input_dir: str,
    quality: str = "high",
    method: str = "enhanced",
    ir_base: Optional[str] = None,
    ir_dir: Optional[str] = None
) -> Tuple[int, int]:
    """
    Process all M4A files in a directory.
    
    Returns:
        Tuple of (success_count, failure_count)
    """
    # Find all M4A files
    pattern = os.path.join(input_dir, "*.m4a")
    files = glob.glob(pattern)
    
    if not files:
        print(f"\n  No M4A files found in {input_dir}")
        return 0, 0
    
    print(f"\n  Found {len(files)} M4A files to process")
    
    success = 0
    failed = 0
    
    for file_path in files:
        # Generate output filename
        base_name = os.path.splitext(file_path)[0]
        output_file = f"{base_name}_binaural.m4a"
        
        if convert_to_binaural(file_path, output_file, quality, method,
                               ir_base=ir_base, ir_dir=ir_dir):
            success += 1
        else:
            failed += 1
    
    return success, failed


def main():
    """Main entry point."""
    # Ensure Unicode output (✓/✗/→) never crashes the CLI when stdout/stderr
    # is a pipe with a non-UTF-8 encoding (e.g. cp1252 on Windows).
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except Exception:
                pass
    
    parser = argparse.ArgumentParser(
        description="Convert Dolby 5.1 to Binaural Atmos for TWS earbuds",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s input.m4a                          # Basic conversion
  %(prog)s input.m4a -o output.m4a            # Custom output name
  %(prog)s input.m4a --quality ultra           # Maximum quality
  %(prog)s input.m4a --method spatial          # Best spatial effect
  %(prog)s --batch /path/to/music              # Convert all M4A files
        """
    )
    
    parser.add_argument(
        "input",
        nargs="?",
        help="Input M4A file path"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file path (auto-generated if not specified)"
    )
    parser.add_argument(
        "-q", "--quality",
        choices=["low", "medium", "high", "ultra"],
        default="high",
        help="Output quality (default: high)"
    )
    parser.add_argument(
        "-m", "--method",
        choices=["standard", "enhanced", "spatial"],
        default="enhanced",
        help="Conversion method (default: enhanced)"
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Batch mode: process all M4A files in input directory"
    )
    parser.add_argument(
        "--export-ir",
        metavar="NAME",
        help="Export stereo IR files (44/48kHz L/R) capturing the selected method's processing"
    )
    parser.add_argument(
        "--convolve",
        metavar="IR_BASE",
        help="Convert using a stereo IR pair (matches {name}_44_left.wav / {name}_48_right.wav etc.)"
    )
    parser.add_argument(
        "--ir-dir",
        default=None,
        help="Directory for IR export/convolution (default: impulse_responses/stereo)"
    )
    
    args = parser.parse_args()
    
    # Print banner
    print("\n" + "="*60)
    print("  Dolby 5.1 to Binaural Atmos Converter")
    print("  Optimized for Android TWS Earbuds")
    print("="*60)
    
    # Check FFmpeg
    if not check_ffmpeg():
        print("\n[ERROR] FFmpeg not found!")
        print("Install with:")
        print("  Windows: winget install ffmpeg")
        print("  macOS:   brew install ffmpeg")
        print("  Linux:   sudo apt install ffmpeg")
        print("\nOr download from: https://ffmpeg.org/download.html")
        sys.exit(1)
    
    # Export IR mode
    if args.export_ir:
        if not export_stereo_irs:
            print("\n[ERROR] foobar_convolver/scipy module not available")
            sys.exit(1)
        chain = FILTER_PRESETS.get(args.method, FILTER_PRESETS["enhanced"])["filter"]
        ir_dir = args.ir_dir or (str(STEREO_IR_DIR) if STEREO_IR_DIR else "impulse_responses/stereo")
        print(f"\n  Exporting IR files for method '{args.method}'...")
        print(f"  Name:    {args.export_ir}")
        print(f"  Dir:     {ir_dir}")
        created = export_stereo_irs(chain, args.export_ir, ir_dir)
        if created:
            print(f"\n  ✓ Created {len(created)} IR files:")
            for p in created:
                print(f"    - {p}")
            print("\n  Use them in foobar2000's Stereo Convolver (foo_dsp_stereoconv.dll)")
            print("  or convert with: python convert_atmos.py file.m4a --convolve <name>")
            sys.exit(0)
        print("\n[ERROR] IR export failed - see console output")
        sys.exit(1)
    
    # Batch mode
    if args.batch:
        if not args.input or not os.path.isdir(args.input):
            print("\n[ERROR] Batch mode requires a directory path")
            print("Usage: python convert_atmos.py --batch /path/to/music")
            sys.exit(1)
        
        success, failed = process_batch(args.input, args.quality, args.method,
                                        args.convolve, args.ir_dir)
        
        print(f"\n{'='*60}")
        print(f"  Batch Complete!")
        print(f"  Success: {success}")
        print(f"  Failed:  {failed}")
        print(f"{'='*60}\n")
        
        sys.exit(0 if failed == 0 else 1)
    
    # Single file mode
    if not args.input:
        parser.print_help()
        sys.exit(1)
    
    if not os.path.isfile(args.input):
        print(f"\n[ERROR] Input file not found: {args.input}")
        sys.exit(1)
    
    # Generate output filename if not provided
    if not args.output:
        base_name = os.path.splitext(args.input)[0]
        args.output = f"{base_name}_binaural.m4a"
    
    # Convert
    start_time = time.time()
    success = convert_to_binaural(
        args.input,
        args.output,
        args.quality,
        args.method,
        ir_base=args.convolve,
        ir_dir=args.ir_dir
    )
    
    if success:
        print(f"\n{'='*60}")
        print(f"  Ready for your Android TWS earbuds!")
        print(f"  ✓ Transfer to your phone")
        print(f"  ✓ Play with any music player")
        print(f"  ✓ Enable Spatial Audio if available")
        print(f"{'='*60}\n")
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
