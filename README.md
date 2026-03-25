# InsituMicron GUI — v2.1.1

> Desktop control & data acquisition GUI for the **InsituMicron in-situ mechanical testing system**.  
> Deployed at **IIT Jammu** for Biaxial and Uniaxial mechanical test rigs.

---

## Deployment Site

| Field | Details |
|-------|---------|
| **Institution** | IIT Jammu |
| **Rig Type** | Biaxial (primary), Uniaxial (secondary mode) |
| **Hardware** | STM32 microcontroller over USB-Serial |
| **Sensor Interface** | I2C load cell conditioners (Biaxial) / ADS1115 ADC (Uniaxial) |

---

## Hardware Architecture

### Biaxial Mode
- **Actuators**: 4 independent servo motors (Individual) + 2 axial axes (X and Y)
- **Load Sensing**: 4 I2C load cell conditioners connected to the STM32
  - Readings streamed over USB-Serial as parsed text packets
  - 4 independent load channels (one per actuator arm), each tare-able independently
- **Motor Control**: Per-motor velocity in mm/min, axial X/Y group control, and a **Preload** mode that auto-stops all motors once a target load (N) is reached
- **Velocity Limit**: Hard cap at ±10 mm/min (= 281 RPM axial); exceeding this triggers a blocking warning dialog
- **RPM Conversion**:
  - Individual motors: `RPM = (mm/min × 225) / 4`
  - Axial motors: `RPM = (mm/min × 225) / 8`

### Uniaxial Mode
- **Actuator**: Single-axis motor, velocity in RPM (-3000 to +3000)
- **Load Sensing**: STM32 reads load cell via ADS1115 (16-bit I2C ADC), transmitted over serial
- **Displacement Sensing**: STM32 reads LVDT/encoder via ADS1115, transmitted over serial
- **Homing**: Target position (mm) + Tolerance (mm) homing sequence controlled via serial commands (`VEL:`, `START`, `STOP`)

### Serial Protocol (both modes)
Commands sent as plain ASCII strings over USB-COM:

| Command | Effect |
|---------|--------|
| `VEL:<rpm>` | Set uniaxial motor velocity |
| `START` | Start uniaxial motor |
| `STOP` | Stop all uniaxial motors |
| `VEL1:<rpm>` ... `VEL4:<rpm>` | Set individual biaxial motor velocity |
| `STARTM1` ... `STARTM4` | Start individual motor |
| `STOPM1` ... `STOPM4` | Stop individual motor |
| `VELX:<rpm>` / `VELY:<rpm>` | Set axial velocities |
| `STARTX` / `STARTY` / `STOPX` / `STOPY` | Axial group control |

---

## GUI Features

### Test Dashboard — Uniaxial
- Live **Load (N)** display with Tare button
- Live **Displacement (mm)** display with Tare button
- Real-time **Load vs. Displacement** graph (pyqtgraph)
- Data recording to CSV (`Time(s)`, `Load(N)`, `Disp(mm)`)
- **Break Detection**: Monitors for a configurable load drop (N); auto-stops motor on specimen fracture
- **Sync Record at Start**: Auto-begins recording when motor starts

### Test Dashboard — Biaxial
- 4-channel live load display (color-coded per actuator), each independently tare-able
- **Tare All** button
- Real-time 4-channel **Load vs. Time** graph
- Same recording, break detection, and auto-record sync features as Uniaxial

### Other Tabs
- **Motor Control**: Mode selector (Uniaxial / Biaxial) → switches panel between single-axis and 4-axis controls
- **Image Setup**: FLIR Spinnaker camera live feed (if SDK installed)
- **Settings**: COM port selection, calibration parameters, sampling rate

---

## Data Acquisition Pipeline

```
STM32 Firmware
  └─ I2C load conditioners (Biaxial 4-ch load)
  └─ ADS1115 ADC (Uniaxial: load + disp)
       │  USB-Serial (ASCII packets)
       ▼
  DataWorker (QThread)
       │  Parses serial stream, applies zero offsets
       │  PySide6 Signal: ui_update (dict), plot_update (dict)
       ▼
  MainWindow (GUI thread)
       └─ Updates labels, graphs, CSV
```

---

## Software Architecture

| File | Role |
|------|------|
| `main.py` | Entry point, stylesheet, DPI scaling (v2.1.1, global stylesheet inlined) |
| `gui.py` | `MainWindow`: Tab layout, signal wiring, serial connection management |
| `gui_test_views.py` | All test view widgets: motor panels, sensor display, graph widget |
| `gui_panels.py` | Reusable panel components (image panel, plot helpers) |
| `serial_handler.py` | Serial port open/close, send_cmd, incoming data parsing |
| `settings.py` | JSON-based user settings persistence |
| `constants.py` | `PRIMARY_COLOR`, `ACCENT_COLOR` brand constants |
| `logging_config.py` | Rotating file logger setup |
| `dpi_scaling.py` | DPI-aware font/widget scaling utilities |
| `Biaxial_firmware.c` | STM32 firmware source (reference) |
| `Uniaxial_firmware.c` | STM32 uniaxial firmware source (reference) |

> **Note**: No `controllers.py`, `daq_handler.py`, `interfaces.py`, or `theme.py` modules exist in this version — these were introduced in V3.1.2.

---

## Requirements

- Python 3.10+
- See [`requirements.txt`](requirements.txt) for full dependency list

Key dependencies:

| Package | Purpose |
|---------|---------|
| `PySide6` | GUI framework |
| `pyserial` | USB-Serial communication with STM32 |
| `pyqtgraph` | Real-time plotting |
| `openpyxl` | Excel export |
| `PySpin` | FLIR Spinnaker camera (optional) |

> `PySpin` requires the [FLIR Spinnaker SDK](https://www.flir.com/products/spinnaker-sdk/) to be separately installed.

---

## Setup & Run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

---

## Build Installer

```bash
pyinstaller build.spec
# Then compile installer.iss with Inno Setup Compiler
```

---

## Version History

| Version | Branch | Notes |
|---------|--------|-------|
| **v2.1.1** | `v2.1.1` | This version — IIT Jammu, STM32 serial DAQ, Biaxial + Uniaxial |
| v3.1.2 | `v3.1.2` | IIT Patna — NI-DAQ USB-6001, stress-strain graphs, refactored architecture |

---

## License

Proprietary — Insitu Instruments Pvt. Ltd. All rights reserved.  
Copyright © 2025 Insitu Instruments.
