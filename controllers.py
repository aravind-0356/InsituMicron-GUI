# controllers.py
"""
Dedicated controllers extracted from MainWindow.
Each controller is a QObject that owns a specific domain of logic.
"""
import os
import csv
import json
import time
import math

import pyqtgraph as pg

from PySide6.QtCore import QObject, QTimer, Signal, Slot, Qt, QThread
from PySide6.QtWidgets import QMessageBox, QProgressDialog

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from interfaces import SensorWorkerProtocol

from logging_config import get_logger
logger = get_logger(__name__)


# =========================================================
# ERROR MANAGER — Device error debounce
# =========================================================
class ErrorManager(QObject):
    """
    Collects device disconnection errors and shows a single consolidated
    popup after a 3-second debounce window.  If multiple devices report
    errors (hub unplug), one popup covers all of them.
    """

    def __init__(self, parent_widget):
        super().__init__(parent_widget)
        self._parent = parent_widget
        self._buffer = []           # List of (device_name, error_msg)
        self._last_flush_time = 0.0

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self._flush)

    def collect(self, device_name, error_msg):
        """Buffer a device error. Deduplicates by device name."""
        # Suppress late arrivals if a batch was shown within the last 5s
        if time.time() - self._last_flush_time < 5.0:
            logger.debug("%s error suppressed (recent flush): %s", device_name, error_msg)
            return

        existing = {e[0] for e in self._buffer}
        if device_name in existing:
            logger.debug("%s error skipped (duplicate): %s", device_name, error_msg)
            return

        self._buffer.append((device_name, error_msg))
        logger.error("%s error collected: %s", device_name, error_msg)

        if not self._timer.isActive():
            self._timer.start()

    def _flush(self):
        """Show consolidated or individual popup."""
        self._last_flush_time = time.time()
        errors = self._buffer.copy()
        self._buffer.clear()

        if not errors:
            return

        unique_names = list(dict.fromkeys(e[0] for e in errors))
        details = "\n\n".join(f"{name}:\n{msg}" for name, msg in errors)

        if len(unique_names) >= 2:
            msg_box = QMessageBox(self._parent)
            msg_box.setIcon(QMessageBox.Critical)
            msg_box.setWindowTitle("USB Hub Disconnected")
            msg_box.setText(
                f"Multiple devices lost connection simultaneously.\n\n"
                f"Affected: {', '.join(unique_names)}\n\n"
                f"Check the USB hub cable connection.")
            msg_box.setDetailedText(details)
            msg_box.setMinimumWidth(600)
            msg_box.setStyleSheet("QTextEdit { min-width: 550px; min-height: 300px; }")
            msg_box.exec()
        else:
            device_name, error_msg = errors[0]
            msg_box = QMessageBox(self._parent)
            msg_box.setIcon(QMessageBox.Critical)
            msg_box.setWindowTitle(f"{device_name} Disconnected")
            msg_box.setText(
                f"{device_name} lost connection.\n\n"
                f"Check the USB cable for this device.")
            msg_box.setDetailedText(error_msg)
            msg_box.setMinimumWidth(500)
            msg_box.setStyleSheet("QTextEdit { min-width: 450px; min-height: 200px; }")
            msg_box.exec()


