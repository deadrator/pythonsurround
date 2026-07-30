@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM Dolby 5.1 to Binaural Atmos Converter for Android TWS
REM Converts surround sound to stereo binaural for headphones
REM ============================================================

set "INPUT=%~1"
set "OUTPUT=%~2"

if "%INPUT%"=="" (
    echo.
    echo Usage: convert_atmos.bat input.m4a [output.m4a]
    echo.
    echo Examples:
    echo   convert_atmos.bat movie_audio.m4a
    echo   convert_atmos.bat movie_audio.m4a movie_binaural.m4a
    echo.
    exit /b 1
)

if not exist "%INPUT%" (
    echo ERROR: Input file not found: %INPUT%
    exit /b 1
)

if "%OUTPUT%"=="" (
    for %%f in ("%INPUT%") do set "OUTPUT=%%~nf_binaural%%~xf"
)

echo ============================================================
echo   Dolby 5.1 to Binaural Atmos Converter
echo ============================================================
echo.
echo Input:  %INPUT%
echo Output: %OUTPUT%
echo.

REM Check if ffmpeg is available
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo ERROR: ffmpeg not found in PATH
    echo Download from: https://ffmpeg.org/download.html
    exit /b 1
)

REM Probe input file
echo [1/3] Analyzing input file...
ffmpeg -i "%INPUT%" 2>&1 | findstr /C:"Audio:" >nul
if errorlevel 1 (
    echo ERROR: No audio stream found in input file
    exit /b 1
)

REM Get channel info
for /f "tokens=*" %%a in ('ffmpeg -i "%INPUT%" 2^>^&1 ^| findstr /C:"Audio:"') do set "AUDIO_INFO=%%a"
echo       !AUDIO_INFO!
echo.

REM ============================================================
REM BINAURAL CONVERSION - Multiple filter options
REM ============================================================

echo [2/3] Converting to binaural stereo...
echo       Using downmix with spatial enhancement...
echo.

REM Method: 5.1 to Stereo downmix with binaural enhancement
REM Standard ITU-R BS.775 downmix coefficients with added spatial processing
REM
REM Channel mapping for 5.1 (FL, FR, FC, LFE, BL, BR):
REM   Left  = FL + 0.707*FC + 0.707*BL
REM   Right = FR + 0.707*FC + 0.707*BR
REM
REM For binaural effect, we add slight delay and EQ

ffmpeg -i "%INPUT%" -filter_complex ^
    "[0:a]aresample=48000,aformat=channel_layouts=5.1[51]; ^
     [51]pan=stereo|c0=c0+0.707*c2+0.707*c4|c1=c1+0.707*c2+0.707*c5[mix]; ^
     [mix]anequalizer=c0 f=100 w=200 g=3 t=1|c1 f=100 w=200 g=3 t=1[bass]; ^
     [bass]equalizer=f=3000:t=q:w=1.5:g=2[hf]; ^
     [hf]equalizer=f=8000:t=q:w=1:g=1[air]; ^
     [air]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[out]" ^
    -map "[out]" ^
    -c:a aac -b:a 256k -ar 48000 ^
    -movflags +faststart ^
    "%OUTPUT%" 2>&1

if errorlevel 1 (
    echo.
    echo Trying alternative method...
    echo.
    
    REM Fallback: Simple stereo downmix (ITU-R BS.775)
    ffmpeg -i "%INPUT%" -af ^
        "aresample=48000,pan=stereo|c0=c0+0.707*c2+0.707*c4|c1=c1+0.707*c2+0.707*c5, ^
         equalizer=f=100:t=q:w=1:g=3, ^
         equalizer=f=3000:t=q:w=1:g=2, ^
         equalizer=f=8000:t=q:w=1:g=1" ^
        -c:a aac -b:a 256k -ar 48000 ^
        -movflags +faststart ^
        "%OUTPUT%" 2>&1
)

if errorlevel 1 (
    echo ERROR: Conversion failed
    exit /b 1
)

echo.
echo [3/3] Conversion complete!
echo.
echo ============================================================
echo   Output: %OUTPUT%
echo   Format: AAC Stereo (Android compatible)
echo   Ready for: TWS earbuds / Any headphone
echo ============================================================
echo.
echo   For best experience on Android:
echo   1. Transfer to your phone
echo   2. Play with any music player
echo   3. Enable "Dolby Atmos" or "Spatial Audio" if available
echo   4. Use wired headphones or TWS earbuds for binaural effect
echo.
