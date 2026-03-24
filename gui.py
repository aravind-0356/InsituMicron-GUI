# gui.py
import sys
import time
import re
import csv
import os
import threading
import queue
import gc
import statistics

# --- Camera Library ---
try:
    import PySpin
except ImportError:
    PySpin = None

# --- Computer Vision Library ---
try:
    import cv2
except ImportError:
    cv2 = None

# --- PyQtGraph Imports ---
import pyqtgraph as pg

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QStackedWidget, QLabel, QMessageBox, QSizePolicy
)
from PySide6.QtCore import (Qt, QTimer, Signal, QObject, Slot, QThread,
                            QMutex, QMutexLocker)
from PySide6.QtGui import QImage, QPixmap

from serial_handler import SerialHandler
from gui_panels import ConnectionPanel, SamplePanel, setup_plot_style
from gui_test_views import (
    UniaxialMotorControlPanel, BiaxialMotorControlPanel, MotorControlPage,
    SensorDisplayPanel, SampleInspectionPanel, TestDashboardPanel
)

# --- Corporate Colors (centralized) ---
from constants import PRIMARY_COLOR, ACCENT_COLOR

# --- Logging ---
from logging_config import get_logger
logger = get_logger(__name__)

# --- Pre-compiled regex for performance ---
UNIAXIAL_DATA_PATTERN = re.compile(r"LOAD:\s*(-?\d+\.?\d*)\s*kN,\s*DISP:\s*(-?\d+\.?\d*)\s*mm", re.IGNORECASE)


# =========================================================
# IMAGE SAVE WORKER (TIFF with No Compression)
# =========================================================
class ImageSaveWorker(QObject):
    def __init__(self, save_queue):
        super().__init__()
        self.save_queue = save_queue
        self.running = True
        self.images_saved = 0  # Counter for total images saved
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while self.running:
            try:
                item = self.save_queue.get(timeout=0.1)
                if item is None:
                    break

                img_data, path = item
                try:
                    if cv2 is not None:
                        # TIFF with NO COMPRESSION (1 = no compression in OpenCV)
                        cv2.imwrite(path, img_data, [cv2.IMWRITE_TIFF_COMPRESSION, 1])
                        self.images_saved += 1
                    else:
                        logger.error("ImageSaveWorker Error: cv2 not installed.")
                except Exception as e:
                    logger.error("ImageSaveWorker Error: %s", e)
                finally:
                    self.save_queue.task_done()
            except queue.Empty:
                continue

    def stop(self):
        self.running = False
        self.save_queue.put(None)
        self.thread.join()


# =========================================================
# CSV STREAMING WRITER (Replaces Excel Worker)
# =========================================================
class CSVWriter(QObject):
    """
    Streams data rows to CSV file in real-time during recording.
    """

    def __init__(self):
        super().__init__()
        self.csv_file = None
        self.csv_writer_obj = None
        self.is_open = False
        self.rows_written = 0  # Counter for data rows written

    def open_file(self, path, mode, headers):
        """
        Open CSV file and write headers.
        Args:
            path: Full path to CSV file
            mode: "Uniaxial" or "Biaxial"
            headers: List of column headers
        """
        try:
            self.csv_file = open(path, 'w', newline='', encoding='utf-8')
            self.csv_writer_obj = csv.writer(self.csv_file)

            # Write headers
            self.csv_writer_obj.writerow(headers)
            self.csv_file.flush()  # Ensure headers are written immediately

            self.is_open = True
            self.rows_written = 0  # Reset counter
            logger.info("CSV file opened: %s", path)
            return True
        except Exception as e:
            logger.error("CSV Writer Error opening file: %s", e)
            return False

    def write_row(self, row_data):
        """
        Write a single data row to CSV.
        Args:
            row_data: List of values for one row
        """
        if not self.is_open or self.csv_writer_obj is None:
            return False

        try:
            self.csv_writer_obj.writerow(row_data)
            self.csv_file.flush()  # Flush after each row for real-time saving
            self.rows_written += 1
            return True
        except Exception as e:
            logger.error("CSV Writer Error writing row: %s", e)
            return False

    def close_file(self):
        """Close the CSV file."""
        if self.is_open and self.csv_file:
            try:
                self.csv_file.close()
                self.is_open = False
                logger.info("CSV file closed successfully")
            except Exception as e:
                logger.error("CSV Writer Error closing file: %s", e)


