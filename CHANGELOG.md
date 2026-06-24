# Changelog

All notable changes to the InsituMicron GUI will be documented in this file.

## [3.2.0] — 2026-06-24

### Added
- **Stress vs. Strain Plotting**: Added a dropdown selector in the dashboard to switch between Load vs. Displacement and Stress vs. Strain plots. Added configuration for sample geometry parameters (cross-sectional area, gauge length) for rectangular/cylindrical samples.
- **Edmund Optics Coaxial Spot Light Controller**: Added `light_controller.py` to drive intensity via NI-DAQ AO0 (0–10 V DC). Runs on the main UI thread (instantaneous writes).
- **Safety Limits & Break Detection**: Implemented a continuous 5000 N hard load cell limit in the acquisition thread, automatically sending a `STOP` command to the motor serial interface if exceeded. Added configurable break-detection (load drop threshold over consecutive samples).
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
