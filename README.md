# InsituMicron GUI — v3.2

> Desktop control & data acquisition GUI for the **InsituMicron in-situ mechanical testing system**.  
> Deployed at **IIT Patna** for the Uniaxial mechanical test rig.

---

## Releases & Download

Pre-compiled standard installers for Windows are distributed via GitHub Releases.
- Visit the [Releases](https://github.com/aravind-0356/InsituMicron-GUI/releases) page to download the latest setup installer (`InsituMicron_GUI_v3.2_Setup.exe`).
- Run the installer to install the desktop application. Administrator access is no longer required to run the application (settings are saved to `%APPDATA%`).

---

## Deployment Site

| Field | Details |
|-------|---------|
| **Institution** | IIT Patna |
| **Rig Type** | Uniaxial (primary), Biaxial (legacy UI retained) |
| **Hardware** | NI-DAQ USB-6001 (sensors) + STM32 over USB-Serial (motor control) |
| **Sensor Interface** | NI-DAQmx hardware-timed analog acquisition (AI0: Load, AI1: LVDT Displacement) |
| **Illumination** | Edmund Optics SL162-WHIIC Coaxial Spot Light, controlled via NI-DAQ AO0 (0–10 V DC) |

---

## Key Changes from V2.1.1

| Area | V2.1.1 (IIT Jammu) | V3.2 (IIT Patna) |
|------|-------------------|-------------------|
| **Primary sensor interface** | STM32 + ADS1115 (I2C ADC), streamed over serial | NI-DAQ USB-6001 hardware-timed acquisition via `nidaqmx` |
| **Load channel** | ADS1115 on STM32, serial packet | NI-DAQ AI0 (differential), ±5V, calibrated via linear interpolation |
| **Displacement channel** | ADS1115 on STM32, serial packet | NI-DAQ AI1 (differential), LVDT ±5V, calibrated via linear interpolation |
| **Acquisition rate** | Serial poll rate (firmware-dependent) | Hardware-timed 1000 Hz continuous, with 50-sample moving average + median-3 filter |
| **Stress-Strain graph** | Not present | Added: dropdown to switch between **Load vs. Displacement** and **Stress vs. Strain** |
| **Graph in dashboard** | Not present | `pyqtgraph` live plot embedded in uniaxial test view |
| **Architecture** | Monolithic (`gui.py` owns all logic) | Refactored: `controllers.py` (business logic), `daq_handler.py` (DAQ worker), `interfaces.py` (shared protocol) |
| **Theme** | Global stylesheet inlined in `main.py` | Extracted to `theme.py` module |
| **App icon** | Not set at runtime | Loaded at startup via `resource_path()` for packaged exe compatibility |
| **Safety limit** | None | 5000 N hard safety limit — auto-stops motor at overload (compression or tension) via DAQ real-time read |
| **Preload logic** | Serial-only (firmware handles it) | DAQ-driven: load cell read by `DAQWorker` in real time, motor stopped via serial on target reached |

---

## Hardware Architecture

### Uniaxial Mode (Primary)

```
NI-DAQ USB-6001
  ├── AI0 (Differential): Load Cell Amplifier output → Load (N)
  │     Calibration: -10V → -9810N,  +10V → +9810N  (configurable in Settings)
  ├── AI1 (Differential): LVDT Conditioner output → Displacement (mm)
  │     Calibration: 2V → 0mm, 10V → 10mm  (configurable in Settings)
  └── AO0: Edmund Optics SL162-WHIIC Coaxial Spot Light intensity (0–10V DC)

STM32 (USB-Serial)
  └── Motor controller: VEL/START/STOP commands for single-axis servo
```

#### DAQ Signal Chain (per sample, 1000 Hz)
```
Raw voltage (AI0/AI1)
  → Linear interpolation (voltage → N or mm)
  → Median filter (window-3, per channel)
  → Moving average (window-50, per channel)
  → Tare offset subtracted
  → Rate-limited emission: UI @ 30 Hz, Plot @ 10 Hz
```

### Biaxial Mode (Legacy UI Retained)
- Same 4-motor + axial panel as V2.1.1 retained in UI (not the primary deployment target at IIT Patna)
- Biaxial sensor data still sourced from STM32 serial stream (unchanged from V2.1.1)

---

## New: Stress vs. Strain Graph

The uniaxial test dashboard now includes a **graph type selector**:

| Graph Type | X-Axis | Y-Axis |
|------------|--------|--------|
| Load vs. Displacement | Displacement (mm) | Load (N) |
| Stress vs. Strain | Strain (mm/mm or %) | Stress (MPa) |

**Stress and Strain calculations** are based on user-entered sample dimensions (cross-sectional area, gauge length). Sample types supported: Rectangular and Cylindrical.

> **Note**: Graph type is locked once recording begins to prevent mid-test data inconsistency.

---

## New: Light Intensity Control

A dedicated **Light Intensity Controller** module (`light_controller.py`) drives the **Edmund Optics SL162-WHIIC Coaxial Spot Light** via the NI-DAQ USB-6001 analog output.

| Parameter | Value |
|-----------|-------|
| **DAQ Channel** | AO0 (analog output) |
| **Voltage Range** | 0 V (off) – 10 V (max brightness) |
| **Control** | UI slider in the Image Setup tab |
| **Default** | 0 V (light off at startup) |
| **Shutdown** | Automatically resets to 0 V when the application closes |

**Design highlights**:
- Runs on the main thread — analog output writes are near-instantaneous (~1 ms), so no dedicated worker thread is needed.
- Completely independent of the DAQ acquisition task in `daq_handler.py`.
- Gracefully degrades if the NI-DAQmx driver or device is unavailable.

---

## DAQ Configuration (Settings Tab)

All DAQ parameters are user-configurable via the Settings tab and persisted in `config/`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `daq_device_name` | `Dev1` | NI-DAQ device name (auto-detected at startup) |
| `daq_load_channel` | `ai0` | Analog input channel for load cell |
| `daq_disp_channel` | `ai1` | Analog input channel for LVDT |
| `daq_sample_rate` | `1000` | Hardware acquisition rate (Hz) |
| `daq_terminal_config` | `DIFF` | Terminal config: `DIFF` (differential) or `RSE` |
| `daq_load_v_min/max` | `-10 / +10 V` | Voltage range for load calibration |
| `daq_load_n_min/max` | `-9810 / +9810 N` | Force range for load calibration |
| `daq_disp_v_min/max` | `2 / 10 V` | Voltage range for LVDT calibration |
| `daq_disp_mm_min/max` | `0 / 10 mm` | Displacement range for LVDT calibration |

---

## Safety Features (New in V3.2)

| Feature | Mechanism |
|---------|-----------|
| **5000 N Hard Safety Limit** | `DAQWorker` checks every sample. If load ≥ 5000 N (compression) or ≤ -5000 N (tension) AND motor is driving toward overload, serial `STOP` is sent immediately |
| **Break Detection** | Configurable load-drop threshold (N). Once peak load drops by ≥ threshold for 10 consecutive samples, motor is stopped and recording flagged |
| **Preload Auto-Stop** | `DAQWorker` monitors real-time load; stops motor via serial once load reaches target — independent of firmware |

---

## Software Architecture (Refactored)

| File | Role |
|------|------|
| `main.py` | Entry point, app icon loading, DPI scaling |
| `theme.py` | **[NEW]** Centralized global stylesheet (extracted from main.py) |
| `gui.py` | `MainWindow`: Tab layout, signal routing between controllers and views |
| `gui_test_views.py` | All test view widgets (motor panels, sensor display, graph with type selector) |
| `gui_panels.py` | Reusable panel components |
| `controllers.py` | **[NEW]** Business logic: `TestController`, `RecordingController` — decoupled from UI |
| `daq_handler.py` | **[NEW]** `DAQWorker` (QThread): NI-DAQmx continuous acquisition, filtering, calibration, CSV streaming |
| `light_controller.py` | **[NEW]** Edmund Optics spot light intensity control via NI-DAQ AO0 (0–10 V) |
| `interfaces.py` | **[NEW]** `SensorWorkerProtocol` TypedDict — shared interface contract between `DAQWorker` and `DataWorker` |
| `serial_handler.py` | Serial port open/close, send_cmd, incoming data parsing (motor only in Uniaxial) |
| `settings.py` | JSON settings with DAQ parameters (extended from V2.1.1) |
| `constants.py` | Brand colors |
| `logging_config.py` | Rotating file logger + `resource_path()` helper for bundled exe |
| `Biaxial_firmware.c` | STM32 biaxial firmware (reference) |
| `Uniaxial_firmware.c` | STM32 uniaxial firmware (reference) |

---

## Data Acquisition Pipeline

```
NI-DAQ USB-6001 (1000 Hz hardware-timed)
  └── AI0: Load Cell Amplifier
  └── AI1: LVDT Displacement Conditioner
       │  nidaqmx AnalogMultiChannelReader (batch reads, 100 samples/cycle)
       ▼
  DAQWorker (QThread)
       │  Calibrate → Median-3 → Moving Average-50 → Offset subtraction
       │  PySide6 Signal: ui_update @ 30 Hz, plot_update @ 10 Hz
       ▼
  MainWindow (GUI thread)
       └─ Updates labels, graphs, CSV (streamed, flush per row)

STM32 USB-Serial  →  DataWorker (QThread)  →  Biaxial sensor fallback
```

---

## Requirements

- Python 3.10+
- NI-DAQmx Runtime or Full Driver ([download from NI](https://www.ni.com/en/support/downloads/drivers/download.ni-daq-mx.html))
- See [`requirements.txt`](requirements.txt) for full dependency list

Key dependencies:

| Package | Purpose |
|---------|---------|
| `PySide6` | GUI framework |
| `nidaqmx` | NI-DAQ USB-6001 interface |
| `numpy` | Pre-allocated DAQ read buffers |
| `pyserial` | USB-Serial motor control (STM32) |
| `pyqtgraph` | Real-time Load/Stress-Strain plotting |
| `openpyxl` | Excel export (Sensor Data + Sample Parameters sheets) |
| `PySpin` | FLIR Spinnaker camera (optional) |

> `PySpin` requires the [FLIR Spinnaker SDK](https://www.flir.com/products/spinnaker-sdk/) separately.  
> `nidaqmx` Python package requires the NI-DAQmx C driver (`nicaiu.dll`) to be installed.

---

## Setup & Run

1. **Create and Activate Virtual Environment (Python 3.10)**:
   ```bash
   python -m venv venv310
   venv310\Scripts\activate
   ```
2. **Install Standard Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Install Spinnaker SDK & PySpin** (For FLIR camera support):
   - Install the FLIR Spinnaker SDK driver.
   - Download the PySpin wheel matching Python 3.10 and install it manually:
     ```bash
     pip install spinnaker_python-3.10.0.121-cp310-cp310-win_amd64.whl
     ```
4. **Run the Application**:
   ```bash
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

| Version | Branch | Deployment | Notes |
|---------|--------|------------|-------|
| v2.1.1 | `v2.1.1` | IIT Jammu | STM32 serial DAQ (ADS1115), Biaxial + Uniaxial |
| **v3.2** | `v3.2` | IIT Patna | NI-DAQ USB-6001, stress-strain graphs, light intensity control, refactored architecture |

---

## License

Proprietary — InsituMicron Pvt. Ltd. All rights reserved.  
Copyright © 2025 InsituMicron
