# InsituMicron GUI — v2.1.1

> Desktop control & data acquisition GUI for the **InsituMicron in-situ mechanical testing system**.  
> Supports **Uniaxial** and **Biaxial** test modes with NI-DAQ and serial firmware communication.

---

## Features

- **Biaxial & Uniaxial Test Dashboards** — Load vs. Displacement real-time graphs
- **NI-DAQ Integration** — USB-6001 for load cell and displacement sensor acquisition
- **Serial Firmware Control** — Real-time feedback over COM port
- **Excel Data Export** — Auto-generated sensor data sheets
- **DPI-Aware UI** — PySide6 interface with dynamic scaling

---

## Version History

| Version | Branch  | Notes |
|---------|---------|-------|
| v3.1.2  | `main`  | Current — Uniaxial mode, stress-strain, refactored controllers |
| **v2.1.1** | `v2.1.1` | This version — Biaxial/Uniaxial stable legacy release |

---

## Requirements

- Python 3.10+
- See [`requirements.txt`](requirements.txt) for full list

Key dependencies:
| Package | Purpose |
|---------|---------|
| `PySide6` | GUI framework |
| `nidaqmx` | NI-DAQ USB-6001 interface |
| `openpyxl` | Excel export |
| `pyserial` | Serial firmware communication |

---

## Setup & Run

```bash
# 1. Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the application
python main.py
```

---

## Build Installer

Uses PyInstaller + Inno Setup:

```bash
pyinstaller build.spec
# Then compile installer.iss with Inno Setup
```

---

## License

Proprietary — InsituMicron. All rights reserved.
