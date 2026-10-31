# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

bin_files = [
    (str(path), 'bin')
    for path in sorted(Path('bin').glob('*'))
    if path.suffix.lower() in {'.exe', '.dll'}
]

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=bin_files,
    datas=[
        ('README.md', '.'),
        ('LICENSE', '.'),
        ('THIRD_PARTY_NOTICES.md', '.'),
        ('licenses', 'licenses'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LyricsSubtitle',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='assets/icon.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='LyricsSubtitle',
)