# =========================================================
# DAQ CONTROLLER — DAQ lifecycle & hot-plug polling
# =========================================================
class DAQController(QObject):
    """Manages DAQ worker thread, hot-plug detection, and error handling."""

    def __init__(self, daq_worker, daq_thread, error_manager, main_window):
        super().__init__(main_window)
        self._worker = daq_worker
        self._thread = daq_thread
        self._error_mgr = error_manager
        self._mw = main_window
        self._conn_panel = main_window.conn_panel # Reference to the UI panel
        self._active = False

        # Hot-plug polling timer
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(3000)
        self._poll_timer.timeout.connect(self._auto_start)
        self._poll_timer.start()
        QTimer.singleShot(500, self._auto_start)

        # Connect signals
        self._worker.daq_error.connect(self.handle_error)
        self._worker.daq_connected.connect(self.on_daq_connected)
        self._worker.daq_diagnostic_info.connect(self.on_diagnostic_received)
        
        # Connect UI buttons
        self._conn_panel.daq_rescan_btn.clicked.connect(self.run_diagnostic)

    @property
    def is_active(self):
        return self._active

    @is_active.setter
    def is_active(self, value):
        self._active = value

    @property
    def worker(self):
        return self._worker

    @property
    def thread(self):
        return self._thread

    @Slot(str)
    def on_daq_connected(self, msg):
        """Signal callback from DAQ thread when device successfully initiates."""
        logger.info("DAQ connected: %s", msg)
        self._active = True
        self._poll_timer.stop()
        self._update_ui_connected(msg)

    @Slot(str)
    def on_diagnostic_received(self, text):
        """Update the diagnostic console in the Connection tab."""
        self._conn_panel.daq_console.append(f"[{time.strftime('%H:%M:%S')}] {text}")
        
        # Restart polling if diagnostic didn't result in a connection and 
        # it was stopped manually.
        if not self._active and not self._poll_timer.isActive():
            logger.info("DAQ diagnostic finished without connection: Restarting polling.")
            self._poll_timer.start()

    def _update_ui_connected(self, device_name):
        """Update the UI labels for a connected state."""
        self._conn_panel.daq_status_light.setStyleSheet("color: #2ecc71; font-size: 24px;") # Green
        self._conn_panel.daq_info_label.setText(f"Connected: {device_name}")
        self._conn_panel.daq_console.append(f"[{time.strftime('%H:%M:%S')}] system: Hardware initialized successfully.")

    def _update_ui_disconnected(self, reason="Not Detected"):
        """Update the UI labels for a disconnected state."""
        self._conn_panel.daq_status_light.setStyleSheet("color: #e74c3c; font-size: 24px;") # Red
        self._conn_panel.daq_info_label.setText(reason)

    def run_diagnostic(self):
        """Perform a full hardware and driver check (Non-blocking)."""
        self._poll_timer.stop() # Pause polling while we do manual check
        self._conn_panel.daq_console.clear()
        self._conn_panel.daq_console.append(f"[{time.strftime('%H:%M:%S')}] Requested hardware diagnostic...")
        self._worker._run_diagnostic_requested.emit()

    @Slot(str)
    def handle_error(self, error_msg):
        """Handle DAQ errors by updating UI and logs."""
        logger.error("DAQ Error: %s", error_msg)
        self._active = False
        self._update_ui_disconnected("Connection Lost")

        # Stop recording if active — prevents incomplete/unclosed CSV
        rec_note = ""
        if self._worker.is_recording():
            self._mw.stop_record()
            rec_note = "\nRecording was stopped to prevent data loss."

        self._error_mgr.collect("NI DAQ", f"{error_msg}{rec_note}")
        
        # Restart polling
        if not self._poll_timer.isActive():
            logger.info("DAQ Error: Restarting hot-plug polling timer.")
            self._poll_timer.start()

    def _auto_start(self):
        """Auto-detect and start DAQ. (Non-blocking request)"""
        if self._active:
            return

        # Only auto-start Uniaxial DAQ if system mode is Uniaxial
        if hasattr(self._mw, '_system_mode') and self._mw._system_mode != "Uniaxial":
            return
        
        from daq_handler import HAS_NIDAQMX
        if not HAS_NIDAQMX:
            # Silent return to avoid log noise on machines without drivers
            return

        # We request a start in 'silent' mode. If it fails to find device,
        # it won't pop up a critical dialog, just emit log/signals.
        QTimer.singleShot(0, lambda: self._worker.request_start(silent=True))

    def start(self):
        """Manually start DAQ acquisition."""
        from daq_handler import HAS_NIDAQMX
        if not HAS_NIDAQMX:
            QMessageBox.critical(
                self._mw, "Driver Not Found",
                "NI-DAQmx driver is not installed.\n\n"
                "Please install from ni.com and restart the application."
            )
            return
        QTimer.singleShot(0, lambda: self._worker.request_start(silent=False))

    def stop(self):
        """Stop DAQ acquisition."""
        self._active = False
        self._worker.stop_acquisition()

    def shutdown(self):
        """Clean shutdown of DAQ thread."""
        if self._active:
            self._worker.stop_acquisition()
        self._thread.quit()
        self._thread.wait()


from logging_config import get_user_config_dir

