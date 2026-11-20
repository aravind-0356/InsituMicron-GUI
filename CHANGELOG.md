# Changelog

All notable changes to the InsituMicron GUI will be documented in this file.

## [3.2.1] — 2026-11-18

### Fixed
- **Displacement Safety Guard Spam & Ghost Value Prevention**:
  - Filtered out NI-DAQmx simulated devices (`is_simulated`) from `detect_daq_device()` in `daq_handler.py`, preventing offline synthetic signals from auto-starting acquisition when physical hardware is unplugged.
  - Added hysteresis deadbands to displacement lower and upper safety guards in `daq_handler.py` so ambient noise and boundary crossings do not trigger continuous modal dialog spam.
  - Added `_system_mode` gating to `daq_handler.py` and synchronized worker auto-polling in `gui.py` and `controllers.py` so Uniaxial DAQ guards do not falsely trigger during Biaxial operations.

## [3.2.0] — 2026-06-24

### Added
- **Analysis & Reporting Page**: Added a comprehensive analysis tab linked to a stateless mathematics engine (`MaterialAnalysisEngine`) with the following features:
  - **Specimen Parameter Settings**: Real-time cross-sectional area (mm²) and gauge length (mm) configurations.
  - **Automated Property Extraction**: Computes Young's Modulus, 0.2% Offset Yield Strength, Ultimate Tensile Strength (UTS), and Break Stress.
  - **Interactive Modulus Selector**: Renders a draggable shaded linear region overlaying the elastic range on the plot. Dragging the region allows the operator to manually override the elastic fit, triggering an instant recalculation of the modulus and yield strength.
  - **Detailed Graphical Indicators**: Plots the stress-strain curve, modulus fit line, 0.2% offset line, and highlights critical material milestones (Yield Point, UTS, Break Point) with custom markers.
  - **Operator Notes & Report Export**: Allows saving custom operator comments and generating a professional PDF report containing specimen parameters, calculated mechanical properties, notes, and the final stress-strain graph.
- **Scalebar Annotation Burning**: Integrated a scale bar utility mapping Navitar zoom barrel positions (0.7x to 4.5x) to empirical stage-micrometer calibration values (`pixels_per_mm`). When active, it burns a physical scale bar overlay onto saved TIFF frames. To avoid frame dropping, the annotation drawing is executed in a background daemon thread (`ImageSaveWorker`).
- **Manual Image Capture**: Added single-frame capture capability accessible via both the Image Setup and Test Dashboard tabs. Captures are timestamped to the microsecond (`capture_{timestamp}_{microseconds}.tiff`) and organized into a dedicated `Manual_Image_Captures` subdirectory under the active test session's output directory.
- **Dual-Protection Actuator Safety Latches**: Implemented a continuous load monitoring safeguard checking both:
  1. Tared load (protecting the specimen)
  2. Raw/non-tared load (protecting the load cell hardware itself from damage, even if the display was zeroed at high preloads)
  - Automatically triggers when the load cell reaches ±5000 N and the motor is driving towards the limit, locking direction and sending a `STOP` command to the serial interface.
- **Displacement Sensor Safety Latch & Warning**: Implemented a two-stage safety guard operating on raw LVDT displacement:
  - **Upper Safety Limit (> 9.5 mm)**: Triggers an automatic motor stop and blocks positive/compression travel when exceeded, requiring negative/tension travel to return the actuator to the safe range (0.5 mm to 9.5 mm).
  - **Lower Safety Warning (< 0.5 mm)**: Emits a single warning popup alerting the operator that the displacement sensor has lost physical contact with the specimen. This warning does not halt the motor, ensuring active tests are not disrupted.
- **Edmund Optics Coaxial Spot Light Controller**: Added `light_controller.py` to drive intensity via NI-DAQ AO0 (0–10 V DC). Runs on the main UI thread (instantaneous writes).
- **Preload Auto-Stop**: Integrated real-time load monitoring to stop the motor via serial once a target preload is reached.
- **Inno Setup Installer Metadata**: Configured `installer.iss` with publisher links, setup mutex (preventing concurrent setup processes), and proprietary EULA (`LICENSES/LICENSE.txt`) acceptance step.
- **Windows Executable Properties**: Embedded file properties (Company, File Version, Copyright) in the standalone executable using a `file_version_info.txt` descriptor with PyInstaller.

### Changed
- **Non-Administrator Execution Settings**: Migrated user settings file (`settings.json`) saving location from the local installation directory to the user-specific `%APPDATA%\InsituMicron GUI\config\` directory. This allows running the GUI without Administrator/Write permissions on the installation directory.
- **Python Environment Downgrade**: Migrated the virtual environment from Python 3.10 to ensure full compatibility with the proprietary Teledyne FLIR Spinnaker (`PySpin`) camera library.
- **Decoupled Architecture**: Decoupled the monolithic UI logic in `gui.py` into a clean, testable structure:
  - `controllers.py` handles high-level test run flow and recording state.
  - `daq_handler.py` runs continuous hardware-timed acquisition (1000 Hz) in a dedicated background thread (`QThread`).
  - `interfaces.py` specifies communication protocols between acquisition threads.
  - `theme.py` centralizes brand CSS stylesheet definitions.
- **Calibration Pipeline**: Implemented a 1000 Hz hardware-timed analog collection buffer with a 3-point median filter followed by a 50-sample moving average to eliminate raw signal jitter.

---

## [2.1.1] — Legacy (IIT Jammu Deployment)
- Original release using STM32 + ADS1115 (I2C ADC) over serial stream.
- Monolithic UI and styling architecture.
