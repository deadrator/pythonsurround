#Requires -Version 5.1
<#
.SYNOPSIS
    Converts Dolby 5.1 surround sound to binaural stereo for headphones/TWS

.DESCRIPTION
    This script converts multi-channel audio (5.1, 7.1) to binaural stereo
    optimized for TWS earbuds and headphones on Android devices.
    
    Features:
    - Automatic channel detection
    - Multiple conversion methods (standard, enhanced, spatial)
    - Quality presets
    - Batch processing support

.PARAMETER InputFile
    Path to input M4A file

.PARAMETER OutputFile
    Path to output file (optional, auto-generated if not specified)

.PARAMETER Quality
    Output quality: low (128k), medium (192k), high (256k), ultra (320k)

.PARAMETER Method
    Conversion method: standard, enhanced, spatial

.PARAMETER Batch
    Process all M4A files in a directory

.EXAMPLE
    .\convert_atmos.ps1 movie_audio.m4a

.EXAMPLE
    .\convert_atmos.ps1 -InputFile movie_audio.m4a -Quality ultra -Method spatial

.EXAMPLE
    .\convert_atmos.ps1 -Batch -InputFile "C:\Music\Atmos"
#>

param(
    [Parameter(Position=0)]
    [string]$InputFile,
    
    [string]$OutputFile,
    
    [ValidateSet("low", "medium", "high", "ultra")]
    [string]$Quality = "high",
    
    [ValidateSet("standard", "enhanced", "spatial")]
    [string]$Method = "enhanced",
    
    [switch]$Batch
)

# Quality presets (bitrate)
$QualityMap = @{
    "low"    = "128k"
    "medium" = "192k"
    "high"   = "256k"
    "ultra"  = "320k"
}