# =========================================================
# CAMERA WORKER (TIFF Format)
# =========================================================
class CameraWorker(QThread):
    image_received = Signal(QImage)
    error_occurred = Signal(str)
    stats_updated = Signal(float)
    limits_ready = Signal(dict)

    def __init__(self):
        super().__init__()
        self.running = False
        self.system = None
        self.cam = None
        self.mutex = QMutex()
        self.pending_commands = []

        self.recording = False
        self.record_dir = ""
        self.snapshot_pending_count = 0  # Counter for pending snapshot requests
        self.snapshot_lock = threading.Lock()  # Thread-safe access

        self.save_queue = queue.Queue()
        self.save_worker = ImageSaveWorker(self.save_queue)

        self.last_display_time = 0.0

    def _ensure_save_worker_running(self):
        """
        Ensure the ImageSaveWorker is running. If it was stopped (due to stream stop),
        reinitialize it with a fresh queue and worker.
        """
        if not self.save_worker.running or not self.save_worker.thread.is_alive():
            # Clear any stale items from old queue
            while not self.save_queue.empty():
                try:
                    self.save_queue.get_nowait()
                except queue.Empty:
                    break
            
            # Create fresh queue and worker
            self.save_queue = queue.Queue()
            self.save_worker = ImageSaveWorker(self.save_queue)
            logger.debug("ImageSaveWorker reinitialized for new stream session")

    def start_recording(self, folder_path):
        self.record_dir = folder_path
        self.recording = True
        self.save_worker.images_saved = 0  # Reset counter
        logger.info("Camera recording STARTED - Folder: %s", folder_path)

    def stop_recording(self):
        self.recording = False
        logger.info("Camera recording STOPPED - Total images saved: %d", self.save_worker.images_saved)

    @Slot()
    def trigger_save_snapshot(self):
        """Thread-safe increment of snapshot request counter."""
        if self.recording:
            with self.snapshot_lock:
                self.snapshot_pending_count += 1

    def run(self):
        if PySpin is None:
            self.error_occurred.emit("PySpin library not found.")
            return

        # Ensure ImageSaveWorker is running (fixes issue after stream restart)
        self._ensure_save_worker_running()

        cam_list = None
        processor = None
        image_result = None

        try:
            self.system = PySpin.System.GetInstance()
            cam_list = self.system.GetCameras()

            if cam_list.GetSize() == 0:
                self.error_occurred.emit("No camera detected.")
                cam_list.Clear()
                self.system.ReleaseInstance()
                return

            self.cam = cam_list.GetByIndex(0)
            self.cam.Init()

            limits = self._extract_limits()
            self.limits_ready.emit(limits)

            s_node_map = self.cam.GetTLStreamNodeMap()
            handling_mode = PySpin.CEnumerationPtr(s_node_map.GetNode('StreamBufferHandlingMode'))
            if PySpin.IsWritable(handling_mode):
                handling_mode_entry = handling_mode.GetEntryByName('NewestOnly')
                handling_mode.SetIntValue(handling_mode_entry.GetValue())

            self.cam.BeginAcquisition()
            self.running = True

            processor = PySpin.ImageProcessor()

            last_time = time.time()
            frame_count = 0

            while self.running:
                self._process_pending_commands()

                # Validate camera connection before acquisition
                if self.cam is None or not self.cam.IsValid():
                    self.error_occurred.emit("Camera disconnected")
                    break

                try:
                    image_result = self.cam.GetNextImage(1000)

                    if image_result.IsIncomplete():
                        pass
                    else:
                        width = image_result.GetWidth()
                        height = image_result.GetHeight()

                        try:
                            image_converted = processor.Convert(image_result, PySpin.PixelFormat_Mono8)
                            image_data = image_converted.GetNDArray()

                            if self.recording:
                                # Get pending count atomically
                                with self.snapshot_lock:
                                    pending = self.snapshot_pending_count
                                    self.snapshot_pending_count = 0
                                
                                # Save all pending images
                                for i in range(pending):
                                    try:
                                        # Use unique timestamp with microseconds
                                        filename = f"img_{time.time():.6f}.tiff"
                                        full_path = os.path.join(self.record_dir, filename)

                                        save_copy = image_data.copy()
                                        self.save_queue.put((save_copy, full_path))
                                    except Exception as e:
                                        logger.error("Snapshot Queue Error: %s", e)

                            if time.time() - self.last_display_time > 0.1:
                                stride = image_converted.GetStride()
                                data_bytes = image_data.tobytes()
                                q_img = QImage(data_bytes, width, height, stride, QImage.Format_Grayscale8).copy()

                                display_img = q_img.scaled(800, 600, Qt.KeepAspectRatio, Qt.FastTransformation)
                                self.image_received.emit(display_img)
                                self.last_display_time = time.time()

                            frame_count += 1
                            curr_time = time.time()
                            if curr_time - last_time > 1.0:
                                fps = frame_count / (curr_time - last_time)
                                self.stats_updated.emit(fps)
                                frame_count = 0
                                last_time = curr_time

                        except PySpin.SpinnakerException as ex:
                            self.error_occurred.emit(f"Conversion Error: {ex}")

                    image_result.Release()
                    image_result = None

                except PySpin.SpinnakerException as ex:
                    error_str = str(ex)
                    if "Timeout" not in error_str:
                        # Check for disconnection-related errors
                        if "-1010" in error_str or "not initialized" in error_str.lower():
                            self.error_occurred.emit("Camera disconnected during recording")
                            break
                        self.error_occurred.emit(f"Acquisition Error: {ex}")

        except Exception as e:
            self.error_occurred.emit(f"Critical Error: {e}")
        finally:
            # Proper cleanup order: images -> processor -> cam_list -> camera -> system
            if image_result is not None:
                try:
                    image_result.Release()
                except:
                    pass
                image_result = None

            if processor is not None:
                processor = None

            if cam_list is not None:
                try:
                    cam_list.Clear()
                except:
                    pass
                cam_list = None

            self._cleanup()

    def _extract_limits(self):
        limits = {}
        try:
            if PySpin.IsReadable(self.cam.Gain):
                limits['Gain'] = (self.cam.Gain.GetMin(), self.cam.Gain.GetMax())
            if PySpin.IsReadable(self.cam.ExposureTime):
                limits['Exposure'] = (self.cam.ExposureTime.GetMin(), self.cam.ExposureTime.GetMax())
            if PySpin.IsReadable(self.cam.BlackLevel):
                limits['BlackLevel'] = (self.cam.BlackLevel.GetMin(), self.cam.BlackLevel.GetMax())
            if PySpin.IsReadable(self.cam.Gamma):
                limits['Gamma'] = (self.cam.Gamma.GetMin(), self.cam.Gamma.GetMax())
        except Exception as e:
            logger.warning("Error reading limits: %s", e)
        return limits

    def _cleanup(self):
        """Proper ordered cleanup to prevent [-1004] interface error"""
        try:
            # Step 1: Stop acquisition if running
            if self.cam is not None:
                try:
                    if self.cam.IsValid() and self.cam.IsStreaming():
                        self.cam.EndAcquisition()
                except:
                    pass  # Camera may already be disconnected
                
                # Step 2: Deinitialize camera
                try:
                    if self.cam.IsValid():
                        self.cam.DeInit()
                except:
                    pass
                
                # Step 3: Explicitly release reference
                self.cam = None

            # Step 4: Release system (must be after camera is fully released)
            if self.system is not None:
                try:
                    self.system.ReleaseInstance()
                except:
                    pass
                self.system = None
                
        except Exception as e:
            logger.error("Cleanup Error: %s", e)

    def stop(self):
        self.running = False
        self.wait()
        self.save_worker.stop()

    def queue_command(self, func, *args):
        with QMutexLocker(self.mutex):
            self.pending_commands.append((func, args))

    def _process_pending_commands(self):
        with QMutexLocker(self.mutex):
            while self.pending_commands:
                func, args = self.pending_commands.pop(0)
                try:
                    func(*args)
                except Exception as e:
                    self.error_occurred.emit(f"Command Failed: {e}")

    def set_gain(self, value, is_auto):
        if not self.cam: return
        try:
            if PySpin.IsWritable(self.cam.GainAuto):
                if is_auto:
                    self.cam.GainAuto.SetValue(PySpin.GainAuto_Continuous)
                    return
                else:
                    self.cam.GainAuto.SetValue(PySpin.GainAuto_Off)

            if PySpin.IsWritable(self.cam.Gain):
                val = max(self.cam.Gain.GetMin(), min(value, self.cam.Gain.GetMax()))
                self.cam.Gain.SetValue(val)
        except PySpin.SpinnakerException as e:
            logger.error("Set Gain Error: %s", e)

    def set_exposure(self, value, is_auto):
        if not self.cam: return
        try:
            if PySpin.IsWritable(self.cam.ExposureAuto):
                if is_auto:
                    self.cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Continuous)
                    return
                else:
                    self.cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)

            if PySpin.IsWritable(self.cam.ExposureMode):
                self.cam.ExposureMode.SetValue(PySpin.ExposureMode_Timed)

            if PySpin.IsWritable(self.cam.ExposureTime):
                val = max(self.cam.ExposureTime.GetMin(), min(value, self.cam.ExposureTime.GetMax()))
                self.cam.ExposureTime.SetValue(val)
        except PySpin.SpinnakerException as e:
            logger.error("Set Exposure Error: %s", e)

    def set_black_level(self, value, is_auto):
        if not self.cam: return
        try:
            if PySpin.IsWritable(self.cam.BlackLevel):
                val = max(self.cam.BlackLevel.GetMin(), min(value, self.cam.BlackLevel.GetMax()))
                self.cam.BlackLevel.SetValue(val)
        except PySpin.SpinnakerException as e:
            logger.error("Set BlackLevel Error: %s", e)

    def set_gamma(self, value):
        if not self.cam: return
        try:
            if PySpin.IsWritable(self.cam.GammaEnable):
                self.cam.GammaEnable.SetValue(True)
            if PySpin.IsWritable(self.cam.Gamma):
                val = max(self.cam.Gamma.GetMin(), min(value, self.cam.Gamma.GetMax()))
                self.cam.Gamma.SetValue(val)
        except PySpin.SpinnakerException as e:
            logger.error("Set Gamma Error: %s", e)


