# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['gui_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('convert_atmos.py', '.'),
        ('default_51.sofa', '.'),
        ('default_71.sofa', '.'),
    ],
    hiddenimports=[
        'audio_codecs',
        'dark_theme',
        'player_gui',
        'speaker_shifter',
        'channel_visualizer',
        'volume_visualizer',
        'visualizer_gui',
        'foobar_convolver',
        'hesuvi_support',
        'hrtf_generator',
        'head_model_parser',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AtmosBinauralConverter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
