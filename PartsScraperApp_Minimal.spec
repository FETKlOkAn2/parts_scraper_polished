# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['parts_scraper_minimal.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['cv2', 'pytesseract', 'numpy', 'PIL'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'skimage', 'pandas', 'easyocr', 'torch', 'IPython', 'jupyter', 'notebook'],
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
    name='PartsScraperApp_Minimal',
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
)