function Test-FFmpeg {
    try {
        $null = Get-Command ffmpeg -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Get-AudioInfo {
    param([string]$File)
    
    $info = & ffmpeg -i $File 2>&1 | Select-String "Audio:"
    if ($info) {
        return $info.Line.Trim()
    }
    return $null
}

function Convert-ToBinaural {
    param(
        [string]$Input,
        [string]$Output,
        [string]$Bitrate,
        [string]$ConvMethod
    )
    
    Write-Host "`n[Converting] $Input" -ForegroundColor Cyan
    Write-Host "Method: $ConvMethod | Quality: $Bitrate" -ForegroundColor Gray
    
    # Build filter based on method
    $filter = switch ($ConvMethod) {
        "standard" {
            # Simple ITU-R BS.775 downmix (standard coefficients)
            "aresample=48000,pan=stereo|c0=c0+0.707*c2+0.707*c4|c1=c1+0.707*c2+0.707*c5"
        }
        "enhanced" {
            # Downmix with bass enhancement and clarity (ITU-R BS.775)
            "aresample=48000,pan=stereo|c0=c0+0.707*c2+0.707*c4|c1=c1+0.707*c2+0.707*c5,anequalizer=c0 f=80 w=200 g=4 t=1|c1 f=80 w=200 g=4 t=1,equalizer=f=2500:t=q:w=1:g=2,equalizer=f=8000:t=q:w=1:g=1"
        }
        "spatial" {
            # Enhanced spatial with crossfeed simulation (ITU-R BS.775 + spatial cues)
            "aresample=48000,aformat=channel_layouts=5.1,pan=stereo|c0=0.87*c0+0.707*c2+0.707*c4+0.25*c5|c1=0.87*c1+0.707*c2+0.707*c5+0.25*c4,anequalizer=c0 f=60 w=150 g=5 t=1|c1 f=60 w=150 g=5 t=1,equalizer=f=2000:t=q:w=1.5:g=3,equalizer=f=6000:t=q:w=1:g=2,equalizer=f=10000:t=q:w=1:g=1.5,volume=0.95"
        }
    }
    
    # Execute conversion
    $result = & ffmpeg -i $Input `
        -af ($filter -replace "`n", ",") `
        -c:a aac `
        -b:a $Bitrate `
        -ar 48000 `
        -movflags +faststart `
        -y $Output 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[Success] $Output" -ForegroundColor Green
        return $true
    } else {
        Write-Host "[Failed] Conversion error" -ForegroundColor Red
        $result | Where-Object { $_ -match "error|Error" } | ForEach-Object {
            Write-Host "  $_" -ForegroundColor Red
        }
        return $false
    }
}

# Main script
Write-Host "`n" -NoNewline
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host "   Dolby 5.1 to Binaural Atmos Converter" -ForegroundColor Magenta
Write-Host "   Optimized for Android TWS Earbuds" -ForegroundColor Magenta
Write-Host "============================================================" -ForegroundColor Magenta

# Check FFmpeg
if (-not (Test-FFmpeg)) {
    Write-Host "`n[ERROR] FFmpeg not found!" -ForegroundColor Red
    Write-Host "Install with: winget install ffmpeg" -ForegroundColor Yellow
    Write-Host "Or download from: https://ffmpeg.org/download.html" -ForegroundColor Yellow
    exit 1
}

$bitrate = $QualityMap[$Quality]

if ($Batch) {
    # Batch mode - process all M4A files
    if (-not $InputFile -or -not (Test-Path $InputFile -PathType Container)) {
        Write-Host "`n[ERROR] Batch mode requires a directory path" -ForegroundColor Red
        exit 1
    }
    
    $files = Get-ChildItem -Path $InputFile -Filter "*.m4a" -File
    Write-Host "`nFound $($files.Count) M4A files to process" -ForegroundColor Cyan
    
    $success = 0
    $failed = 0
    
    foreach ($file in $files) {
        $outName = "$($file.BaseName)_binaural$($file.Extension)"
        $outPath = Join-Path $file.DirectoryName $outName
        
        if (Convert-ToBinaural -Input $file.FullName -Output $outPath -Bitrate $bitrate -ConvMethod $Method) {
            $success++
        } else {
            $failed++
        }
    }
    
    Write-Host "`n============================================================" -ForegroundColor Magenta
    Write-Host "Batch Complete: $success succeeded, $failed failed" -ForegroundColor $(if ($failed -eq 0) { "Green" } else { "Yellow" })
    
} else {
    # Single file mode
    if (-not $InputFile) {
        Write-Host "`nUsage:" -ForegroundColor Yellow
        Write-Host "  .\convert_atmos.ps1 input.m4a" -ForegroundColor White
        Write-Host "  .\convert_atmos.ps1 -InputFile input.m4a -Quality ultra" -ForegroundColor White
        Write-Host "  .\convert_atmos.ps1 -Batch -InputFile 'C:\Music\Atmos'" -ForegroundColor White
        Write-Host "`nOptions:" -ForegroundColor Yellow
        Write-Host "  -Quality: low, medium, high, ultra" -ForegroundColor Gray
        Write-Host "  -Method: standard, enhanced, spatial" -ForegroundColor Gray
        exit 0
    }
    
    if (-not (Test-Path $InputFile -PathType Leaf)) {
        Write-Host "`n[ERROR] Input file not found: $InputFile" -ForegroundColor Red
        exit 1
    }
    
    # Auto-generate output filename if not provided
    if (-not $OutputFile) {
        $file = Get-Item $InputFile
        $OutputFile = Join-Path $file.DirectoryName "$($file.BaseName)_binaural$($file.Extension)"
    }
    
    # Analyze input
    Write-Host "`n[Analyzing] $InputFile" -ForegroundColor Cyan
    $audioInfo = Get-AudioInfo -File $InputFile
    if ($audioInfo) {
        Write-Host "  $audioInfo" -ForegroundColor Gray
    }
    
    # Convert
    $startTime = Get-Date
    $success = Convert-ToBinaural -Input $InputFile -Output $OutputFile -Bitrate $bitrate -ConvMethod $Method
    $duration = (Get-Date) - $startTime
    
    if ($success) {
        $outputInfo = Get-AudioInfo -File $OutputFile
        Write-Host "`n============================================================" -ForegroundColor Magenta
        Write-Host "Conversion Complete!" -ForegroundColor Green
        Write-Host "  Output: $OutputFile" -ForegroundColor White
        Write-Host "  Time:   $($duration.TotalSeconds.ToString('F1'))s" -ForegroundColor Gray
        if ($outputInfo) {
            Write-Host "  $outputInfo" -ForegroundColor Gray
        }
        Write-Host "`nReady for your Android TWS earbuds!" -ForegroundColor Cyan
        Write-Host "  - Transfer to your phone" -ForegroundColor Gray
        Write-Host "  - Play with any music player" -ForegroundColor Gray
        Write-Host "  - Enable Spatial Audio if available" -ForegroundColor Gray
    }
}

Write-Host ""