# =========================================================
# HOMING CONTROLLER — encoder-based homing state machine
# =========================================================
class HomingController(QObject):
    """Manages encoder-based homing logic and config persistence."""

    home_position_changed = Signal(object)  # Emits new home pos (int or None)
    motor_direction_request = Signal(int)    # Request motor direction change (1, -1, 0)

    HOME_CONFIG_FILE = os.path.join(get_user_config_dir(), "home_config.json")

    def __init__(self, serial_handler, uni_control, main_window):
        super().__init__(main_window)
        self._serial = serial_handler
        self._uni = uni_control
        self._mw = main_window

        self._current_encoder_pos = 0
        self._home_encoder_pos = None
        self._homing_active = False
        self._last_homing_cmd = ""
        self._current_raw_disp = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(20)
        self._timer.timeout.connect(self._homing_loop)

        self._load_config()

    def _load_config(self):
        """Load saved home position from JSON file."""
        try:
            if os.path.exists(self.HOME_CONFIG_FILE):
                with open(self.HOME_CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    self._home_encoder_pos = data.get("home_encoder_position")
                    logger.info("Loaded home position: %s", self._home_encoder_pos)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("Could not load home config: %s", e)
            self._home_encoder_pos = None

    def _save_config(self):
        """Save home position to JSON file."""
        try:
            with open(self.HOME_CONFIG_FILE, 'w') as f:
                json.dump({"home_encoder_position": self._home_encoder_pos}, f)
            logger.info("Saved home position: %s", self._home_encoder_pos)
        except IOError as e:
            logger.error("Could not save home config: %s", e)

    @property
    def home_position(self):
        return self._home_encoder_pos

    @property
    def current_raw_disp(self):
        return self._current_raw_disp

    @current_raw_disp.setter
    def current_raw_disp(self, val):
        self._current_raw_disp = val

    @staticmethod
    def pulses_to_mm(pulses):
        """Convert encoder pulses to mm: (pulses/10000) * (3/800)."""
        return (pulses / 10000.0) * (3.0 / 800.0)

    @Slot(int)
    def on_encoder_updated(self, pos):
        """Receive encoder pulse count from STM32."""
        self._current_encoder_pos = pos

    def set_home(self):
        """Capture current encoder value as the home position."""
        self._home_encoder_pos = self._current_encoder_pos
        self._save_config()
        self._uni.update_home_label(self._home_encoder_pos)
        mm = self.pulses_to_mm(self._home_encoder_pos)
        QMessageBox.information(
            self._mw, "Home Position Set",
            f"Home position saved successfully!\n{mm:.4f} mm ({self._home_encoder_pos:,} pulses)"
        )
        logger.info("Home position SET to encoder: %d", self._home_encoder_pos)

    def clear_home(self):
        """Clear saved home position after user confirmation."""
        if self._home_encoder_pos is None:
            QMessageBox.information(self._mw, "No Home Position", "No home position is currently set.")
            return
        mm = self.pulses_to_mm(self._home_encoder_pos)
        reply = QMessageBox.question(
            self._mw, "Clear Home Position",
            f"Are you sure you want to clear the home position?\nCurrent: {mm:.4f} mm ({self._home_encoder_pos:,} pulses)",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            old_pos = self._home_encoder_pos
            self._home_encoder_pos = None
            self._save_config()
            self._uni.update_home_label(None)
            logger.info("Home position CLEARED (was: %d)", old_pos)

    def start_homing(self, rpm):
        """Start encoder-based homing."""
        if self._home_encoder_pos is None:
            QMessageBox.warning(self._mw, "No Home Position",
                                "No home position is set. Click 'Set Home' first.")
            return
        if not self._serial.is_connected():
            QMessageBox.critical(self._mw, "Connection Error", "USB is disconnected!")
            return

        self._homing_active = True
        self._homing_rpm = abs(rpm)
        self._last_homing_cmd = ""
        self._homing_initial_diff_sign = None  # Will be set on first motor command
        self._uni.lbl_live_encoder.setVisible(True)
        self._timer.start()
        logger.info("Homing STARTED — target encoder: %d, speed: %d RPM",
                    self._home_encoder_pos, self._homing_rpm)

    def stop_homing(self):
        """Stop homing and halt motor."""
        self._homing_active = False
        self._timer.stop()
        self._serial.send_cmd("STOP")
        self.motor_direction_request.emit(0)
        self._uni.lbl_live_encoder.setVisible(False)
        logger.info("Homing STOPPED")

    def _homing_loop(self):
        """Timer-driven loop: monitor encoder position, stop when close."""
        if not self._homing_active:
            return
        curr = self._current_encoder_pos
        target = self._home_encoder_pos
        diff = curr - target

        curr_mm = self.pulses_to_mm(curr)
        self._uni.lbl_live_encoder.setText(f"Live Position: {curr_mm:.4f} mm ({curr:,} pulses)")
        if abs(diff) <= 5000:
            self.stop_homing()
            logger.info("Homing COMPLETE — encoder at %d (target: %d)", curr, target)
            QMessageBox.information(self._mw, "Homing Complete",
                                    f"Home position reached!\n{curr_mm:.4f} mm ({curr:,} pulses)")
            self._uni.lbl_live_encoder.setText(f"Encoder: {curr:,} pulses") # Added this line based on user's snippet, corrected placement
            return

        # Determine direction and command based on current position relative to target
        if self._current_encoder_pos < self._home_encoder_pos:
            cmd = f"VEL:{self._homing_rpm}"
            dir_val = 1
        else:
            cmd = f"VEL:-{self._homing_rpm}"
            dir_val = -1

        # Only send command if direction changes or it's the first command
        if cmd != self._last_homing_cmd:
            self._serial.send_cmd(cmd)
            self._serial.send_cmd("START")
            self.motor_direction_request.emit(dir_val)
            self._last_homing_cmd = cmd
            # The initial diff sign is used to detect if we've crossed the target.
            # This should be set when the motor *starts* moving in a particular direction.
            # If the command changes, the initial direction for this new segment of homing also changes.
            self._homing_initial_diff_sign = (diff > 0)

        if self._homing_initial_diff_sign is not None:
            current_sign = (diff > 0)
            if current_sign != self._homing_initial_diff_sign:
                self.stop_homing()
                logger.info("Homing COMPLETE (crossed target) — encoder at %d (target: %d)", curr, target)
                QMessageBox.information(self._mw, "Homing Complete",
                                        f"Home position reached!\n{curr_mm:.4f} mm ({curr:,} pulses)")
                return


# =========================================================
# PRELOAD CONTROLLER — preload sequencing
# =========================================================
class PreloadController(QObject):
    """Manages preload command sequencing for biaxial and uniaxial modes."""

    def __init__(self, serial_handler, data_worker: 'SensorWorkerProtocol', daq_worker: 'SensorWorkerProtocol', cdaq_worker: 'SensorWorkerProtocol', main_window):
        super().__init__(main_window)
        self._serial = serial_handler
        self._data_worker = data_worker
        self._daq_worker = daq_worker
        self._cdaq_worker = cdaq_worker
        self._mw = main_window
        self._sequence_cmds: list[tuple[str, int]] = []
        self._target_load = 0.0
        self._preload_type = ""

    def start_preload(self, mode, target, rpm):
        """Start biaxial preload."""
        self._target_load = target
        self._preload_type = f"Biaxial ({mode})"
        # Unfreeze plots when preload starts 
        self._data_worker.set_freeze_plots(False)
        self._daq_worker.set_freeze_plots(False)
        self._cdaq_worker.set_freeze_plots(False)

        if not self._serial.is_connected():
            QMessageBox.critical(self._mw, "Connection Error",
                                 "USB is disconnected! Please connect to the device.")
            return

        indices = []
        if mode == "X":
            indices = [2, 3]
        elif mode == "Y":
            indices = [0, 1]
        elif mode == "ALL":
            indices = [0, 1, 2, 3]

        self._sequence_cmds = []
        for i in indices:
            self._sequence_cmds.append((f"VEL{i + 1}:{rpm}", 10))
            self._sequence_cmds.append((f"STARTM{i + 1}", 10))

        self._cdaq_worker.request_configure_preload(target, indices)
        self._process_commands()

    def start_uni_preload(self, target, rpm):
        """Start preload on the single Uniaxial motor."""
        self._target_load = target
        self._preload_type = "Uniaxial"
        
        # Unfreeze plots when preload starts 
        self._data_worker.set_freeze_plots(False)
        self._daq_worker.set_freeze_plots(False)

        if not self._serial.is_connected():
            QMessageBox.critical(self._mw, "Connection Error",
                                 "USB is disconnected! Please connect to the device.")
            return

        current_load = self._daq_worker.get_current_load()
        speed = abs(rpm)
        velocity = speed if target > current_load else -speed

        self._serial.send_cmd(f"VEL:{velocity}")
        self._serial.send_cmd("START")
        self._daq_worker.set_motor_direction(1 if velocity > 0 else -1)

        self._daq_worker.request_configure_preload(target, [0])
        logger.info("Uniaxial PRELOAD armed - Target: %.1f N, Speed: %d RPM (auto-dir: %d)",
                    target, speed, velocity)

    def handle_daq_preload_finished(self):
        """DAQ detected preload target reached — stop the motor."""
        self._serial.send_cmd("STOP")
        self._daq_worker.set_motor_direction(0)
        logger.info("DAQ Preload target reached — motor STOPPED")
        
        QMessageBox.information(
            self._mw, "Preload Complete",
            f"Preload successful at {self._target_load} N.\nUniaxial motor stopped."
        )

    def handle_data_preload_finished(self):
        """cDAQWorker detected biaxial preload target reached."""
        logger.info("Biaxial Preload sequence COMPLETE.")
        
        QMessageBox.information(
            self._mw, "Preload Complete",
            f"Preload successful at {self._target_load} N.\n{self._preload_type} motor(s) stopped."
        )

    def _process_commands(self):
        """Send queued preload commands with delays."""
        if not self._sequence_cmds:
            return
        cmd, delay = self._sequence_cmds.pop(0)
        self._serial.send_cmd(cmd)
        if self._sequence_cmds:
            QTimer.singleShot(delay, self._process_commands)


# =========================================================
# EXCEL EXPORT WORKER (Background Thread)
# =========================================================
class ExcelExportWorker(QObject):
    """Runs CSV-to-Excel conversion on a background thread to prevent GUI freeze."""
    finished = Signal()
    error = Signal(str)

    def __init__(self, save_dir, sample_id, sample_type, system_mode,
                 width, thickness, radius, gauge_length, extra_dims):
        super().__init__()
        self._save_dir = save_dir
        self._sample_id = sample_id
        self._sample_type = sample_type
        self._system_mode = system_mode
        self._width = width
        self._thickness = thickness
        self._radius = radius
        self._gauge_length = gauge_length
        self._extra_dims = extra_dims

    @Slot()
    def run(self):
        try:
            from openpyxl import Workbook

            excel_path = os.path.join(self._save_dir, "test_results.xlsx")
            csv_path = os.path.join(self._save_dir, "test_result(csv format).csv")

            wb = Workbook()

            ws_data = wb.active
            ws_data.title = "Sensor Data"

            if os.path.exists(csv_path):
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    for row in reader:
                        ws_data.append(row)

            ws_params = wb.create_sheet("Sample Parameters")
            ws_params.append(["Parameter", "Value"])
            ws_params.append(["Sample ID", self._sample_id])
            ws_params.append(["Sample Type", self._sample_type])
            ws_params.append(["Mode", self._system_mode])

            if self._sample_type == "Rectangular":
                ws_params.append(["Width (mm)", self._width])
                ws_params.append(["Thickness (mm)", self._thickness])
                ws_params.append(["Gauge Length (mm)", self._gauge_length])
            elif self._sample_type == "Biaxial":
                ws_params.append(["Additional Dimensions", self._extra_dims])
            else:
                ws_params.append(["Radius (mm)", self._radius])
                ws_params.append(["Gauge Length (mm)", self._gauge_length])

            wb.save(excel_path)
            logger.info("Excel summary created: %s", excel_path)

            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


# =========================================================
# RECORDING CONTROLLER — start/stop, folder, CSV/Excel
# =========================================================
class RecordingController(QObject):
    """Manages recording lifecycle: validation, folder creation, CSV, Excel export."""

    recording_started = Signal()
    recording_stopped = Signal()

    def __init__(self, main_window, data_worker: 'SensorWorkerProtocol', daq_controller, cdaq_worker: 'SensorWorkerProtocol', camera_panel):
        super().__init__(main_window)
        self._mw = main_window
        self._data_worker = data_worker
        self._daq_ctrl = daq_controller
        self._cdaq_worker = cdaq_worker
        self._camera = camera_panel
        self.current_save_dir = ""
        self.manual_captures_dir = None
        self._is_recording = False

    def start_record(self):
        """Pre-selection validation and immediate folder/file creation."""
        mw = self._mw

        # VALIDATION: Check connection
        if mw._system_mode == "Uniaxial":
            if not self._daq_ctrl.is_active:
                QMessageBox.critical(
                    mw, "DAQ Not Connected",
                    "NI DAQ is not acquiring data.\n\n"
                    "Please start DAQ acquisition before recording."
                )
                return
        else:
            if not mw.serial_handler.is_connected():
                QMessageBox.critical(mw, "Connection Error",
                                     "USB is disconnected! Please connect to the device.")
                return

        # VALIDATION: Check camera stream if saving images
        if mw._save_images and not self._camera.is_live():
            QMessageBox.critical(mw, "Camera Error",
                                 "Camera feed is not live! Please start the stream in 'Image Setup' tab.")
            return

        # VALIDATION: Check if output folder has been selected
        if not mw._output_folder:
            QMessageBox.critical(
                mw, "No Output Folder Selected",
                "Please select an output folder in the Test Configuration screen before starting recording."
            )
            return

        # VALIDATION: Check at least one save option
        if not mw._save_sensor_data and not mw._save_images:
            QMessageBox.critical(
                mw, "No Save Options Selected",
                "Please select at least one save option (Sensor Data or Camera Images) in the Test Configuration screen."
            )
            return

        # Create timestamped test folder
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        test_folder_name = f"{mw._sample_id}_{timestamp}"
        self.current_save_dir = os.path.join(mw._output_folder, test_folder_name)

        try:
            os.makedirs(self.current_save_dir, exist_ok=True)
            
            # Always create Manual captures folder for the test session
            self.manual_captures_dir = os.path.join(self.current_save_dir, "Manual_Image_Captures")
            os.makedirs(self.manual_captures_dir, exist_ok=True)

            if mw._save_images:
                self.images_dir = os.path.join(self.current_save_dir, "Auto_Record_Image_Captures")
                os.makedirs(self.images_dir, exist_ok=True)
            else:
                self.images_dir = None
            logger.info("Created test folder: %s", self.current_save_dir)
        except Exception as e:
            QMessageBox.critical(mw, "Folder Creation Error", f"Failed to create test folder:\n{e}")
            return

        # Start Camera Recording
        if mw._save_images and self.images_dir:
            self._camera.worker.start_recording(self.images_dir)

        # Start Data Recording
        csv_path = ""
        if mw._save_sensor_data:
            csv_path = os.path.join(self.current_save_dir, "test_result(csv format).csv")

        if mw._system_mode == "Uniaxial" and self._daq_ctrl.is_active:
            self._daq_ctrl.worker.request_start_recording(csv_path)
        else:
            self._cdaq_worker.request_start_recording(csv_path, mw._system_mode)

        # Update UI
        mw.sensor_panel.set_recording_state(True)
        mw.dashboard_panel.bl_graph_combo.setEnabled(False)

        recording_info = []
        if mw._save_sensor_data:
            recording_info.append("Sensor Data")
        if mw._save_images:
            recording_info.append("Camera Images")
        logger.info("Recording started: %s", ', '.join(recording_info))
        mw.dashboard_panel.start_rec_timer()
        self._is_recording = True
        self.recording_started.emit()

    def stop_record(self):
        """Stop recording and close files, then create Excel summary."""
        mw = self._mw

        if mw._save_images:
            self._camera.worker.stop_recording()

        self._daq_ctrl.worker.stop_recording()
        self._data_worker.stop_recording()
        self._cdaq_worker.stop_recording()

        mw.sensor_panel.set_recording_state(False)
        mw.dashboard_panel.bl_graph_combo.setEnabled(True)
        mw.dashboard_panel.stop_rec_timer()

        if mw._save_sensor_data:
            self._run_excel_export()
        else:
            self._show_save_complete()

        self._is_recording = False
        self.manual_captures_dir = None
        self.recording_stopped.emit()

    def _run_excel_export(self):
        """Run Excel export in background thread with progress dialog."""
        mw = self._mw
        self._export_progress = QProgressDialog(
            "Exporting data to Excel...", None, 0, 0, mw)
        self._export_progress.setWindowTitle("Saving")
        self._export_progress.setMinimumWidth(320)
        self._export_progress.setMinimumDuration(0)
        self._export_progress.setCancelButton(None)
        self._export_progress.setModal(True)
        self._export_progress.show()

        self._export_thread = QThread()
        self._export_worker = ExcelExportWorker(
            self.current_save_dir, mw._sample_id, mw._sample_type,
            mw._system_mode, mw._sample_width, mw._sample_thickness,
            mw._sample_radius, mw._sample_gauge_length, mw._sample_extra_dims
        )
        self._export_worker.moveToThread(self._export_thread)
        self._export_thread.started.connect(self._export_worker.run)
        self._export_worker.finished.connect(self._on_export_finished)
        self._export_worker.error.connect(self._on_export_error)
        self._export_worker.finished.connect(self._export_thread.quit)
        self._export_worker.error.connect(self._export_thread.quit)
        self._export_thread.start()

    def _on_export_finished(self):
        """Called when Excel export completes successfully."""
        self._export_progress.close()
        self._show_save_complete()
        self._export_worker.deleteLater()
        self._export_thread.deleteLater()

    def _on_export_error(self, error_msg):
        """Called when Excel export fails."""
        self._export_progress.close()
        logger.error("Excel export error: %s", error_msg)
        self._show_save_complete()
        self._export_worker.deleteLater()
        self._export_thread.deleteLater()

    def _show_save_complete(self):
        """Show the recording saved popup."""
        mw = self._mw
        saved_items = []
        if mw._save_sensor_data:
            saved_items.append("Sensor data (Excel)")
        if mw._save_images:
            saved_items.append("Camera images")

        QMessageBox.information(
            mw, "Recording Saved",
            f"{' and '.join(saved_items)} saved to:\n\n{self.current_save_dir}"
        )
        logger.info("Recording stopped. All files closed.")


# =========================================================
# CAPTURE CONTROLLER — manual single-image capture
# =========================================================
class CaptureController(QObject):
    """Handles manual image capture: validation, folder creation, and save dispatch.
    
    Always saves to Manual_Captures/ subfolder inside the user's output folder,
    regardless of whether a recording is active.
    """

    capture_success = Signal(str)   # Emits the saved file path
    capture_error = Signal(str)     # Emits error message for status label

    def __init__(self, main_window, camera_panel, dashboard_panel=None):
        super().__init__(main_window)
        self._mw = main_window
        self._camera = camera_panel
        self._dashboard = dashboard_panel

    def capture_image(self):
        """Validate conditions and dispatch a single frame capture."""
        mw = self._mw

        # --- VALIDATION 1: Camera stream must be live ---
        if not self._camera.is_live():
            QMessageBox.warning(
                mw, "Camera Not Active",
                "Camera stream is not active.\n\n"
                "Please start the camera stream in the 'Image Setup' tab before capturing."
            )
            self.capture_error.emit("Stream not active")
            return

        # --- VALIDATION 2: Output folder must be set ---
        if not mw._output_folder:
            QMessageBox.warning(
                mw, "No Save Location",
                "No output folder selected.\n\n"
                "Please set a save location in the 'Test Configuration' tab."
            )
            self.capture_error.emit("No save location")
            return

        # --- VALIDATION 3: Output folder must still exist ---
        if not os.path.isdir(mw._output_folder):
            QMessageBox.warning(
                mw, "Save Location Invalid",
                "The selected output folder no longer exists.\n\n"
                "Please select a new save location in 'Test Configuration'."
            )
            self.capture_error.emit("Folder missing")
            return

        # --- Decide where to save based on recording state ---
        # If currently recording, save inside that test's specific manual captures folder
        if hasattr(mw, 'rec_ctrl') and mw.rec_ctrl._is_recording and mw.rec_ctrl.manual_captures_dir:
            captures_dir = mw.rec_ctrl.manual_captures_dir
        else:
            # Otherwise use global fallback folder in output dir
            captures_dir = os.path.join(mw._output_folder, "Manual_Image_Captures")
            try:
                os.makedirs(captures_dir, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(
                    mw, "Folder Creation Error",
                    f"Failed to create captures folder:\n{e}"
                )
                self.capture_error.emit("Folder creation failed")
                return

        # --- Generate unique filename ---
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        microseconds = f"{time.time() % 1:.6f}"[2:]  # Extract fractional part
        filename = f"capture_{timestamp}_{microseconds}.tiff"
        save_path = os.path.join(captures_dir, filename)

        # --- Brief button disable for feedback (200ms) on BOTH tabs ---
        if hasattr(self._camera, 'btn_capture'):
            self._camera.btn_capture.setEnabled(False)
            QTimer.singleShot(200, lambda: self._camera.btn_capture.setEnabled(True))
            
        if self._dashboard and hasattr(self._dashboard, 'btn_capture_dash'):
            self._dashboard.btn_capture_dash.setEnabled(False)
            QTimer.singleShot(200, lambda: self._dashboard.btn_capture_dash.setEnabled(True))

        # --- Dispatch capture to camera worker (thread-safe) ---
        self._camera.worker.request_capture(save_path)
        logger.info("Manual capture requested: %s", save_path)


# =========================================================
# GRAPH CONTROLLER — dashboard curves & graph type switching
# =========================================================
class GraphController(QObject):
    """Manages dashboard graph curves and data routing."""

    def __init__(self, main_window, dashboard_panel):
        super().__init__(main_window)
        self._mw = main_window
        self._dash = dashboard_panel

        self._bl_graph_mode = "Load vs Displacement"

        # Dashboard curves (initialized in setup_curves)
        self.uni_curve = None
        self.uni_ld_curve = None
        self.uni_dt_curve = None
        self.bi_curves = []

    def setup_curves(self, mode):
        """Clear and recreate dashboard curves for the given mode."""
        self._dash.plot_load_time.clear()
        self._dash.plot_load_disp.clear()
        self._dash.plot_disp_time.clear()
        self._dash.plot_bi_loads.clear()

        # Remove old legend
        legend = self._dash.plot_bi_loads.plotItem.legend
        if legend is not None:
            scene = legend.scene()
            if scene is not None:
                scene.removeItem(legend)
            self._dash.plot_bi_loads.plotItem.legend = None

        if mode == "Uniaxial":
            self.uni_curve = self._dash.plot_load_time.plot(
                pen=pg.mkPen(color='#2980b9', width=3)
            )
            self.uni_ld_curve = self._dash.plot_load_disp.plot(
                pen=pg.mkPen(color='#27ae60', width=3)
            )
            self.uni_dt_curve = self._dash.plot_disp_time.plot(
                pen=pg.mkPen(color='#e67e22', width=3)
            )
            self.bi_curves = []
        else:
            self._dash.plot_bi_loads.addLegend(labelTextSize='14pt', offset=(30, 30))
            self.uni_curve = None
            self.uni_ld_curve = None
            self.uni_dt_curve = None
            colors = ['#c0392b', '#27ae60', '#2980b9', '#8e44ad']
            self.bi_curves = [
                self._dash.plot_bi_loads.plot(
                    pen=pg.mkPen(color=c, width=3), name=f"Load {i + 1}")
                for i, c in enumerate(colors)
            ]

    def on_bl_graph_changed(self, mode):
        """Handle bottom-left graph switch between Load vs Disp and Stress vs Strain."""
        if mode == "Stress vs Strain" and self._mw._sample_type == "Biaxial":
            QMessageBox.warning(
                self._mw, "Not Available",
                "Stress vs Strain is not available for Biaxial sample type.\n"
                "Please select Rectangular or Circular sample type in Test Configuration."
            )
            self._dash.bl_graph_combo.blockSignals(True)
            self._dash.bl_graph_combo.setCurrentText("Load vs Displacement")
            self._dash.bl_graph_combo.blockSignals(False)
            self._dash._on_bl_graph_switch("Load vs Displacement")
            return
        self._bl_graph_mode = mode
        
        # If test is finished/idle but we have data in memory, instantly refresh the plot
        if self._mw._time_data:
            data = {
                "mode": "Biaxial" if self._mw._sample_type == "Biaxial" else "Uniaxial",
                "time": self._mw._time_data,
                "uni_L": self._mw._load_data,
                "uni_D": self._mw._disp_data,
                "bi_L": self._mw._bi_load_data,
                "_source": "internal_refresh"
            }
            self.update_graphs(data)

    def _get_cross_section_area(self):
        """Calculate cross-sectional area based on sample type."""
        if self._mw._sample_type == "Rectangular":
            return self._mw._sample_width * self._mw._sample_thickness
        elif self._mw._sample_type == "Circular":
            return math.pi * self._mw._sample_radius ** 2
        return 0.0

    @Slot(dict)
    def update_graphs(self, data):
        """Route plot data to the correct dashboard curves."""
        # Ignore serial-sourced data when DAQ is active
        if data.get("_source") == "serial" and self._mw.daq_ctrl.is_active:
            return

        if data["mode"] == "Uniaxial":
            # Main sensor page curve (handled by MainWindow)
            if self._mw.uni_curve is not None:
                self._mw.uni_curve.setData(data["time"], data["uni_L"])

            if self.uni_curve is not None:
                self.uni_curve.setData(data["time"], data["uni_L"])

            uni_d = data.get("uni_D", [])

            if self.uni_ld_curve is not None and uni_d:
                if self._bl_graph_mode == "Stress vs Strain":
                    area = self._get_cross_section_area()
                    gauge = self._mw._sample_gauge_length
                    if area > 0 and gauge > 0:
                        stress = [l / area for l in data["uni_L"]]
                        strain = [d / gauge for d in uni_d]
                        self.uni_ld_curve.setData(strain, stress)
                else:
                    self.uni_ld_curve.setData(uni_d, data["uni_L"])

            if self.uni_dt_curve is not None and uni_d:
                self.uni_dt_curve.setData(data["time"], uni_d)
        else:
            for i in range(4):
                if i < len(data["bi_L"]) and data["time"] and data["bi_L"][i]:
                    if i < len(self._mw.bi_curves) and self._mw.bi_curves[i] is not None:
                        self._mw.bi_curves[i].setData(data["time"], data["bi_L"][i])
                    if i < len(self.bi_curves) and self.bi_curves[i] is not None:
                        self.bi_curves[i].setData(data["time"], data["bi_L"][i])
