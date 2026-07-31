#!/usr/bin/env python3
"""
Channel Audio Visualizer - TUI / Command Line

Visualizes 5.1 / 7.1 / Atmos (and any other) per-channel audio levels:

    python visualize_audio.py song.m4a              # live per-channel VU bars
    python visualize_audio.py song.flac --snapshot  # static ASCII level chart
    python visualize_audio.py --system              # live system playback capture
    python visualize_audio.py song.m4a --speed 8    # accelerated playhead

Supports every format FFmpeg can decode (M4A, MP4, MKV, FLAC, WAV, OGG, ...).
System capture needs the optional 'sounddevice' package (WASAPI loopback on
Windows, PulseAudio monitor on Linux).
"""

import argparse
import os
import sys
import time

import numpy as np

from channel_visualizer import (
    DecodedAudio, SystemCapture, analyze_file, compute_levels, level_to_meter,
    WINDOW_SECONDS
)

BAR_WIDTH = 20
BAR_FULL = "█"
BAR_EMPTY = "░"


def _setup_bars():
    """Pick Unicode or ASCII bar characters depending on stdout encoding."""
    global BAR_FULL, BAR_EMPTY
    enc = (sys.stdout.encoding or "utf-8") if sys.stdout else "utf-8"
    try:
        "\u2588".encode(enc, "strict")
        BAR_FULL, BAR_EMPTY = "█", "░"
    except (UnicodeEncodeError, LookupError, TypeError):
        BAR_FULL, BAR_EMPTY = "#", "-"


def _enable_vt():
    """Enable ANSI virtual terminal processing on Windows consoles."""
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_uint32()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            pass


def _fmt(seconds):
    seconds = max(0, int(seconds or 0))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _bar(level: float, width: int = BAR_WIDTH) -> str:
    filled = int(round(level * width))
    filled = max(0, min(width, filled))
    return BAR_FULL * filled + BAR_EMPTY * (width - filled)


def _db(value: float) -> str:
    db = 20.0 * np.log10(max(float(value), 1e-9))
    return f"{db:6.1f}"


def _print_metadata(info: dict, audio=None):
    rate = audio.sample_rate if audio else info.get("sample_rate", 0)
    print(f"  File:    {info['file']}")
    print(f"  Format:  {info.get('format', '?')}")
    print(f"  Sample:  {rate} Hz")
    print(f"  Layout:  {info.get('channels', 0)}ch {info.get('channel_layout', '?')}"
          f"  {info.get('channel_names', [])}")
    print(f"  Length:  {_fmt(info.get('duration', 0))}")
    print("  " + "-" * 56)


def _render_live(names, rms, peak, progress, duration):
    lines = []
    lines.append(f"  {_bar(progress, 30)} {_fmt(progress * duration)} / {_fmt(duration)}")
    for i, name in enumerate(names):
        if i >= len(rms):
            break
        lines.append(f"  {name:<5} {_bar(level_to_meter(rms[i]))} "
                     f"RMS {_db(rms[i])} dB   Peak {_db(peak[i])} dB")
    return "\n".join(lines)


def _live_loop(names, get_frame, duration, speed, fps=25):
    """Generic live loop: get_frame() -> (rms, peak, progress 0..1, done)."""
    frame_dt = 1.0 / fps
    count = 0
    try:
        while True:
            start = time.time()
            rms, peak, progress, done = get_frame()
            text = _render_live(names, rms, peak, progress, duration)
            lines = text.count("\n") + 1
            if count == 0:
                sys.stdout.write(text)
            else:
                sys.stdout.write(f"\033[{lines}A" + text)
            sys.stdout.write("\n")
            sys.stdout.flush()
            count += 1
            elapsed = time.time() - start
            time.sleep(max(0.0, frame_dt - elapsed) / speed)
            if done:
                break
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\n")


def cmd_live(args):
    """Live visualization of a file's channels as the playhead advances."""
    info = analyze_file(args.file)
    _print_metadata(info)
    print("  Decoding...")
    audio = DecodedAudio(args.file, channel_names=info["channel_names"])
    try:
        window = int(args.window * audio.sample_rate)
        state = {"pos": 0, "last": time.time()}

        def get_frame():
            now = time.time()
            state["pos"] += int((now - state["last"]) * audio.sample_rate * args.speed)
            state["last"] = now
            pos = state["pos"]
            if pos >= audio.total_samples:
                if args.loop:
                    state["pos"] = 0
                    return np.zeros(audio.channels), np.zeros(audio.channels), 0.0, False
                return np.zeros(audio.channels), np.zeros(audio.channels), 1.0, True
            block = audio.get_block(pos, window)
            rms, peak = compute_levels(block)
            return rms, peak, pos / audio.total_samples, False

        _live_loop(audio.channel_names, get_frame, audio.duration, args.speed)
        print(f"\n  Done - visualized {_fmt(audio.duration)} of audio.")
    finally:
        audio.cleanup()