# =========================================================
# DATA WORKER (CSV Streaming)
# =========================================================
class DataWorker(QObject):
    ui_update = Signal(dict)
    plot_update = Signal(dict)
    break_detected_stop = Signal(str)
    overload_detected = Signal(str)  # Signal for firmware overload protection
    request_image_save = Signal()
    recording_error = Signal(str)  # Signal for CSV write failures
    preload_finished = Signal()    # Signal when preload sequence is complete

    def __init__(self, serial_handler):
        super().__init__()
        self.serial = serial_handler
        self._system_mode = "Uniaxial"

        self._uni_load_filtered = 0.0
        self._uni_disp_filtered = 0.0
        self._bi_loads_filtered = [0.0] * 4

        self._uni_load_offset = 0.0
        self._uni_disp_offset = 0.0
        self._bi_offsets = [0.0] * 4

        self._is_recording = False
        self._start_time = 0.0

        # CSV Writer for streaming
        self.csv_writer = None

        self.last_ui_update = 0.0
        self.last_plot_update = 0.0

        # For plotting (keep in memory for live updates)
        self._time_data = []
        self._load_data = []
        self._disp_data = []
        self._bi_load_data = [[], [], [], []]
        
        # Median buffers (Window 3)
        self._uni_med_buf = []
        self._bi_med_bufs = [[], [], [], []]
        
        # Sensor error tracking (True = sensor error)
        self._bi_sensor_errors = [False, False, False, False]

        self._break_detection_enabled = False
        self._break_drop_threshold = 1000.0
        self._peak_loads = [0.0, 0.0, 0.0, 0.0]
        self._break_triggered_axes = {"X": False, "Y": False}
        
        # Break persistence counters
        self._break_persist_count_uni = 0
        self._break_persist_counts_bi = [0, 0, 0, 0]

        self._sampling_rate = 4
        self._rec_thread = None

        # Thread safety mutex for break detection
        self._break_mutex = QMutex()
        
        # Max buffer size for plot data (prevents memory leak)
        # 10000 samples = ~16 minutes at 10 Hz, ~83 minutes at 2 Hz
        self._max_plot_buffer_size = 10000

        # --- Preload Logic State ---
        self._preload_active = False
        self._preload_target = 0.0
        self._preload_indices = []
        self._preload_finished_flags = [False, False, False, False] # For indices 0-3

    @Slot(str)
    def process_line(self, line):
        current_time = time.perf_counter()

        try:
            # --- Overload Detection (Firmware Safety) ---
            # Check for overload message from firmware - simple string check is O(1)
            if line.startswith("OVERLOAD:"):
                # Emit signal with the full overload message for popup display
                self.overload_detected.emit(line.strip())
                return  # Don't process overload messages as sensor data

            if self._system_mode == "Uniaxial":
                m = UNIAXIAL_DATA_PATTERN.match(line)
                if m:
                    raw_load = float(m.group(1)) * 1000.0
                    
                    # Median Filter (Window 3)
                    self._uni_med_buf.append(raw_load)
                    if len(self._uni_med_buf) > 3:
                        self._uni_med_buf.pop(0)
                    
                    self._uni_load_filtered = statistics.median(self._uni_med_buf)
                    self._uni_disp_filtered = float(m.group(2))

                    with QMutexLocker(self._break_mutex):
                        if self._break_detection_enabled:
                            current_mag = abs(self._uni_load_filtered)
                            self._peak_loads[0] = max(self._peak_loads[0], current_mag)
                            drop = self._peak_loads[0] - current_mag
                            if drop > self._break_drop_threshold:
                                self._break_persist_count_uni += 1
                                # Require 10 consecutive drops (approx 10-15ms depending on rate)
                                if self._break_persist_count_uni > 10:
                                    self.serial.send_cmd("STOP")
                                    self._break_detection_enabled = False
                                    self.break_detected_stop.emit(f"Break Detected! Drop: {drop:.1f} N")
                            else:
                                self._break_persist_count_uni = 0

                    # --- Preload Check (Uniaxial) ---
                    # Note: Uniaxial usually uses just one specific logic, but if 'indexes' are used, we follow that.
                    # Typically for Uni, we might just check the main load.
                    if self._preload_active and self._preload_indices:
                        # Assuming index 0 corresponds to the uniaxial load cell if monitored this way
                        # or if we are checking the filtered value directly.
                        # For now, let's assume if 0 is in indices, we check _uni_load_filtered.
                        if not self._preload_finished_flags[0] and (0 in self._preload_indices):
                            stop = False
                            # Use offset-corrected value (what user sees on UI)
                            val = self._uni_load_filtered - self._uni_load_offset
                            if self._preload_target >= 0:
                                if val >= self._preload_target: stop = True
                            else:
                                if val <= self._preload_target: stop = True
                            
                            if stop:
                                self.serial.send_cmd("STOP") # Uniaxial just has one STOP
                                self._preload_finished_flags[0] = True
                                logger.info("Preload Target Met (Uniaxial): %.2f N", val)
                                # Uni is single axis, so we are likely done
                                self._preload_active = False
                                self.preload_finished.emit()

            else:
                # CSV format: load1,load2,load3,load4 (in KN) or ERR for failed sensors
                parts = line.split(',')
                if len(parts) == 4:
                    for idx, val_str in enumerate(parts):
                        val_stripped = val_str.strip()
                        
                        # Check for error marker (fast string comparison)
                        if val_stripped == "ERR":
                            self._bi_sensor_errors[idx] = True
                            # Keep last valid value, don't update filtered
                        else:
                            try:
                                raw = float(val_stripped) * 1000.0  # Convert KN to N
                                self._bi_sensor_errors[idx] = False
                                
                                # Median Filter (Window 3)
                                self._bi_med_bufs[idx].append(raw)
                                if len(self._bi_med_bufs[idx]) > 3:
                                    self._bi_med_bufs[idx].pop(0)
                                    
                                self._bi_loads_filtered[idx] = statistics.median(self._bi_med_bufs[idx])
                            except ValueError:
                                pass  # Skip malformed values

                # --- Preload Check (Biaxial) ---
                if self._preload_active:
                    all_done = True
                    for i in self._preload_indices:
                        if not self._preload_finished_flags[i]:
                            all_done = False
                            # Use offset-corrected value (what user sees on UI)
                            val = self._bi_loads_filtered[i] - self._bi_offsets[i]
                            
                            stop = False
                            if self._preload_target >= 0:
                                if val >= self._preload_target: stop = True
                            else:
                                if val <= self._preload_target: stop = True
                            
                            if stop:
                                # Stop specific motor
                                self.serial.send_cmd(f"STOPM{i+1}")
                                # Redundancy
                                self.serial.send_cmd(f"STOPM{i+1}")
                                self._preload_finished_flags[i] = True
                                logger.info("Preload Target Met (Motor %d): %.2f N", i+1, val)
                    
                    if all_done:
                        self._preload_active = False
                        self.serial.send_cmd("STOP") # Final safety all-stop
                        self.preload_finished.emit()
                        logger.info("Preload Sequence Complete (All Targets Met)")

                with QMutexLocker(self._break_mutex):
                    if self._break_detection_enabled:
                        for idx in range(4):
                            axis = "Y" if idx < 2 else "X"
                            
                            current_mag = abs(self._bi_loads_filtered[idx])
                            self._peak_loads[idx] = max(self._peak_loads[idx], current_mag)
                            drop = self._peak_loads[idx] - current_mag
                            
                            if drop > self._break_drop_threshold:
                                self._break_persist_counts_bi[idx] += 1
                                if self._break_persist_counts_bi[idx] > 10:
                                    # GLOBAL STOP TRIGGER
                                    self._break_detection_enabled = False
                                    for _ in range(3):
                                        self.serial.send_cmd("STOP")
                                        time.sleep(0.02)

                                    self.break_detected_stop.emit(f"Break detected on {axis}-Axis (Load {idx + 1})! Stopping ALL motors.")
                                    break # Stop checking other sensors
                            else:
                                self._break_persist_counts_bi[idx] = 0

            if current_time - self.last_ui_update >= 0.033:
                data = {
                    "mode": self._system_mode,
                    "uni_load": self._uni_load_filtered - self._uni_load_offset,
                    "uni_disp": self._uni_disp_filtered - self._uni_disp_offset,
                    "bi_loads": [self._bi_loads_filtered[i] - self._bi_offsets[i] for i in range(4)],
                    "bi_errors": list(self._bi_sensor_errors),  # Sensor error states
                    "uni_zero_L": self._uni_load_offset,
                    "uni_zero_D": self._uni_disp_offset,
                    "bi_zeros": list(self._bi_offsets)
                }
                self.ui_update.emit(data)
                self.last_ui_update = current_time

            if current_time - self.last_plot_update >= 0.1:
                plot_data = {
                    "mode": self._system_mode,
                    "time": self._time_data,
                    "uni_L": self._load_data,
                    "bi_L": self._bi_load_data
                }
                self.plot_update.emit(plot_data)
                self.last_plot_update = current_time

        except Exception as e:
            logger.error("DataWorker Error: %s", e)

    def record_snapshot(self):
        """Called by recording thread at specified rate"""
        t_rel = time.time() - self._start_time

        if self._system_mode == "Uniaxial":
            l = self._uni_load_filtered - self._uni_load_offset
            d = self._uni_disp_filtered - self._uni_disp_offset

            # Add to plot buffers
            self._time_data.append(t_rel)
            self._load_data.append(l)
            self._disp_data.append(d)
            
            # Rolling window: trim buffers if too large to prevent memory leak
            if len(self._time_data) > self._max_plot_buffer_size:
                trim_count = self._max_plot_buffer_size // 5  # Remove oldest 20%
                self._time_data = self._time_data[trim_count:]
                self._load_data = self._load_data[trim_count:]
                self._disp_data = self._disp_data[trim_count:]

            # STREAM TO CSV immediately - halt on failure to prevent data loss
            if self.csv_writer and self.csv_writer.is_open:
                if not self.csv_writer.write_row([f"{t_rel:.3f}", f"{l:.2f}", f"{d:.4f}"]):
                    self._is_recording = False
                    self.recording_error.emit("CSV write failed - recording stopped to prevent data loss")
                    return
        else:
            # Add to plot buffers
            self._time_data.append(t_rel)
            for i in range(4):
                val = self._bi_loads_filtered[i] - self._bi_offsets[i]
                self._bi_load_data[i].append(val)
            
            # Rolling window: trim buffers if too large to prevent memory leak
            if len(self._time_data) > self._max_plot_buffer_size:
                trim_count = self._max_plot_buffer_size // 5  # Remove oldest 20%
                self._time_data = self._time_data[trim_count:]
                for i in range(4):
                    self._bi_load_data[i] = self._bi_load_data[i][trim_count:]

            # STREAM TO CSV immediately - halt on failure to prevent data loss
            if self.csv_writer and self.csv_writer.is_open:
                row = [f"{t_rel:.3f}"] + [f"{self._bi_loads_filtered[i] - self._bi_offsets[i]:.2f}" for i in range(4)]
                if not self.csv_writer.write_row(row):
                    self._is_recording = False
                    self.recording_error.emit("CSV write failed - recording stopped to prevent data loss")
                    return

        # Trigger image save
        self.request_image_save.emit()

    def _recording_loop(self):
        start_time = time.time()
        count = 0

        while self._is_recording:
            self.record_snapshot()
            count += 1

            target_time = start_time + (count * (1.0 / self._sampling_rate))

            now = time.time()
            sleep_time = target_time - now

            if sleep_time > 0:
                time.sleep(sleep_time)

    @Slot(str, str)
    def start_recording(self, csv_path, mode):
        """
        Start recording with CSV file already created.
        Args:
            csv_path: Full path to CSV file (or None if not saving data)
            mode: "Uniaxial" or "Biaxial"
        """
        self._system_mode = mode

        # Reset state
        self._peak_loads = [0.0, 0.0, 0.0, 0.0]
        self._break_triggered_axes = {"X": False, "Y": False}
        self._time_data.clear()
        self._load_data.clear()
        self._disp_data.clear()
        for l in self._bi_load_data: l.clear()
        
        # Clear median buffers
        self._uni_med_buf = []
        self._bi_med_bufs = [[], [], [], []]

        # Initialize CSV Writer
        self.csv_writer = CSVWriter()
        if mode == "Uniaxial":
            headers = ["Time(s)", "Load(N)", "Disp(mm)"]
        else:
            headers = ["Time(s)", "Load 1 (N)", "Load 2 (N)", "Load 3 (N)", "Load 4 (N)"]

        if csv_path:
            if not self.csv_writer.open_file(csv_path, mode, headers):
                logger.error("ERROR: Failed to open CSV file for writing")
                return
        else:
            logger.info("Recording started without CSV output (Images only mode)")
            if self.csv_writer.is_open:
                self.csv_writer.close_file()

        self._start_time = time.time()
        self._is_recording = True

        # Start recording thread
        self._rec_thread = threading.Thread(target=self._recording_loop, daemon=True)
        self._rec_thread.start()

    @Slot()
    def stop_recording(self):
        """Stop recording and close CSV file"""
        self._is_recording = False
        if self._rec_thread:
            self._rec_thread.join(timeout=1.0)

        # Close CSV file
        if self.csv_writer:
            self.csv_writer.close_file()
            self.csv_writer = None
            logger.info("Data recording STOPPED")

    def is_recording(self):
        """Return True if currently recording"""
        return self._is_recording

    @Slot(str)
    def set_mode(self, mode):
        self._system_mode = mode

    @Slot(bool, float)
    def set_break_detection(self, enabled, threshold):
        with QMutexLocker(self._break_mutex):
            self._break_detection_enabled = enabled
            self._break_drop_threshold = abs(threshold)
            if enabled:
                self._peak_loads = [0.0, 0.0, 0.0, 0.0]
                self._break_persist_count_uni = 0
                self._break_persist_counts_bi = [0, 0, 0, 0]

    @Slot(int)
    def update_sampling_rate(self, rate):
        if rate > 0:
            self._sampling_rate = rate

    @Slot()
    def zero_uni_load(self):
        self._uni_load_offset = self._uni_load_filtered

    @Slot()
    def zero_uni_disp(self):
        self._uni_disp_offset = self._uni_disp_filtered

    @Slot(int)
    def zero_bi_single(self, idx):
        self._bi_offsets[idx] = self._bi_loads_filtered[idx]

    @Slot()
    def zero_bi_all(self):
        for i in range(4): self._bi_offsets[i] = self._bi_loads_filtered[i]

    @Slot(float, list)
    def configure_preload(self, target, indices):
        """Configure and arm the preload logic."""
        self._preload_target = target
        self._preload_indices = indices
        self._preload_finished_flags = [False, False, False, False]
        # Only set active if there are indices to verify
        if indices:
            self._preload_active = True
            logger.info("DataWorker: Preload armed. Target: %.2f N, Indices: %s", target, indices)
        else:
            self._preload_active = False


