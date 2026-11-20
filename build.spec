# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, copy_metadata

# Automotive dependency collection for NI-DAQmx 1.4.1 requirements
ni_datas, ni_binaries, ni_hiddenimports = collect_all('nidaqmx') # Main DAQ library - Verified
nt_datas, nt_binaries, nt_hiddenimports = collect_all('nitypes') # Required data types - Verified
ox_datas, ox_binaries, ox_hiddenimports = collect_all('openpyxl') # Excel exports - Verified
cl_datas, cl_binaries, cl_hiddenimports = collect_all('click') # nidaqmx CLI dependency - Verified
dep_datas, dep_binaries, dep_hiddenimports = collect_all('deprecation') # nidaqmx version management - Verified
ht_datas, ht_binaries, ht_hiddenimports = collect_all('hightime') # nidaqmx precision timing - Verified
dc_datas, dc_binaries, dc_hiddenimports = collect_all('python-decouple') # nidaqmx config dependency - Verified
rq_datas, rq_binaries, rq_hiddenimports = collect_all('requests') # nidaqmx update checks - Verified
te_datas, te_binaries, te_hiddenimports = collect_all('typing_extensions') # nidaqmx typing support - Verified
tz_datas, tz_binaries, tz_hiddenimports = collect_all('tzlocal') # nidaqmx timezone dependency - Verified
pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all('packaging') # nidaqmx requirement tracking - Verified
ps_datas, ps_binaries, ps_hiddenimports = collect_all('PySpin') # FLIR camera library - Verified
cv_datas, cv_binaries, cv_hiddenimports = collect_all('cv2')    # OpenCV image saving - Verified
rl_datas, rl_binaries, rl_hiddenimports = collect_all('reportlab') # PDF export
sp_datas, sp_binaries, sp_hiddenimports = collect_all('scipy') # Material analysis
pg_datas, pg_binaries, pg_hiddenimports = collect_all('pyqtgraph') # Real-time plotting
ser_datas, ser_binaries, ser_hiddenimports = collect_all('serial') # Serial motor communication
pil_datas, pil_binaries, pil_hiddenimports = collect_all('PIL')    # Image processing & PDF graphs
np_datas, np_binaries, np_hiddenimports = collect_all('numpy')     # Signal processing & array math

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=ni_binaries + nt_binaries + ox_binaries + cl_binaries + dep_binaries + ht_binaries + dc_binaries + rq_binaries + te_binaries + tz_binaries + pkg_binaries + ps_binaries + cv_binaries + rl_binaries + sp_binaries + pg_binaries + ser_binaries + pil_binaries + np_binaries,
    datas=[
        ('LICENSES', 'LICENSES'),
        ('config', 'config'),
        ('app_icon.ico', '.'),
        ('InsituMicronlogo.jpg', '.'),
    ] + ni_datas + nt_datas + ox_datas + cl_datas + dep_datas + ht_datas + dc_datas + rq_datas + te_datas + tz_datas + pkg_datas + ps_datas + cv_datas + rl_datas + sp_datas + pg_datas + ser_datas + pil_datas + np_datas + copy_metadata('nidaqmx') + copy_metadata('nitypes') + copy_metadata('python-decouple') + copy_metadata('openpyxl') + copy_metadata('reportlab') + copy_metadata('scipy') + copy_metadata('pyqtgraph') + copy_metadata('packaging') + copy_metadata('pillow'),
    hiddenimports=[
        # PySide6
        'PySide6.QtCore',
        'PySide6.QtWidgets',
        'PySide6.QtGui',
        'PySide6.QtPrintSupport',
        'serial.tools.list_ports',
        'serial.tools.list_ports_windows',
        # NumPy internals
        'numpy.core._methods',
        'numpy.lib.format',
    ] + ni_hiddenimports + nt_hiddenimports + ox_hiddenimports + cl_hiddenimports + dep_hiddenimports + ht_hiddenimports + dc_hiddenimports + rq_hiddenimports + te_hiddenimports + tz_hiddenimports + pkg_hiddenimports + ps_hiddenimports + cv_hiddenimports + rl_hiddenimports + sp_hiddenimports + pg_hiddenimports + ser_hiddenimports + pil_hiddenimports + np_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'pandas',
        'pytest',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='InsituMicronGUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # Disabled — UPX can corrupt Qt/NumPy DLLs silently
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.ico',
    version='file_version_info.txt',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='InsituMicronGUI',
)