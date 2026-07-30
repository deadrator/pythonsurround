@echo off
REM ============================================================
REM Atmos Binaural Converter - Windows EXE Builder
REM Creates a standalone .exe using PyInstaller
REM ============================================================

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
echo [2/4] Installing dependencies...
pip install pillow

REM Create the EXE
echo [3/4] Building EXE (this may take a minute)...
echo.

pyinstaller ^
    --onefile ^
    --windowed ^
    --name "AtmosBinauralConverter" ^
    --icon=NUL ^
    --add-data "convert_atmos.py;." ^
    --noconfirm ^
    --clean ^
    gui_app.py

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
echo.
echo ============================================================
echo.

REM Open the dist folder
explorer dist

pause