# =========================================================
# MAIN WINDOW
# =========================================================
class MainWindow(QMainWindow):
    show_error_signal = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("InsituMicron GUI")
        self.resize(1300, 850)

        self.serial_handler = SerialHandler()

        # Data Worker Thread
        self.data_thread = QThread()
        self.data_worker = DataWorker(self.serial_handler)
        self.data_worker.moveToThread(self.data_thread)

        self.serial_handler.data_received.connect(self.data_worker.process_line)
        self.data_worker.ui_update.connect(self.update_labels)
        self.data_worker.plot_update.connect(self.update_graphs)
        self.data_worker.break_detected_stop.connect(self.handle_break_stop)
        self.data_worker.overload_detected.connect(self.handle_overload_stop)
        self.data_worker.recording_error.connect(self.handle_recording_error)
        self.data_worker.preload_finished.connect(lambda: logger.info("Preload finished (Signal received in UI)"))
        self.serial_handler.connection_status_changed.connect(self.handle_connection_status)
        self.show_error_signal.connect(self.show_critical_error_box)

        self.data_thread.start()

        self._system_mode = "Biaxial"

        # Output folder state
        self._output_folder = ""

        # Save options state (default: save both)
        self._save_sensor_data = True
        self._save_images = True

        self._sample_id = "Default"
        self._sample_type = "Biaxial"
        self._sample_width = 10.0
        self._sample_thickness = 1.0
        self._sample_radius = 5.0
        self._sample_gauge_length = 50.0

        self._homing_active = False
        self._homing_target = 0.0
        self._homing_tol = 0.05
        self._homing_timer = QTimer()
        self._homing_timer.setInterval(100)
        self._homing_timer.timeout.connect(self._homing_loop)
        self._last_homing_cmd = ""
        self._homing_velocity = 100
        self._current_raw_disp = 0.0

        self._homing_velocity = 100
        self._current_raw_disp = 0.0

        self._cached_bi_loads = [0.0] * 4
        
        # Sync record state
        self._sync_record_enabled = False
        self._sample_extra_dims = ""

        self._is_connected = False

        self.conn_panel = ConnectionPanel(self.serial_handler)
        self.sample_panel = SamplePanel(self)

        # Connect folder selection and save options signals
        self.sample_panel.output_folder_changed.connect(self.set_output_folder)
        self.sample_panel.save_sensor_changed.connect(self.set_save_sensor)
        self.sample_panel.save_images_changed.connect(self.set_save_images)

        self.camera_panel = SampleInspectionPanel()

        # FIXED: Direct connection without lambda using folder_path
        self.data_worker.request_image_save.connect(self.camera_panel.worker.trigger_save_snapshot)

        self.dashboard_panel = TestDashboardPanel()

        self.camera_panel.worker.image_received.connect(self.dashboard_panel.update_image)
        self.dashboard_panel.stop_all_requested.connect(lambda: self.serial_handler.send_cmd("STOP"))
        self.dashboard_panel.stop_rec_requested.connect(self.stop_record)

        self.uni_control = UniaxialMotorControlPanel(self.serial_handler)
        self.uni_control.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        self.bi_control = BiaxialMotorControlPanel(self.serial_handler)
        self.bi_control.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        self.motor_page = MotorControlPage(self.uni_control, self.bi_control)
        self.motor_page.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.motor_page.mode_changed_sig.connect(self.switch_mode)

        self.sensor_panel = SensorDisplayPanel()
        self.sensor_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        self.sensor_panel.set_zero_uni_load.connect(self.data_worker.zero_uni_load)
        self.sensor_panel.set_zero_uni_disp.connect(self.data_worker.zero_uni_disp)
        self.sensor_panel.set_zero_bi_single.connect(self.data_worker.zero_bi_single)
        self.sensor_panel.set_zero_bi_all.connect(self.data_worker.zero_bi_all)

        self.sensor_panel.request_start_rec.connect(self.start_record)
        self.sensor_panel.request_stop_rec.connect(self.stop_record)
        self.sensor_panel.auto_record_changed.connect(self.set_sync_record)

        self.sensor_panel.break_detection_changed.connect(self.data_worker.set_break_detection)

        self.bi_control.preload_start.connect(self.start_preload)
        self.bi_control.preload_stop.connect(lambda: self.serial_handler.send_cmd("PRESTOP"))
        
        # Connect motor start signals for sync recording
        self.uni_control.motor_started.connect(self.handle_motor_started)
        self.bi_control.motor_started.connect(self.handle_motor_started)

        self.sensor_panel.sampling_rate_changed.connect(self.data_worker.update_sampling_rate)

        self.uni_control.homing_requested.connect(self.start_homing)
        self.uni_control.homing_cancelled.connect(self.stop_homing)

        # Initialize dashboard curves (will be recreated in switch_mode)
        self.dashboard_uni_curve = None
        self.dashboard_bi_curves = []

        self.setup_layout()

        # Ensure UI defaults to Biaxial (Call after everything is initialized)
        self.motor_page.combo.setCurrentText(self._system_mode)

    def setup_layout(self):
        main = QWidget()
        self.setCentralWidget(main)
        layout = QHBoxLayout(main)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar_drawer = QWidget()
        self.sidebar_drawer.setFixedWidth(250)
        self.sidebar_drawer.setStyleSheet("background-color: #ecf0f1; border-right: 1px solid #bdc3c7;")
        drawer_layout = QVBoxLayout(self.sidebar_drawer)
        drawer_layout.setContentsMargins(0, 10, 0, 0)

        # Company Logo at the top of sidebar
        # Use get_resource_dir() for PyInstaller compatibility
        from logging_config import get_resource_dir
        logo_path = os.path.join(get_resource_dir(), "InsituMicronlogo.jpg")
        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignCenter)
        # Set background to white to match logo's white background
        self.logo_label.setStyleSheet("background-color: white; margin: 8px 8px 5px 8px; padding: 5px; border-radius: 4px;")
        if os.path.exists(logo_path):
            logo_pixmap = QPixmap(logo_path)
            # Scale to 35px height for compact fit
            scaled_pixmap = logo_pixmap.scaledToHeight(35, Qt.SmoothTransformation)
            self.logo_label.setPixmap(scaled_pixmap)
        else:
            logger.warning("Logo not found at: %s", logo_path)
        drawer_layout.addWidget(self.logo_label)

        # FIXED: Increased MENU label font size to 22px
        self.lbl_menu = QLabel("MENU")
        self.lbl_menu.setStyleSheet(
            "font-weight: bold; font-size: 22px; color: #2c3e50; margin-left: 15px; margin-bottom: 10px;")

        self.sidebar = QListWidget()
        self.sidebar.addItems(["Connection", "Test Configuration", "Test Setup", "Image Setup", "Test Dashboard"])
        # FIXED: Increased sidebar font size to 20px
        self.sidebar.setStyleSheet(f"""
            QListWidget {{ background-color: transparent; border: none; font-size: 20px; }}
            QListWidget::item {{ padding: 16px; margin: 2px 5px; color: #2c3e50; }}
            QListWidget::item:selected {{ background-color: {PRIMARY_COLOR}; color: white; border-radius: 5px; }}
            QListWidget::item:hover:!selected {{ background-color: #dfe6e9; border-radius: 5px; }}
        """)
        self.sidebar.currentRowChanged.connect(self.change_page)

        drawer_layout.addWidget(self.lbl_menu)
        drawer_layout.addWidget(self.sidebar)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)

        self.pages = QStackedWidget()
        self.pages.addWidget(self.conn_panel)
        self.pages.addWidget(self.sample_panel)

        self.test_setup_page = QWidget()
        ts_layout = QVBoxLayout(self.test_setup_page)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        top_row.setContentsMargins(0, 0, 0, 0)

        motion_container = QWidget()
        mc_layout = QVBoxLayout(motion_container)
        mc_layout.setContentsMargins(0, 0, 0, 0)
        mc_layout.addWidget(self.motor_page)
        mc_layout.addStretch()

        sensor_container = QWidget()
        sc_layout = QVBoxLayout(sensor_container)
        sc_layout.setContentsMargins(0, 0, 0, 0)
        sc_layout.addWidget(self.sensor_panel)
        sc_layout.addStretch()

        top_row.addWidget(motion_container, 7)
        top_row.addWidget(sensor_container, 3)

        ts_layout.addLayout(top_row, 0)

        self.graph_stack = QStackedWidget()
        self.graph_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        uni_g = QWidget()
        uni_gl = QVBoxLayout(uni_g)
        uni_gl.setContentsMargins(0, 5, 0, 0)
        self.plot_uni_lt = pg.PlotWidget()
        setup_plot_style(self.plot_uni_lt, "Uniaxial Load vs Time", "Time (s)", "Load (N)")
        self.uni_curve = self.plot_uni_lt.plot(pen=pg.mkPen(color='#2980b9', width=3))
        uni_gl.addWidget(self.plot_uni_lt)
        self.graph_stack.addWidget(uni_g)

        bi_g = QWidget()
        bi_gl = QVBoxLayout(bi_g)
        bi_gl.setContentsMargins(0, 5, 0, 0)
        self.plot_bi = pg.PlotWidget()
        setup_plot_style(self.plot_bi, "Biaxial Loads vs Time", "Time (s)", "Load (N)")
        # FIXED: Added labelTextSize parameter
        self.plot_bi.addLegend(labelTextSize='16pt')
        colors = ['#c0392b', '#27ae60', '#2980b9', '#8e44ad']
        self.bi_curves = [self.plot_bi.plot(pen=pg.mkPen(color=c, width=3), name=f"Load {i + 1}") for i, c in
                          enumerate(colors)]
        bi_gl.addWidget(self.plot_bi)
        self.graph_stack.addWidget(bi_g)

        ts_layout.addWidget(self.graph_stack, 1)

        self.pages.addWidget(self.test_setup_page)

        self.pages.addWidget(self.camera_panel)

        self.pages.addWidget(self.dashboard_panel)

        content_layout.addWidget(self.pages)

        layout.addWidget(self.sidebar_drawer)
        layout.addWidget(content_widget)

        # Initialize with default mode
        self.switch_mode(self._system_mode)

    def change_page(self, idx):
        self.pages.setCurrentIndex(idx)

    def switch_mode(self, mode):
        """FIXED: Properly recreate dashboard curves based on mode"""
        self._system_mode = mode
        self.sensor_panel.set_mode(mode)
        self.graph_stack.setCurrentIndex(0 if mode == "Uniaxial" else 1)
        self.data_worker.set_mode(mode)

        # FIXED: Clear dashboard plot and recreate curves for selected mode
        self.dashboard_panel.plot_widget.clear()

        # Remove old legend if exists (with proper null checks)
        legend = self.dashboard_panel.plot_widget.plotItem.legend
        if legend is not None:
            scene = legend.scene()
            if scene is not None:
                scene.removeItem(legend)
            self.dashboard_panel.plot_widget.plotItem.legend = None

        if mode == "Uniaxial":
            # Add legend FIRST with larger text
            self.dashboard_panel.plot_widget.addLegend(labelTextSize='16pt', offset=(30, 30))

            # Create single uniaxial curve
            self.dashboard_uni_curve = self.dashboard_panel.plot_widget.plot(
                pen=pg.mkPen(color='#2980b9', width=3), name="Load"
            )
            self.dashboard_bi_curves = []
        else:
            # Add legend FIRST with larger text
            self.dashboard_panel.plot_widget.addLegend(labelTextSize='16pt', offset=(30, 30))

            # Create four biaxial curves
            self.dashboard_uni_curve = None
            colors = ['#c0392b', '#27ae60', '#2980b9', '#8e44ad']
            self.dashboard_bi_curves = [
                self.dashboard_panel.plot_widget.plot(pen=pg.mkPen(color=c, width=3), name=f"Load {i + 1}")
                for i, c in enumerate(colors)
            ]

        self.dashboard_panel.update_dashboard_title(mode)

    @Slot(str)
    def set_output_folder(self, folder):
        self._output_folder = folder
        logger.info("MainWindow: Output folder set to %s", folder)

    def set_sample_id(self, v):
        self._sample_id = v

    def set_sample_type(self, v):
        self._sample_type = v

    def set_sample_width(self, v):
        self._sample_width = v

    def set_sample_thickness(self, v):
        self._sample_thickness = v

    def set_sample_radius(self, v):
        self._sample_radius = v

    def set_sample_gauge_length(self, v):
        self._sample_gauge_length = v

    @Slot(bool)
    def set_save_sensor(self, enabled):
        self._save_sensor_data = enabled
        logger.debug("Save sensor data: %s", enabled)

    @Slot(bool)
    def set_save_images(self, enabled):
        self._save_images = enabled

    @Slot(str)
    def set_sample_extra_dims(self, text):
        self._sample_extra_dims = text
        logger.debug("Sample extra dims set: %s", text)


    @Slot(bool)
    def set_sync_record(self, enabled):
        self._sync_record_enabled = enabled
        logger.debug("Sync record enabled: %s", enabled)

    @Slot()
    def handle_motor_started(self):
        """Called when any motor start button is clicked"""
        logger.debug("handle_motor_started called. Enabled: %s, Recording: %s", self._sync_record_enabled, self.data_worker.is_recording())
        if self._sync_record_enabled and not self.data_worker.is_recording():
            logger.info("Sync Record: Motor started, auto-starting recording...")
            self.start_record()

    @Slot(dict)
    def update_labels(self, data):
        self._current_raw_disp = data["uni_disp"] + data["uni_zero_D"]
        self.uni_control.update_disp(self._current_raw_disp)

        self.sensor_panel.update_uni(data["uni_load"], data["uni_disp"])
        self.sensor_panel.update_uni_offset(data["uni_zero_L"], data["uni_zero_D"])
        self.sensor_panel.update_bi(data["bi_loads"], data.get("bi_errors", [False]*4))
        for i, val in enumerate(data["bi_zeros"]):
            self.sensor_panel.update_bi_offset(i, val)

        self._cached_bi_loads = data["bi_loads"]

    @Slot(dict)
    def update_graphs(self, data):
        """FIXED: Handle dashboard curves safely"""
        if data["mode"] == "Uniaxial":
            self.uni_curve.setData(data["time"], data["uni_L"])
            if self.dashboard_uni_curve is not None:
                self.dashboard_uni_curve.setData(data["time"], data["uni_L"])
        else:
            for i in range(4):
                if i < len(data["bi_L"]):
                    self.bi_curves[i].setData(data["time"], data["bi_L"][i])
                    if i < len(self.dashboard_bi_curves):
                        self.dashboard_bi_curves[i].setData(data["time"], data["bi_L"][i])

    @Slot(str)
    def handle_break_stop(self, msg):
        logger.warning("BREAK DETECTED: %s", msg)
        self.sensor_panel.chk_bd_uni.setChecked(False)
        self.sensor_panel.chk_bd_bi.setChecked(False)
        self.uni_control.lbl_status.setText("Status: BREAK STOP")
        
        if self.data_worker.is_recording():
             self.stop_record()
             msg += "\nRecording stopped."
             
        QMessageBox.information(self, "Auto-Stop", msg)

    @Slot(str)
    def handle_overload_stop(self, msg):
        """
        Handler for firmware overload protection.
        Shows a warning popup when the microcontroller detects overload and stops motors.
        """
        logger.warning("OVERLOAD PROTECTION TRIGGERED: %s", msg)
        # Update status labels
        self.uni_control.lbl_status.setText("Status: OVERLOAD STOP")
        self.uni_control.lbl_status.setStyleSheet(
            "background-color: #e74c3c; color: white; padding: 8px; border-radius: 4px; font-weight: bold;")
        
        # Show warning popup with overload details
        QMessageBox.warning(
            self,
            "⚠️ Overload Protection Triggered",
            f"The firmware has stopped all motors due to overload protection.\n\n"
            f"{msg}\n\n"
            f"Please check the load cell readings and reduce the applied force "
            f"before resuming operations."
        )

    @Slot(str)
    def handle_recording_error(self, error_msg):
        """Handle CSV write failures during recording"""
        logger.error("Recording error: %s", error_msg)
        self.stop_record()  # Ensure recording is fully stopped
        QMessageBox.critical(self, "Recording Error", error_msg)

    def start_preload(self, mode, target, rpm):
        if not self.serial_handler.is_connected():
            QMessageBox.critical(self, "Connection Error", "USB is disconnected! Please connect to the device.")
            return

        indices = []
        if mode == "X":
            indices = [2, 3]
        elif mode == "Y":
            indices = [0, 1]
        elif mode == "ALL":
            indices = [0, 1, 2, 3]

        self.preload_sequence_cmds = []
        for i in indices:
            self.preload_sequence_cmds.append((f"VEL{i + 1}:{rpm}", 10))
            self.preload_sequence_cmds.append((f"STARTM{i + 1}", 10))

        # ARM the DataWorker BEFORE sending start commands
        self.data_worker.configure_preload(target, indices)

        self._process_preload_commands()

    def _process_preload_commands(self):
        if not hasattr(self, 'preload_sequence_cmds') or not self.preload_sequence_cmds:
            return

        cmd, delay = self.preload_sequence_cmds.pop(0)
        self.serial_handler.send_cmd(cmd)

        if self.preload_sequence_cmds:
            QTimer.singleShot(delay, self._process_preload_commands)

    # _start_preload_monitoring and _preload_loop removed (Logic moved to DataWorker)

    def start_record(self):
        """Pre-selection validation and immediate folder/file creation"""
        # VALIDATION: Check connection first
        if not self.serial_handler.is_connected():
            QMessageBox.critical(self, "Connection Error", "USB is disconnected! Please connect to the device.")
            return

        # VALIDATION: Check camera stream if saving images
        if self._save_images and not self.camera_panel.is_live():
            QMessageBox.critical(self, "Camera Error", "Camera feed is not live! Please start the stream in 'Image Setup' tab.")
            return

        # VALIDATION: Check if output folder has been selected
        if not self._output_folder:
            QMessageBox.critical(
                self,
                "No Output Folder Selected",
                "Please select an output folder in the Test Configuration screen before starting recording."
            )
            return

        # VALIDATION: Check at least one save option is selected
        if not self._save_sensor_data and not self._save_images:
            QMessageBox.critical(
                self,
                "No Save Options Selected",
                "Please select at least one save option (Sensor Data or Camera Images) in the Test Configuration screen."
            )
            return

        # Create timestamped test folder
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        test_folder_name = f"{self._sample_id}_{timestamp}"
        self.current_save_dir = os.path.join(self._output_folder, test_folder_name)

        try:
            os.makedirs(self.current_save_dir, exist_ok=True)
            
            if self._save_images:
                self.images_dir = os.path.join(self.current_save_dir, "Images")
                os.makedirs(self.images_dir, exist_ok=True)
            else:
                self.images_dir = None
                
            logger.info("Created test folder: %s", self.current_save_dir)
        except Exception as e:
            QMessageBox.critical(self, "Folder Creation Error", f"Failed to create test folder:\n{e}")
            return

        # Start Camera Recording (only if enabled)
        if self._save_images and self.images_dir:
            self.camera_panel.worker.start_recording(self.images_dir)

        # Start Data Recording (handles both CSV streaming and image triggers)
        csv_path = None
        if self._save_sensor_data:
            csv_path = os.path.join(self.current_save_dir, "test_data.csv")
        
        # Always start worker to drive timing loop (even if just for images)
        self.data_worker.start_recording(csv_path, self._system_mode)

        # Update UI
        self.sensor_panel.set_recording_state(True)
        
        # Log what's being recorded
        recording_info = []
        if self._save_sensor_data:
            recording_info.append("Sensor Data")
        if self._save_images:
            recording_info.append("Camera Images")
        logger.info("Recording started: %s", ', '.join(recording_info))

    def stop_record(self):
        """Stop recording and close files, then create Excel summary"""
        # Stop camera recording (only if it was enabled)
        if self._save_images:
            self.camera_panel.worker.stop_recording()
        
        # Stop data recording (always, since it drives the loop)
        self.data_worker.stop_recording()
        
        self.sensor_panel.set_recording_state(False)

        # Create Excel file with two sheets (only if sensor data was recorded)
        if self._save_sensor_data:
            try:
                self._create_excel_summary()
            except Exception as e:
                logger.error("Excel export error: %s", e)

        # Build save message based on what was saved
        saved_items = []
        if self._save_sensor_data:
            saved_items.append("Sensor data (Excel)")
        if self._save_images:
            saved_items.append("Camera images")
        
        # Show success popup with save location
        QMessageBox.information(
            self,
            "Recording Saved",
            f"{' and '.join(saved_items)} saved to:\n\n{self.current_save_dir}"
        )
        logger.info("Recording stopped. All files closed.")

    def _create_excel_summary(self):
        """Create Excel file with Sensor Data and Sample Parameters sheets"""
        from openpyxl import Workbook

        excel_path = os.path.join(self.current_save_dir, "test_results.xlsx")
        csv_path = os.path.join(self.current_save_dir, "test_data.csv")

        wb = Workbook()

        # Sheet 1: Sensor Data (from CSV)
        ws_data = wb.active
        ws_data.title = "Sensor Data"

        if os.path.exists(csv_path):
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    ws_data.append(row)

        # Sheet 2: Sample Parameters
        ws_params = wb.create_sheet("Sample Parameters")

        # Add headers
        ws_params.append(["Parameter", "Value"])
        ws_params.append(["Sample ID", self._sample_id])
        ws_params.append(["Sample Type", self._sample_type])
        ws_params.append(["Mode", self._system_mode])

        # Add dimensions based on sample type
        if self._sample_type == "Rectangular":
            ws_params.append(["Width (mm)", self._sample_width])
            ws_params.append(["Thickness (mm)", self._sample_thickness])
            ws_params.append(["Gauge Length (mm)", self._sample_gauge_length])
        elif self._sample_type == "Biaxial":
            ws_params.append(["Additional Dimensions", self._sample_extra_dims])
        else:  # Circular
            ws_params.append(["Radius (mm)", self._sample_radius])
            ws_params.append(["Gauge Length (mm)", self._sample_gauge_length])

        wb.save(excel_path)
        logger.info("Excel summary created: %s", excel_path)

        # Remove temporary CSV file (data is now in Excel)
        if os.path.exists(csv_path):
            os.remove(csv_path)
            logger.debug("Temporary CSV file removed: %s", csv_path)

    @Slot(bool, str)
    def handle_connection_status(self, is_connected, msg):
        if self._is_connected and not is_connected:
            self.show_error_signal.emit("Connection Lost", f"The USB device was disconnected.\n\nDetails: {msg}")

        self._is_connected = is_connected

    @Slot(str, str)
    def show_critical_error_box(self, title, msg):
        QMessageBox.critical(self, title, msg)

    def start_homing(self, target, tol):
        if self._system_mode != "Uniaxial": return
        self._homing_target = target
        self._homing_tol = tol
        self._homing_active = True
        self._homing_timer.start()

    def stop_homing(self):
        self._homing_active = False
        self._homing_timer.stop()
        self.serial_handler.send_cmd("STOP")

    def _homing_loop(self):
        if not self._homing_active: return
        curr = self._current_raw_disp
        diff = curr - self._homing_target
        if abs(diff) <= self._homing_tol:
            self.stop_homing()
            self.uni_control.lbl_status.setText("Status: HOMED")
        else:
            direction = "-" if diff > 0 else "+"
            cmd = f"VEL:{direction}{self._homing_velocity}"
            if cmd != self._last_homing_cmd:
                self.serial_handler.send_cmd(cmd)
                self.serial_handler.send_cmd("START")
                self._last_homing_cmd = cmd

    def closeEvent(self, e):
        self.serial_handler.disconnect()

        if hasattr(self, 'data_thread'):
            self.data_thread.quit()
            self.data_thread.wait()

        if hasattr(self, 'camera_panel') and self.camera_panel.worker.isRunning():
            self.camera_panel.stop_camera()

        e.accept()