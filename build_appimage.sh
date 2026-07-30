#!/bin/bash
# ============================================================
# Atmos Binaural Converter - AppImage Builder
# Build script for creating Linux AppImage
# ============================================================

set -e

echo "============================================================"
echo "   Building Atmos Binaural Converter AppImage"
echo "============================================================"
echo ""

# Check if running on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo "❌ Error: This script must be run on Linux"
    exit 1
fi

# Check for required tools
check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo "❌ Error: $1 is required but not installed"
        echo "   Install with: $2"
        exit 1
    fi
}

check_command "python3" "sudo apt install python3"
check_command "pip3" "sudo apt install python3-pip"
check_command "ffmpeg" "sudo apt install ffmpeg"

# Install appimage-builder if not present
if ! command -v appimage-builder &> /dev/null; then
    echo "📦 Installing appimage-builder..."
    pip3 install --user appimage-builder
    
    # Add to PATH if needed
    export PATH="$HOME/.local/bin:$PATH"
fi

# Check for appimagetool
if ! command -v appimagetool &> /dev/null; then
    echo "📦 Downloading appimagetool..."
    
    # Try wget first, then curl as fallback
    if command -v wget &> /dev/null; then
        wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" -O /tmp/appimagetool
    elif command -v curl &> /dev/null; then
        curl -sL "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" -o /tmp/appimagetool
    else
        echo "❌ Error: Neither wget nor curl found"
        echo "   Install with: sudo apt install wget curl"
        exit 1
    fi
    
    chmod +x /tmp/appimagetool
    sudo mv /tmp/appimagetool /usr/local/bin/
fi

echo ""
echo "🔨 Building AppImage..."
echo ""

# Run appimage-builder
appimage-builder --recipe AppImageBuilder.yml

# Find the generated AppImage
APPIMAGE_FILE=$(find . -maxdepth 1 -name "*.AppImage" -type f | head -1)

if [ -f "$APPIMAGE_FILE" ]; then
    echo ""
    echo "============================================================"
    echo "   ✅ Build Complete!"
    echo "============================================================"
    echo ""
    echo "   Output: $APPIMAGE_FILE"
    echo ""
    echo "   To run:"
    echo "   chmod +x $APPIMAGE_FILE"
    echo "   ./$APPIMAGE_FILE"
    echo ""
    echo "   The AppImage is portable - copy it anywhere on Linux!"
    echo "============================================================"
else
    echo ""
    echo "❌ Build failed - no AppImage generated"
    exit 1
fi
