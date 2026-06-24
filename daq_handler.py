# daq_handler.py
"""
NI DAQ USB-6001 Data Acquisition Handler for Uniaxial System.

Acquires load cell and LVDT displacement sensor data via nidaqmx
continuous hardware-timed acquisition. Emits rate-limited Qt signals
for UI display, plotting, break detection, and CSV recording.

Thread-Safety Contract:
    - All cross-thread data passed via PySide6 Signal/Slot ONLY.
    - All list/array data in signal payloads is .copy()'d before emission.
    - Pre-allocated NumPy read buffer owned exclusively by DAQ thread.
    - No QMutex on hot path — atomic Python ops + Qt signal dispatch.
"""

import csv
import time
import threading
import statistics
import collections
import numpy as np
from PySide6.QtCore import QObject, Signal, Slot, QThread, QCoreApplication
from logging_config import get_logger
from settings import load_settings

logger = get_logger(__name__)

# Conditional import — app runs without NI-DAQmx driver (like PySpin pattern)
try:
    import nidaqmx
    from nidaqmx.constants import (
        AcquisitionType,
        TerminalConfiguration,
    )
    from nidaqmx.stream_readers import AnalogMultiChannelReader
    HAS_NIDAQMX = True
    NIDAQ_IMPORT_ERROR = None
except Exception as e:
    HAS_NIDAQMX = False
    NIDAQ_IMPORT_ERROR = str(e)
    # Log the full traceback if available
    import traceback
    logger.error("NI-DAQmx Import Failure:\n%s", traceback.format_exc())


def detect_daq_device():
    """
    Check if any NI DAQ device is connected.
    Also validates that the C-API (nicaiu.dll) is correctly installed.

    Returns:
        str or None: Device name (e.g. 'Dev1') if found, None otherwise.
    """
    if not HAS_NIDAQMX:
        return None
    try:
        system = nidaqmx.system.System.local()
        for dev in system.devices:
            # Skip cDAQ chassis and modules (they belong to the Biaxial system)
            if "cdaq" in dev.name.lower() or "cdaq" in dev.product_type.lower():
                continue
            if "9219" in dev.product_type:
                continue
                
            logger.info("DAQ device detected: %s (%s)", dev.name, dev.product_type)
            return dev.name
        return None
    except Exception as e:
        # Check for typical "DLL not found" errors
        err_str = str(e).lower()
        if "nicaiu" in err_str or "not found" in err_str or "loadlibrary" in err_str:
            logger.error("NI-DAQmx C API (nicaiu.dll) is missing or corrupted: %s", e)
        return None


def perform_full_daq_diagnostic():
    """
    Performs a comprehensive check of the NI-DAQmx environment.
    Returns a multi-line string with findings.
    """
    report = []
    report.append("--- NI-DAQmx Hardware Diagnostic ---")
    
    # 1. Python Environment Verification
    if not HAS_NIDAQMX:
        report.append("[FAIL] Python 'nidaqmx' library is NOT installed in the current environment.")
        if NIDAQ_IMPORT_ERROR:
            report.append(f"       Internal Error: {NIDAQ_IMPORT_ERROR}")
        report.append("       -> Resolution: Run 'pip install nidaqmx' or check your virtual environment.")
        return "\n".join(report)
    
    report.append("[PASS] Python 'nidaqmx' library is installed.")

    # 2. Driver/Library (nicaiu.dll) & Device Discovery
    try:
        system = nidaqmx.system.System.local()
        report.append("[PASS] NI-DAQmx C API (nicaiu.dll) detected and loaded.")
        
        devices = system.devices
        if not devices:
            report.append("[FAIL] No hardware devices detected via USB/PCI.")
            report.append("       -> Resolution: Check USB cable and ensure device is powered on.")
        else:
            report.append(f"[PASS] {len(devices)} device(s) found.")
            for i, dev in enumerate(devices):
                report.append(f"       Device {i+1}: {dev.name} ({dev.product_type})")
            
            # 3. Connection Test (Try to create a dummy task)
            try:
                with nidaqmx.Task() as test_task:
                    test_task.ai_channels.add_ai_voltage_chan(f"{devices[0].name}/ai0")
                    report.append(f"[PASS] Successfully opened a test task on {devices[0].name}.")
            except Exception as test_err:
                report.append(f"[FAIL] Could open device, but could NOT open task: {test_err}")
                report.append("       -> Note: This often happens if the device is busy in NI MAX.")
                
    except Exception as e:
        err_str = str(e).lower()
        if "nicaiu" in err_str or "not found" in err_str or "loadlibrary" in err_str:
            report.append("[FAIL] NI-DAQmx C API (nicaiu.dll) was NOT found.")
            report.append("       -> Resolution: Install NI-DAQmx Runtime or Full Driver from ni.com.")
        else:
            report.append(f"[CRITICAL] System Discovery error: {e}")
        
    return "\n".join(report)


