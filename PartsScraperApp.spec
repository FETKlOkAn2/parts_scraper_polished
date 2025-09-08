# -*- mode: python ; coding: utf-8 -*-


block_cipher = None


a = Analysis(
    ['parts_scraper_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('wm_remover.py', '.')],
    hiddenimports=['tkinter', 'tkinter.ttk', 'tkinter.filedialog', 'tkinter.messagebox', 'tkinter.scrolledtext', 'cv2', 'pytesseract', 'numpy', 'pandas', 'PIL', 'PIL.Image', 'PIL.ImageTk', 'pathlib', 'threading', 'os', 'sys'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'skimage', 'tensorflow', 'torch', 'tensorboard', 'easyocr', 'transformers'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='PartsScraperApp',
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