def cmd_snapshot(args):
    """Static ASCII chart of per-channel levels (whole file or --at window)."""
    info = analyze_file(args.file)
    print()
    _print_metadata(info)
    audio = DecodedAudio(args.file, channel_names=info["channel_names"])
    try:
        start = int(args.at * audio.sample_rate) if args.at is not None else 0
        count = int(args.window * audio.sample_rate) if args.at is not None else audio.total_samples
        end = min(start + count, audio.total_samples)
        sums = np.zeros(audio.channels, dtype=np.float64)
        peaks = np.zeros(audio.channels, dtype=np.float64)
        n = 0
        block = 1_000_000
        pos = start
        while pos < end:
            seg = audio.get_block(pos, min(block, end - pos))
            rms, peak = compute_levels(seg)
            sums += (rms.astype(np.float64) ** 2) * len(seg)
            peaks = np.maximum(peaks, peak)
            n += len(seg)
            pos += block
        mean_rms = np.sqrt(sums / max(n, 1))
        print("\n  Channel levels:")
        for i, name in enumerate(audio.channel_names):
            print(f"  {name:<5} {_bar(level_to_meter(mean_rms[i]))} "
                  f"RMS {_db(mean_rms[i])} dB   Peak {_db(peaks[i])} dB")
        print()
    finally:
        audio.cleanup()


def cmd_system(args):
    """Live visualization of system playback (loopback capture)."""
    print("\n  System audio capture (sounddevice)\n")
    if not SystemCapture.available():
        print("  " + SystemCapture.describe())
        sys.exit(1)
    holder = {"rms": None, "peak": None}

    def cb(rms, names):
        holder["rms"] = rms
        holder["peak"] = np.maximum(holder["peak"] if holder["peak"] is not None
                                     else np.zeros_like(rms), rms)

    cap = SystemCapture(callback=cb)
    if not cap.start():
        print("  Failed to start system capture.")
        sys.exit(1)
    names = cap.channel_names
    print(f"  Capturing from device #{cap.device_index} ({cap.sample_rate} Hz) - Ctrl+C to stop\n")
    start_t = time.time()

    def get_frame():
        rms = holder["rms"]
        if rms is None:
            rms = np.zeros(len(names))
        peak = holder["peak"] if holder["peak"] is not None else np.zeros_like(rms)
        # decay the peak hold so it tracks recent transients
        holder["peak"] = peak * 0.97
        done = bool(args.timeout) and time.time() - start_t > args.timeout
        return rms, peak, 0.0, done

    try:
        _live_loop(names, get_frame, 0.0, 1.0)
    finally:
        cap.stop()
        print("  Capture stopped.")


def main():
    parser = argparse.ArgumentParser(
        prog="visualize_audio",
        description="Visualize 5.1 / 7.1 / Atmos per-channel audio levels (file or live system capture)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  visualize_audio.py song.m4a                # live per-channel visualization
  visualize_audio.py song.flac --snapshot    # static ASCII level chart
  visualize_audio.py --system                # live system playback capture
  visualize_audio.py song.m4a --speed 10     # accelerated playhead
""")
    parser.add_argument("file", nargs="?", help="Audio file to visualize")
    parser.add_argument("--snapshot", action="store_true",
                        help="Print a static ASCII level chart instead of live animation")
    parser.add_argument("--system", action="store_true",
                        help="Visualize live system playback (needs sounddevice)")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="Playhead speed multiplier (default 1.0)")
    parser.add_argument("--window", type=float, default=WINDOW_SECONDS,
                        help="Level analysis window in seconds (default 0.5)")
    parser.add_argument("--at", type=float, default=None,
                        help="Snapshot window start in seconds (default: whole file)")
    parser.add_argument("--loop", action="store_true",
                        help="Loop the file in live mode")
    parser.add_argument("--timeout", type=float, default=None,
                        help="System capture duration in seconds (default: until Ctrl+C)")
    args = parser.parse_args()

    _enable_vt()
    # Never crash when stdout is a non-UTF-8 pipe (cp1252 on Windows)
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except Exception:
                pass
    _setup_bars()

    if args.system:
        cmd_system(args)
        return
    if not args.file:
        parser.print_help()
        sys.exit(1)
    if not os.path.isfile(args.file):
        print(f"[ERROR] File not found: {args.file}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  Channel Audio Visualizer")
    print("=" * 60)

    if args.snapshot:
        cmd_snapshot(args)
    else:
        cmd_live(args)


if __name__ == "__main__":
    main()