# =========================================================
# CSV WRITER (Streaming — identical to gui.py CSVWriter)
# =========================================================
class DAQCSVWriter:
    """Streams data rows to CSV file in real-time during recording."""

    def __init__(self):
        self.csv_file = None
        self.csv_writer_obj = None
        self.is_open = False
        self.rows_written = 0

    def open_file(self, path, headers):
        try:
            self.csv_file = open(path, 'w', newline='', encoding='utf-8')
            self.csv_writer_obj = csv.writer(self.csv_file)
            self.csv_writer_obj.writerow(headers)
            self.csv_file.flush()
            self.is_open = True
            self.rows_written = 0
            logger.info("DAQ CSV file opened: %s", path)
            return True
        except Exception as e:
            logger.error("DAQ CSV open error: %s", e)
            return False

    def write_row(self, row_data):
        if not self.is_open or self.csv_writer_obj is None:
            return False
        try:
            self.csv_writer_obj.writerow(row_data)
            self.csv_file.flush()
            self.rows_written += 1
            return True
        except Exception as e:
            logger.error("DAQ CSV write error: %s", e)
            return False

    def close_file(self):
        if self.is_open and self.csv_file:
            try:
                self.csv_file.close()
                self.is_open = False
                logger.info("DAQ CSV file closed (%d rows)", self.rows_written)
            except Exception as e:
                logger.error("DAQ CSV close error: %s", e)


