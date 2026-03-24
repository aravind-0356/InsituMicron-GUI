# -*- mode: python ; coding: utf-8 -*-
# InsituMicron GUI - PyInstaller Build Specification

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('LICENSES', 'LICENSES'),
        ('app_icon.ico', '.'),
        ('InsituMicronlogo.jpg', '.'),  # Company logo for sidebar
        ('IM_logo_only.jpg', '.'),      # Small logo
    ],
    hiddenimports=[
        'pyqtgraph.graphicsItems.PlotItem',
        'pyqtgraph.graphicsItems.ViewBox',
        'pyqtgraph.graphicsItems.PlotCurveItem',
        'pyqtgraph.graphicsItems.AxisItem',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Only exclude modules we are 100% sure are not needed
        'tkinter',
        'matplotlib',
        'scipy',
        'pandas',
        'PIL',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='InsituMicronGUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.ico',  # Application icon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='InsituMicronGUI',
)
