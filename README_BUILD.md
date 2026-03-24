# InsituMicron GUI - Build & Packaging Guide

## Prerequisites
- Python 3.10+ with dependencies installed
- PyInstaller: `pip install pyinstaller`
- Inno Setup 6.x: Download from https://jrsoftware.org/isinfo.php
- FLIR Spinnaker SDK (for camera features)

---

## Step 1: Clean Build Environment

Delete old build artifacts:
```powershell
Remove-Item -Recurse -Force build, dist, __pycache__ -ErrorAction SilentlyContinue
```

## Step 2: Build Executable with PyInstaller

Run from the project directory:
```powershell
pyinstaller build.spec --clean --noconfirm
```

This creates:
```
dist/
└── InsituMicronGUI/
    ├── InsituMicronGUI.exe    ← Your application
    ├── _internal/             ← Python runtime & libraries
    ├── LICENSES/              ← License files
    └── app_icon.ico           ← Application icon
```

**Expected size**: ~150-200 MB (includes Qt libraries)

## Step 3: Create Installer with Inno Setup

1. Open **Inno Setup Compiler**
2. File → Open → Select `installer.iss`
3. Build → Compile (or press F9)
4. The installer will be created in `installer_output/` folder:
   - `InsituMicronGUI_Setup_2.1.1.exe`

---

## Files Created

| File | Purpose |
|------|---------|
| `app_icon.ico` | Application icon (multi-resolution) |
| `build.spec` | PyInstaller configuration |
| `installer.iss` | Inno Setup installer script |
| `requirements.txt` | Cleaned Python dependencies |

---

## Customization Options

### Change Version Number
Update in these files:
1. `main.py` → `__version__ = "X.X.X"`
2. `installer.iss` → `#define MyAppVersion "X.X.X"`
3. `LICENSES/LICENSE.txt` → `Software Version: X.X.X`

### Change Company Logo
1. Replace `app_icon.ico` with your new icon
2. Replace `IM_logo_only.jpg` and `InsituMicronlogo.jpg` for installer wizard

### Reduce Package Size
The `build.spec` already excludes unused modules. For further reduction:
1. Use UPX compression (already enabled)
2. Exclude more modules in the `excludes` list

---

## Distribution Checklist

- [ ] Update version number in all files
- [ ] Run `pyinstaller build.spec --clean`
- [ ] Test the exe in `dist/InsituMicronGUI/`
- [ ] Compile installer with Inno Setup
- [ ] Test installer on a clean Windows machine
- [ ] Verify camera works (with Spinnaker SDK installed)
- [ ] Verify serial communication works

---

## Troubleshooting

### "PySpin not found" error
Users need to install FLIR Spinnaker SDK separately. The app will work in data-only mode without it.

### Large package size
This is normal due to Qt libraries (~100MB). Cannot be reduced significantly without removing features.

### Missing DLL errors
Run `pyinstaller build.spec --clean` to rebuild from scratch.