# =========================================================
# DAQ WORKER
# =========================================================
class DAQWorker(QObject):
    """
    NI DAQ USB-6001 acquisition worker.

    Runs on a dedicated QThread. Acquires analog voltages from load cell
    and LVDT displacement sensor via hardware-timed continuous sampling.
    Processes data (filter, calibrate) and emits rate-limited signals
    to the GUI thread.

    Signal interface matches DataWorker for seamless GUI integration.
    """

    # --- Signals (matching DataWorker interface) ---
    ui_update = Signal(dict)
    plot_update = Signal(dict)
    break_detected_stop = Signal(str)
    overload_detected = Signal(str)
    request_image_save = Signal()
    recording_error = Signal(str)
    preload_finished = Signal()

    daq_error = Signal(str)
    daq_connected = Signal(str)
    daq_diagnostic_info = Signal(str)  # New: specifically for the diagnostic console
    _start_requested = Signal(bool)  # Internal: thread-safe start dispatch
    _run_diagnostic_requested = Signal() # Internal: run diagnostic on worker thread
    _start_recording_requested = Signal(str, str)
    _configure_preload_requested = Signal(float, list)
    _reset_overload_requested = Signal()  # Internal: thread-safe overload latch reset

    # Noise tolerance for displacement ratchet enforcement (mm)
    _RATCHET_MARGIN = 0.05

    def __init__(self, serial_handler=None):
        super().__init__()
        self._serial = serial_handler
        self._start_requested.connect(self._handle_start)
        self._run_diagnostic_requested.connect(self.run_diagnostic_slot)
        self._start_recording_requested.connect(self.start_recording)
        self._configure_preload_requested.connect(self.configure_preload)
        self._reset_overload_requested.connect(self.reset_overload_latch)
        self._data_lock = threading.Lock()

        # --- DAQ Configuration (loaded from settings) ---
        settings = load_settings()
        self._device_name = settings.get("daq_device_name", "Dev1")
        self._load_channel = settings.get("daq_load_channel", "ai0")
        self._disp_channel = settings.get("daq_disp_channel", "ai1")
        self._sample_rate = settings.get("daq_sample_rate", 1000)
        self._terminal_config = settings.get("daq_terminal_config", "DIFF")

        # --- Calibration (linear interpolation) ---
        self._load_v_min = settings.get("daq_load_v_min", -10.0)
        self._load_v_max = settings.get("daq_load_v_max", 10.0)
        self._load_n_min = settings.get("daq_load_n_min", -9810.0)
        self._load_n_max = settings.get("daq_load_n_max", 9810.0)

        self._disp_v_min = settings.get("daq_disp_v_min", 2.0)
        self._disp_v_max = settings.get("daq_disp_v_max", 10.0)
        self._disp_mm_min = settings.get("daq_disp_mm_min", 0.0)
        self._disp_mm_max = settings.get("daq_disp_mm_max", 10.0)

        # --- Acquisition State ---
        self._running = False
        self._task = None
        self._task_counter = 0  # Unique task name counter
        self._batch_size = 100  # Samples per read cycle (100ms at 1000Hz)

        # --- Filtered Values (Python floats — immutable, thread-safe to read) ---
        self._load_filtered = 0.0
        self._disp_filtered = 0.0

        # --- Offsets (zero correction) ---
        self._load_offset = 0.0
        self._disp_offset = 0.0

        # --- Median Buffers (Window-3) ---
        self._load_med_buf = collections.deque(maxlen=3)
        self._disp_med_buf = collections.deque(maxlen=3)

        # --- Moving Average Buffers (Window-50) ---
        self._load_avg_buf = collections.deque(maxlen=50)
        self._disp_avg_buf = collections.deque(maxlen=50)
        self._load_running_sum = 0.0
        self._disp_running_sum = 0.0

        # --- Rate Limiting ---
        self._last_ui_update = 0.0
        self._last_plot_update = 0.0

        # --- Plot Buffers (rolling, bounded) ---
        self._time_data = []
        self._load_data = []
        self._disp_data = []
        self._max_plot_buffer_size = 10000

        # --- Recording State ---
        self._is_recording = False
        self._start_time = 0.0
        self._sampling_rate = settings.get("sampling_rate", 4)  # CSV recording rate
        self._rec_decimation = max(1, self._sample_rate // self._sampling_rate)
        self._csv_writer = None
        self._rec_sample_counter = 0     # Counts HW samples for recording decimation
        self._rec_total_snapshots = 0    # Total snapshots taken (for precise timestamp)

        # --- Break Detection (atomic flags — no mutex) ---
        self._break_detection_enabled = False
        self._break_drop_threshold = 1000.0
        self._peak_load = 0.0
        self._break_persist_count = 0

        # --- Preload Logic ---
        self._preload_active = False
        self._preload_target = 0.0
        self._preload_persist_count = 0
        
        # --- Safety Limit Latch ---
        self._overload_fired = False
        self._motor_direction = 0  # 1 (Compression), -1 (Tension), 0 (Stopped)
        
        # --- Displacement Safety Guard ---
        self._disp_upper_limit = settings.get("disp_safety_upper_mm", 9.5)
        self._disp_upper_warned = False

        self._disp_lower_limit = settings.get("disp_safety_lower_mm", 0.5)
        self._disp_lower_warned = False

        self._encoder_pos = 0
        self._encoder_limit_warned = False

        self._freeze_plots = False

    @Slot(bool)
    def set_freeze_plots(self, freeze):
        self._freeze_plots = freeze

    # =========================================================
    # CALIBRATION: Voltage → Engineering Units
    # =========================================================

    def _voltage_to_load(self, voltage):
        """Linear interpolation: voltage → force (N)."""
        v_range = self._load_v_max - self._load_v_min
        if v_range == 0:
            return 0.0
        ratio = (voltage - self._load_v_min) / v_range
        return self._load_n_min + ratio * (self._load_n_max - self._load_n_min)

    def _voltage_to_disp(self, voltage):
        """Linear interpolation: voltage → displacement (mm)."""
        v_range = self._disp_v_max - self._disp_v_min
        if v_range == 0:
            return 0.0
        ratio = (voltage - self._disp_v_min) / v_range
        return self._disp_mm_min + ratio * (self._disp_mm_max - self._disp_mm_min)

    # =========================================================
    # DAQ LIFECYCLE
    # =========================================================

    @Slot(bool)
    def _handle_start(self, silent):
        """Slot that runs on DAQ thread — invoked via signal."""
        self.start_acquisition(silent=silent)

    def request_start(self, silent=False):
        """Thread-safe: emit signal to start acquisition on DAQ thread."""
        self._start_requested.emit(silent)

    @Slot()
    def start_acquisition(self, silent=False):
        """
        Start continuous DAQ acquisition.

        Args:
            silent: If True, don't emit daq_error on failure (for auto-start).
                    Errors are still logged.
        """
        if not HAS_NIDAQMX:
            msg = ("NI-DAQmx driver not installed.\n\n"
                   "Please install the NI-DAQmx driver from ni.com "
                   "and ensure the 'nidaqmx' Python package is installed.")
            logger.warning(msg)
            if not silent:
                self.daq_error.emit(msg)
            return

        if self._running:
            logger.warning("DAQ acquisition already running")
            return

        # Check device exists before creating Task
        detected = detect_daq_device()
        if detected is None:
            msg = f"No NI DAQ device found (expected '{self._device_name}')."
            logger.warning(msg)
            if not silent:
                self.daq_error.emit(msg)
            return

        # Dynamically update device name to the one found by the OS
        self._device_name = detected
        self._overload_fired = False  # Reset safety latch for new session
        self._disp_upper_warned = False
        self._disp_lower_warned = False

        try:
            self._setup_task()
            self._running = True
            logger.info("DAQ acquisition started on %s (Rate: %d Hz, Batch: %d)",
                        self._device_name, self._sample_rate, self._batch_size)
            self.daq_connected.emit(f"DAQ: {self._device_name}")
            self._acquisition_loop()
        except nidaqmx.errors.DaqError as e:
            self._running = False
            self._cleanup_task()
            error_msg = f"DAQ Error: {e}"
            logger.error(error_msg)
            self.daq_error.emit(error_msg)
        except Exception as e:
            self._running = False
            self._cleanup_task()
            error_msg = f"DAQ unexpected error: {e}"
            logger.error(error_msg)
            self.daq_error.emit(error_msg)

    def _safe_stop(self):
        """Safely send STOP command, guarding against None serial_handler."""
        if self._serial is not None:
            self._serial.send_cmd("STOP")
        else:
            logger.error("STOP command suppressed — no serial handler! Hardware may be unprotected.")

    def _setup_task(self):
        """Configure nidaqmx Task with differential channels and hardware timing."""
        # Reset device to flush any stale resources from previous sessions
        try:
            self.daq_diagnostic_info.emit(f"system: Resetting device '{self._device_name}'...")
            device = nidaqmx.system.System.local().devices[self._device_name]
            device.reset_device()
            logger.info("DAQ device '%s' reset before task setup", self._device_name)
            self.daq_diagnostic_info.emit("system: Device reset complete.")
        except Exception as e:
            logger.warning("DAQ device reset failed (non-fatal): %s", e)
            self.daq_diagnostic_info.emit(f"warn: Device reset failed: {e}")

        # Resolve terminal configuration
        if self._terminal_config == "DIFF":
            term_cfg = TerminalConfiguration.DIFF
        else:
            term_cfg = TerminalConfiguration.RSE

        self._task_counter += 1
        task_name = f"UniaxialDAQ_{self._task_counter}"
        self.daq_diagnostic_info.emit(f"system: Creating Task '{task_name}'...")
        self._task = nidaqmx.Task(task_name)

        # Channel 1: Load cell — AI0(+) / AI4(-)
        load_phys = f"{self._device_name}/{self._load_channel}"
        self.daq_diagnostic_info.emit(f"config: Adding Load channel {load_phys}...")
        self._task.ai_channels.add_ai_voltage_chan(
            load_phys,
            name_to_assign_to_channel="Load",
            terminal_config=term_cfg,
            min_val=-5.0,
            max_val=5.0,
        )

        # Channel 2: LVDT displacement — AI1(+) / AI5(-)
        disp_phys = f"{self._device_name}/{self._disp_channel}"
        self.daq_diagnostic_info.emit(f"config: Adding Displacement channel {disp_phys}...")
        self._task.ai_channels.add_ai_voltage_chan(
            disp_phys,
            name_to_assign_to_channel="Displacement",
            terminal_config=term_cfg,
            min_val=-5.0,
            max_val=5.0,
        )

        # Hardware timing — continuous acquisition
        self._task.timing.cfg_samp_clk_timing(
            rate=self._sample_rate,
            sample_mode=AcquisitionType.CONTINUOUS,
            samps_per_chan=self._batch_size * 4,  # Buffer 4x batch for headroom
        )

        # Pre-allocate NumPy read buffer — reused every cycle, NEVER emitted
        self._read_buffer = np.zeros(
            (2, self._batch_size), dtype=np.float64
        )

        # Create stream reader for efficient multi-channel reads
        self._reader = AnalogMultiChannelReader(self._task.in_stream)

        logger.info("DAQ Task configured: %s, %s (Terminal: %s)",
                     load_phys, disp_phys, self._terminal_config)

    # =========================================================
    # ACQUISITION LOOP (Hot Path)
    # =========================================================

    def _acquisition_loop(self):
        """
        Main acquisition loop. Reads batches from DAQ, processes, emits signals.

        Runs on DAQ thread. Exits when _running is set to False.
        """
        while self._running:
            try:
                # Read batch into pre-allocated buffer (C-backed, releases GIL)
                self._reader.read_many_sample(
                    self._read_buffer,
                    number_of_samples_per_channel=self._batch_size,
                    timeout=2.0,
                )

                # Process each sample in the batch
                current_time = time.perf_counter()
                for i in range(self._batch_size):
                    v_load = self._read_buffer[0, i]
                    v_disp = self._read_buffer[1, i]

                    # Calibrate: voltage → engineering units
                    raw_load = self._voltage_to_load(v_load)
                    raw_disp = self._voltage_to_disp(v_disp)

                    # Median filter (Window-3) — per channel
                    self._load_med_buf.append(raw_load)
                    load_median = sorted(self._load_med_buf)[len(self._load_med_buf) // 2]

                    self._disp_med_buf.append(raw_disp)
                    disp_median = sorted(self._disp_med_buf)[len(self._disp_med_buf) // 2]

                    # Moving Average (Window-50) — smooths continuous noise
                    if len(self._load_avg_buf) == self._load_avg_buf.maxlen:
                        self._load_running_sum -= self._load_avg_buf[0]
                    self._load_avg_buf.append(load_median)
                    self._load_running_sum += load_median
                    
                    if len(self._disp_avg_buf) == self._disp_avg_buf.maxlen:
                        self._disp_running_sum -= self._disp_avg_buf[0]
                    self._disp_avg_buf.append(disp_median)
                    self._disp_running_sum += disp_median
                    
                    with self._data_lock:
                        self._load_filtered = self._load_running_sum / len(self._load_avg_buf)
                        self._disp_filtered = self._disp_running_sum / len(self._disp_avg_buf)
                        
                        bd_enabled = self._break_detection_enabled
                        bd_thresh = self._break_drop_threshold
                        pl_active = self._preload_active
                        pl_target = self._preload_target
                        
                        current_val = self._load_filtered - self._load_offset  # tared
                        raw_load = self._load_filtered                          # non-tared (hardware protection)
                        
                        motor_dir = self._motor_direction
                        overload_already_fired = self._overload_fired
                        
                        is_pos_overload = (current_val >= 5000.0 or raw_load >= 5000.0) and motor_dir > 0
                        is_neg_overload = (current_val <= -5000.0 or raw_load <= -5000.0) and motor_dir < 0
                        
                        overload_triggered = False
                        if (is_pos_overload or is_neg_overload) and not overload_already_fired:
                            self._overload_fired = True
                            self._motor_direction = 0
                            overload_triggered = True

                    # --- 5000N Hard Safety Limit ---
                    # Fires when the motor is ACTIVELY driving into the limit (strictly non-zero direction).
                    # Checks BOTH tared (specimen protection) and raw/non-tared (hardware protection).
                    # This prevents the load cell from being damaged even if the user has zeroed
                    # at a large preload, which would shift the 'safe' displayed range beyond hardware limits.
                    # Both STOP and popup are gated behind _overload_fired (fires once per motor start).
                    
                    if overload_triggered:
                        self._safe_stop()
                        limit_type = "COMPRESSION" if is_pos_overload else "TENSION"
                        logger.warning("LOAD OVERLOAD (%s): tared=%.1f N, raw=%.1f N — STOP sent",
                                       limit_type, current_val, raw_load)
                        self.overload_detected.emit(
                            f"OVERLOAD ({limit_type}): Safety Limit Reached!\n"
                            f"Load (displayed): {current_val:.1f} N  |  Load (raw): {raw_load:.1f} N\n"
                            f"Limit: \u00b15000.0 N"
                        )

                    # --- Displacement Safety Guard (Uniaxial Only) ---
                    # Operates on raw (non-tared) displacement.
                    raw_disp = self._disp_filtered
                    motor_dir = self._motor_direction

                    # -- Upper Limit (> 9.5mm) --
                    if raw_disp >= self._disp_upper_limit:
                        if motor_dir > 0:  # Compression (positive) is BLOCKED
                            self._safe_stop()
                            with self._data_lock:
                                self._motor_direction = 0
                            if not self._disp_upper_warned:
                                self._disp_upper_warned = True
                                self.overload_detected.emit(
                                    f"DISPLACEMENT LIMIT: Upper bound exceeded!\n"
                                    f"Displacement: {raw_disp:.2f} mm (limit: {self._disp_upper_limit:.1f} mm)\n"
                                    f"Please move in Tension (negative) direction to return to the safe range (0.5mm to 9.5mm non-tared)."
                                )
                        elif motor_dir < 0:
                            self._disp_upper_warned = False
                    else:
                        self._disp_upper_warned = False

                    # -- Lower Limit (< 0.5mm) --
                    if raw_disp <= self._disp_lower_limit:
                        # DO NOT STOP THE MOTOR. Just warn the user once.
                        if not self._disp_lower_warned:
                            self._disp_lower_warned = True
                            self.overload_detected.emit(
                                f"WARNING: Displacement sensor lost contact and lower safety limit exceeded!\n"
                                f"Current: {raw_disp:.2f} mm. Safe range is 0.5mm to 9.5mm (non-tared)."
                            )
                    else:
                        self._disp_lower_warned = False

                    # --- Break Detection (every sample, atomic flags) ---
                    if bd_enabled:
                        # current_val is the tared load shown on the UI
                        current_mag = abs(current_val)
                        self._peak_load = max(self._peak_load, current_mag)
                        drop = self._peak_load - current_mag

                        if drop > bd_thresh:
                            self._break_persist_count += 1
                            if self._break_persist_count > 10:
                                with self._data_lock:
                                    self._break_detection_enabled = False
                                self._safe_stop()
                                # Emit break signal — GUI slot will handle UI updates
                                self.break_detected_stop.emit(
                                    f"Break Detected! Drop: {drop:.1f} N"
                                )
                        else:
                            self._break_persist_count = 0

                    # --- Preload Check (with persistence counter) ---
                    if pl_active:
                        stop = False
                        if pl_target >= 0:
                            if current_val >= pl_target: stop = True
                        else:
                            if current_val <= pl_target: stop = True

                        if stop:
                            self._preload_persist_count += 1
                            # Require N consecutive samples over target to debounce noise spikes
                            if self._preload_persist_count >= 5:
                                with self._data_lock:
                                    self._preload_active = False
                                self._safe_stop()
                                logger.info("DAQ Preload target met via load cell.")
                                self.preload_finished.emit()
                        else:
                            self._preload_persist_count = 0

                    # --- Recording (sample-count-based for precise timing) ---
                    if self._is_recording:
                        self._rec_sample_counter += 1
                        # Decimate: record every N-th HW sample
                        if self._rec_sample_counter >= self._rec_decimation:
                            self._rec_sample_counter = 0
                            self._record_snapshot()

                # --- Rate-Limited Signal Emissions (after batch) ---
                current_time = time.perf_counter()

                # UI update (~30 Hz = every 33ms)
                if current_time - self._last_ui_update >= 0.033:
                    self._emit_ui_update()
                    self._last_ui_update = current_time

                # Plot update (~10 Hz = every 100ms)
                if current_time - self._last_plot_update >= 0.1 and not self._freeze_plots:
                    self._emit_plot_update()
                    self._last_plot_update = current_time

                # Process pending Qt signals (start_recording, configure_preload, etc.)
                QCoreApplication.processEvents()

            except nidaqmx.errors.DaqError as e:
                if self._running:
                    self._running = False
                    error_msg = f"DAQ read error: {e}"
                    logger.error(error_msg)
                    self.daq_error.emit(error_msg)
                break
            except Exception as e:
                if self._running:
                    self._running = False
                    error_msg = f"DAQ unexpected error: {e}"
                    logger.error(error_msg)
                    self.daq_error.emit(error_msg)
                break

        # Cleanup
        self._cleanup_task()

    def _cleanup_task(self):
        """Stop and close the nidaqmx Task. Robust against disconnected hardware."""
        if self._task is not None:
            try:
                self._task.stop()
            except Exception:
                pass  # Device may already be gone
            try:
                self._task.close()
            except Exception:
                pass  # Device may already be gone
            logger.info("DAQ Task stopped and closed")
            self._task = None
            self._reader = None

    @Slot()
    def stop_acquisition(self):
        """Stop DAQ acquisition. Called via signal from GUI thread."""
        self._running = False
        logger.info("DAQ stop requested")

    def is_acquiring(self):
        """Return True if DAQ is actively acquiring."""
        return self._running

    @Slot()
    def run_diagnostic_slot(self):
        """Runs the exhaustive hardware diagnostic on the DAQ worker thread (non-blocking)."""
        report = perform_full_daq_diagnostic()
        self.daq_diagnostic_info.emit(report)
        
        # After diagnostic, try to actually start acquisition
        if detect_daq_device():
            self.start_acquisition(silent=True)

    # =========================================================
    # SIGNAL EMISSION (Thread-Safe — .copy() on all lists)
    # =========================================================

    def _emit_ui_update(self):
        """Emit UI update signal with immutable scalar values."""
        # Dict contains only Python floats (immutable) — inherently thread-safe
        data = {
            # NOTE: "_source" key is intentionally ABSENT here. DataWorker adds
            # "_source": "serial" so MainWindow can filter serial data when DAQ
            # is active. If you add "_source": "serial" here, DAQ data will be
            # silently filtered out of graphs. See interfaces.py for full docs.
            "mode": "Uniaxial",
            "uni_load": self._load_filtered - self._load_offset,
            "uni_disp": self._disp_filtered - self._disp_offset,
            "bi_loads": [0.0, 0.0, 0.0, 0.0],  # Compatibility with existing UI
            "bi_errors": [False, False, False, False],
            "uni_zero_L": self._load_offset,
            "uni_zero_D": self._disp_offset,
            "bi_zeros": [0.0, 0.0, 0.0, 0.0],
        }
        self.ui_update.emit(data)

    def _emit_plot_update(self):
        """Emit plot update with .copy() of rolling buffers."""
        # CRITICAL: .copy() prevents race condition with GUI thread
        data = {
            # NOTE: "_source" key intentionally absent — see _emit_ui_update.
            "mode": "Uniaxial",
            "time": self._time_data.copy(),
            "uni_L": self._load_data.copy(),
            "uni_D": self._disp_data.copy(),
            "bi_L": [[], [], [], []],  # Compatibility
        }
        self.plot_update.emit(data)

    # =========================================================
    # RECORDING (CSV Streaming)
    # =========================================================

    def _record_snapshot(self):
        """Record one data point. Timestamp from sample count for precision."""
        self._rec_total_snapshots += 1
        t_rel = self._rec_total_snapshots / self._sampling_rate  # Perfectly spaced
        load = self._load_filtered - self._load_offset
        disp = self._disp_filtered - self._disp_offset

        # Add to plot buffers
        self._time_data.append(t_rel)
        self._load_data.append(load)
        self._disp_data.append(disp)

        # Rolling window: trim if too large
        if len(self._time_data) > self._max_plot_buffer_size:
            trim_count = self._max_plot_buffer_size // 5
            self._time_data = self._time_data[trim_count:]
            self._load_data = self._load_data[trim_count:]
            self._disp_data = self._disp_data[trim_count:]

        # Stream to CSV
        if self._csv_writer and self._csv_writer.is_open:
            if not self._csv_writer.write_row(
                [f"{t_rel:.3f}", f"{load:.2f}", f"{disp:.4f}"]
            ):
                self._is_recording = False
                self.recording_error.emit(
                    "CSV write failed — recording stopped to prevent data loss"
                )
                return

        # Trigger image save
        self.request_image_save.emit()

    def request_start_recording(self, csv_path, mode="Uniaxial"):
        """Thread-safe request to start recording."""
        self._start_recording_requested.emit(csv_path, mode)

    @Slot(str, str)
    def start_recording(self, csv_path, mode="Uniaxial"):
        """Start recording with CSV file. Called via signal from GUI thread."""
        with self._data_lock:
            self._peak_load = 0.0
            self._time_data.clear()
            self._load_data.clear()
            self._disp_data.clear()
            self._load_med_buf.clear()
            self._disp_med_buf.clear()
            self._load_avg_buf.clear()
            self._disp_avg_buf.clear()
            self._load_running_sum = 0.0
            self._disp_running_sum = 0.0

            self._csv_writer = DAQCSVWriter()
            headers = ["Time(s)", "Load(N)", "Disp(mm)"]

            if csv_path:
                if not self._csv_writer.open_file(csv_path, headers):
                    logger.error("Failed to open DAQ CSV file")
                    return
            else:
                logger.info("DAQ recording started without CSV (images only)")

            self._start_time = time.time()
            self._rec_sample_counter = 0
            self._rec_total_snapshots = 0
            self._is_recording = True
            logger.info("DAQ recording started (Rate: %d Hz, Decimation: 1:%d)",
                        self._sampling_rate, self._rec_decimation)

    @Slot()
    def stop_recording(self):
        """Stop recording and close CSV file."""
        with self._data_lock:
            self._is_recording = False

            if self._csv_writer:
                self._csv_writer.close_file()
                self._csv_writer = None
                logger.info("DAQ recording stopped")

    def is_recording(self):
        """Return True if currently recording."""
        return self._is_recording

    def get_current_load(self):
        """Thread-safe getter for the current primary load reading."""
        # Using the filtered load value, minus any zero-offset
        with self._data_lock:
            return self._load_filtered - self._load_offset

    # =========================================================
    # CONFIGURATION SLOTS (GUI → DAQ thread via signal dispatch)
    # =========================================================

    @Slot(str)
    def set_mode(self, mode):
        """Mode setter for DataWorker interface compatibility."""
        pass  # DAQWorker is always Uniaxial

    @Slot(bool, float)
    def set_break_detection(self, enabled, threshold):
        """Configure break detection. Runs on DAQ thread via signal dispatch."""
        with self._data_lock:
            self._break_detection_enabled = enabled
            self._break_drop_threshold = abs(threshold)
            if enabled:
                self._peak_load = 0.0
                self._break_persist_count = 0
                logger.info("Break detection enabled (threshold: %.1f N)", threshold)

    @Slot(int)
    def update_sampling_rate(self, rate):
        """Update CSV recording rate."""
        with self._data_lock:
            self._sampling_rate = rate
            self._rec_decimation = max(1, self._sample_rate // self._sampling_rate)
            logger.debug("DAQ sampling rate updated: %d Hz", rate)

    @Slot(int)
    def set_motor_direction(self, direction):
        """Update direction: 1 for positive, -1 for negative, 0 for stopped."""
        with self._data_lock:
            if direction != self._motor_direction:
                self._motor_direction = direction
                if direction != 0:
                    self._disp_upper_warned = False
                    self._disp_lower_warned = False
                    self._encoder_limit_warned = False

    @Slot(int)
    def update_encoder_position(self, pos):
        """Called every time the serial parser receives a new encoder pulse position."""
        with self._data_lock:
            self._encoder_pos = pos
            motor_dir = self._motor_direction

        # --- Encoder Hardware Limit ---
        limit = -67008011
        if pos <= limit:
            if motor_dir < 0:  # Tension (negative) is BLOCKED
                self._safe_stop()
                with self._data_lock:
                    self._motor_direction = 0
                if not self._encoder_limit_warned:
                    self._encoder_limit_warned = True
                    self.overload_detected.emit(
                        f"ENCODER HARDWARE LIMIT REACHED!\n"
                        f"Position: {pos} (Limit: {limit})\n"
                        f"Please actuate in Compression (positive) mode to return to safe limits."
                    )
            elif motor_dir > 0: # Compression allowed
                self._encoder_limit_warned = False
        else:
            self._encoder_limit_warned = False

    def request_reset_overload_latch(self):
        """Thread-safe: emit signal to reset overload latch on DAQ thread."""
        self._reset_overload_requested.emit()

    @Slot()
    def reset_overload_latch(self):
        """Reset the load-cell overload latch. Runs on DAQ thread via signal."""
        with self._data_lock:
            self._overload_fired = False
        logger.info("Overload latch cleared (reset_overload_latch)")

    @Slot()
    def zero_uni_load(self):
        """Zero the load cell offset."""
        with self._data_lock:
            self._load_offset = self._load_filtered
            self._overload_fired = False  # Reset safety latch
        logger.info("Load zeroed at %.2f N", self._load_offset)

    @Slot()
    def zero_uni_disp(self):
        """Zero the displacement offset."""
        with self._data_lock:
            self._disp_offset = self._disp_filtered
            logger.info("Displacement zeroed at %.4f mm", self._disp_offset)

    @Slot(int)
    def zero_bi_single(self, idx):
        """No-op for DataWorker interface compatibility."""
        pass

    @Slot()
    def zero_bi_all(self):
        """No-op for DataWorker interface compatibility."""
        pass

    def request_configure_preload(self, target: float, indices: list):
        """Thread-safe request to configure and arm preload logic."""
        self._configure_preload_requested.emit(target, indices)

    @Slot(float, list)
    def configure_preload(self, target, indices):
        """Configure and arm preload logic. Runs on DAQ thread via signal."""
        with self._data_lock:
            self._preload_target = target
            self._preload_persist_count = 0
            if indices:
                self._preload_active = True
                logger.info("DAQ Preload armed: target=%.2f N", target)
            else:
                self._preload_active = False

