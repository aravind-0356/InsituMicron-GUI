# InsituMicron GUI — v3.1.2

> Desktop control & data acquisition GUI for the **InsituMicron in-situ mechanical testing system**.  
> Supports **Uniaxial** and **Biaxial** test modes with real-time DAQ, FLIR camera control, and serial firmware communication.

---

## Features

- **Uniaxial Test Dashboard** — Load vs. Displacement and Stress vs. Strain graphs
- **NI-DAQ Integration** — USB-6001 for load cell and displacement sensor acquisition
- **FLIR Spinnaker Camera** — Live feed and image capture during tests
- **Serial Firmware Control** — Real-time feedback from Uniaxial/Biaxial firmware over COM port
- **Excel Data Export** — Auto-generates Sensor Data and Sample Parameters sheets
- **DPI-Aware UI** — PySide6 interface with dynamic scaling and custom theming

---

## Version History

| Version | Branch  | Notes |
|---------|---------|-------|
| **v3.1.2** | `main` | Current — Uniaxial mode, stress-strain graphs, refactored controllers |
| v2.1.1  | `v2.1.1` | Legacy — Biaxial/Uniaxial stable release |

---

## Requirements

- Python 3.10+
- See [`requirements.txt`](requirements.txt) for full list

Key dependencies:
| Package | Purpose |
|---------|---------|
| `PySide6` | GUI framework |
| `nidaqmx` | NI-DAQ USB-6001 interface |
| `PySpin` | FLIR Spinnaker camera SDK |
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

> **Note**: `PySpin` (FLIR Spinnaker SDK) must be installed separately from the [FLIR SDK installer](https://www.flir.com/products/spinnaker-sdk/).  
> **Note**: NI-DAQmx driver must be installed from [NI website](https://www.ni.com/en/support/downloads/drivers/download.ni-daq-mx.html).

---

## Build Installer

Uses PyInstaller + Inno Setup:

```bash
# Build executable
pyinstaller build.spec

# Then compile installer.iss with Inno Setup
```

See [`installer.iss`](installer.iss) for the Inno Setup script.

---

## Project Structure

```
InsituMicron-GUI/
├── main.py               # Entry point
├── gui.py                # Main window & UI layout
├── gui_panels.py         # Reusable UI panel components
├── gui_test_views.py     # Test mode views (Uniaxial/Biaxial dashboards)
├── controllers.py        # Business logic & state management
├── daq_handler.py        # NI-DAQ acquisition worker
├── serial_handler.py     # Serial port communication
├── interfaces.py         # Shared worker protocol definitions
├── settings.py           # User settings persistence
├── constants.py          # App-wide constants
├── logging_config.py     # Logging setup
├── dpi_scaling.py        # DPI-aware scaling utilities
├── theme.py              # UI theme & styling
├── config/               # Runtime configuration files
├── LICENSES/             # Third-party license files
├── build.spec            # PyInstaller build spec
└── installer.iss         # Inno Setup installer script
```

---

## License

Proprietary — InsituMicron. All rights reserved.
