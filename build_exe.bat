@echo off
REM ============================================================
REM Atmos Binaural Converter - Windows EXE Builder
REM Creates a standalone .exe using PyInstaller
REM ============================================================
REM Work from the folder this script lives in, even when double-clicked
REM from elsewhere (so the .spec path always resolves).
cd /d "%~dp0"

echo.
echo ============================================================
echo   Building Atmos Binaural Converter EXE
echo ============================================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found! Install Python 3.8+ from https://python.org
    pause
    exit /b 1
)

REM Install PyInstaller if not present
echo [1/4] Checking PyInstaller...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo      Installing PyInstaller...
    pip install pyinstaller
)

REM Install any required dependencies
echo [2/4] Installing dependencies (numpy/scipy/h5py/pillow/sounddevice)...
pip install -r requirements.txt

REM Create the EXE
echo [3/4] Building EXE (this may take a minute)...
echo.

REM Use the committed spec (AtmosBinauralConverter.spec) so the
REM module list, hidden imports, and bundled data stay in sync.
pyinstaller AtmosBinauralConverter.spec --noconfirm --clean

if errorlevel 1 (
    echo.
    echo ❌ Build failed!
    pause
    exit /b 1
)

echo.
echo [4/4] Copying to output folder...
if not exist "dist" mkdir dist

echo.
echo ============================================================
echo   ✅ Build Complete!
echo ============================================================
echo.
echo   EXE Location: dist\AtmosBinauralConverter.exe
echo.
echo   You can copy this EXE to any Windows machine - no Python needed!
echo   (FFmpeg must still be installed and in PATH)
echo.
echo ============================================================
echo.

REM Open the dist folder
explorer dist

pause
