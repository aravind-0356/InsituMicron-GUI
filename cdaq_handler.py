import json
import os
import time
import threading
import collections
import numpy as np

from PySide6.QtCore import QObject, Signal, Slot, QCoreApplication
from logging_config import get_logger, resource_path

logger = get_logger(__name__)

try:
    import nidaqmx
    from nidaqmx.constants import (
        BridgeConfiguration,
        ExcitationSource,
        AcquisitionType
    )
    from nidaqmx.stream_readers import AnalogMultiChannelReader
    HAS_NIDAQMX = True
except ImportError:
    HAS_NIDAQMX = False

from daq_handler import DAQCSVWriter

class CDAQWorker(QObject):
    """
    NI cDAQ Biaxial Sensor acquisition worker.
    Implements SensorWorkerProtocol for seamless integration.
    """
    ui_update = Signal(dict)
    plot_update = Signal(dict)
    break_detected_stop = Signal(str)
    overload_detected = Signal(str)
    request_image_save = Signal()
    recording_error = Signal(str)
    preload_finished = Signal()
    
    daq_error = Signal(str)
    daq_connected = Signal(str)
    
    _start_requested = Signal(bool)
    _start_recording_requested = Signal(str, str)
    _configure_preload_requested = Signal(float, list)

    def __init__(self, serial_handler=None):
        super().__init__()
        self._serial = serial_handler
        
        self._start_requested.connect(self._handle_start)
        self._start_recording_requested.connect(self.start_recording)
        self._configure_preload_requested.connect(self.configure_preload)
        
        self._data_lock = threading.Lock()
        
        # State
        self._running = False
        self._task = None
        self._system_mode = "Biaxial"
        
        # Configuration
        self._config_path = resource_path(os.path.join("config", "sensors_config.json"))
        self._sample_rate = 100
        self._batch_size = 10
        self._channels_config = []
        
        # Buffers and filtering
        self._bi_loads_filtered = [0.0] * 4
        self._bi_offsets = [0.0] * 4
        self._bi_med_bufs = [collections.deque(maxlen=3) for _ in range(4)]
        self._bi_sensor_errors = [False] * 4
        
        # Recording
        self._is_recording = False
        self._csv_writer = None
        self._sampling_rate = 4
        self._rec_decimation = max(1, self._sample_rate // self._sampling_rate)
        self._rec_sample_counter = 0
        self._rec_total_snapshots = 0
        self._start_time = 0.0
        
        # Break detection
        self._break_detection_enabled = False
        self._break_drop_threshold = 1000.0
        self._peak_loads = [0.0] * 4
        self._break_persist_counts_bi = [0] * 4
        
        # Preload
        self._preload_active = False
        self._preload_target = 0.0
        self._preload_indices = []
        self._preload_finished_flags = [False] * 4
        
        # Plotting
        self._time_data = []
        self._bi_load_data = [[], [], [], []]
        self._max_plot_buffer_size = 10000
        self._last_ui_update = 0.0
        self._last_plot_update = 0.0
        self._freeze_plots = False

    @Slot(bool)
    def set_freeze_plots(self, freeze):
        with self._data_lock:
            self._freeze_plots = freeze

    def load_config(self):
        try:
            self._config_path = resource_path(os.path.join("config", "sensors_config.json"))
            with open(self._config_path, 'r') as f:
                config = json.load(f)
                acq = config.get("acquisition", {})
                self._sample_rate = acq.get("sample_rate_hz", 100)
                self._batch_size = acq.get("batch_size", 10)
                self._rec_decimation = max(1, self._sample_rate // self._sampling_rate)
                
                self._channels_config = []
                for i in range(4):
                    sensor_key = f"sensor_{i}"
                    if sensor_key in config:
                        self._channels_config.append(config[sensor_key])
            return True
        except Exception as e:
            logger.error("Failed to load cDAQ config: %s", e)
            return False

    def detect_device(self, allow_simulated=False):
        if not HAS_NIDAQMX: return None
        try:
            system = nidaqmx.system.System.local()
            # First priority: find real physical cDAQ device
            for dev in system.devices:
                if len(dev.ai_physical_chans) >= 4 and not dev.is_simulated:
                    return dev.name
            # Fallback to simulated device only if explicitly allowed
            if allow_simulated:
                for dev in system.devices:
                    if len(dev.ai_physical_chans) >= 4:
                        return dev.name
        except Exception as e:
            logger.error("Error detecting cDAQ: %s", e)
        return None

    @Slot(bool)
    def _handle_start(self, silent):
        self.start_acquisition(silent=silent)

    def request_start(self, silent=False):
        self._start_requested.emit(silent)

    @Slot()
    def start_acquisition(self, silent=False):
        if not HAS_NIDAQMX:
            msg = "NI-DAQmx driver not installed."
            if not silent: self.daq_error.emit(msg)
            return
            
        if self._running:
            return
            
        dev_name = self.detect_device()
        if dev_name is None:
            msg = "No compatible NI cDAQ module found (need >=4 AI channels)."
            if not silent: self.daq_error.emit(msg)
            return
            
        if not self.load_config():
            msg = "Failed to load sensors_config.json."
            if not silent: self.daq_error.emit(msg)
            return

        try:
            # Force reset the device to clear any zombie locks from previous crashes
            try:
                nidaqmx.system.System.local().devices[dev_name].reset_device()
            except Exception as e:
                logger.warning("Could not reset device %s: %s", dev_name, e)

            self._task = nidaqmx.Task()
            
            for cfg in self._channels_config:
                # Support configuring format "cDAQ1Mod1/ai0" or just "ai0"
                phys_chan = cfg['physical_channel']
                if "/" not in phys_chan:
                    phys_chan = f"{dev_name}/{phys_chan}"
                    
                from nidaqmx.constants import BridgeElectricalUnits, ForceUnits, BridgePhysicalUnits
                
                # Set channel limits to a safe margin above the calibrated span (e.g. 2x span)
                span = cfg.get("span_n", 5000.0)
                safe_max = span * 2.0
                
                self._task.ai_channels.add_ai_force_bridge_two_point_lin_chan(
                    phys_chan,
                    name_to_assign_to_channel=cfg.get("name", ""),
                    min_val=-safe_max,
                    max_val=safe_max,
                    units=ForceUnits.NEWTONS,
                    bridge_config=BridgeConfiguration.FULL_BRIDGE,
                    voltage_excit_source=ExcitationSource.INTERNAL,
                    voltage_excit_val=2.5,
                    nominal_bridge_resistance=350.0,
                    first_electrical_val=0.0,
                    second_electrical_val=cfg["sensitivity_vv"],
                    electrical_units=BridgeElectricalUnits.VOLTS_PER_VOLT,
                    first_physical_val=cfg["intercept_n"],
                    second_physical_val=cfg["span_n"],
                    physical_units=BridgePhysicalUnits.NEWTONS
                )
                
            self._task.timing.cfg_samp_clk_timing(
                rate=self._sample_rate,
                sample_mode=AcquisitionType.CONTINUOUS,
                samps_per_chan=self._batch_size * 4
            )
            
            self._read_buffer = np.zeros((4, self._batch_size), dtype=np.float64)
            self._reader = AnalogMultiChannelReader(self._task.in_stream)
            
            self._running = True
            logger.info("cDAQ acquisition started on %s at %d Hz", dev_name, self._sample_rate)
            self.daq_connected.emit(f"cDAQ: {dev_name}")
            
            self._acquisition_loop()
            
        except nidaqmx.errors.DaqError as e:
            self._running = False
            self._cleanup_task()
            msg = f"cDAQ Error: {e}"
            logger.error(msg)
            self.daq_error.emit(msg)
        except Exception as e:
            self._running = False
            self._cleanup_task()
            msg = f"cDAQ unexpected error: {e}"
            logger.error(msg)
            self.daq_error.emit(msg)

    def _acquisition_loop(self):
        while self._running:
            try:
                self._reader.read_many_sample(
                    self._read_buffer,
                    number_of_samples_per_channel=self._batch_size,
                    timeout=2.0
                )
                
                for i in range(self._batch_size):
                    for ch in range(4):
                        raw_load = self._read_buffer[ch, i]
                        
                        # Median filter
                        self._bi_med_bufs[ch].append(raw_load)
                        median_val = sorted(self._bi_med_bufs[ch])[len(self._bi_med_bufs[ch]) // 2]
                        
                        with self._data_lock:
                            self._bi_loads_filtered[ch] = median_val
                            
                            tared_val = median_val - self._bi_offsets[ch]
                            
                            # Break detection
                            if self._break_detection_enabled:
                                current_mag = abs(tared_val)
                                self._peak_loads[ch] = max(self._peak_loads[ch], current_mag)
                                drop = self._peak_loads[ch] - current_mag
                                
                                if drop > self._break_drop_threshold:
                                    self._break_persist_counts_bi[ch] += 1
                                    if self._break_persist_counts_bi[ch] > 10:
                                        self._break_detection_enabled = False
                                        if self._serial:
                                            for _ in range(3):
                                                self._serial.send_cmd("STOP")
                                                time.sleep(0.02)
                                        axis = "Y" if ch < 2 else "X"
                                        self.break_detected_stop.emit(f"Break detected on {axis}-Axis (Load {ch + 1})!")
                                else:
                                    self._break_persist_counts_bi[ch] = 0
                                    
                    # Preload check
                    with self._data_lock:
                        if self._preload_active:
                            all_done = True
                            for idx in self._preload_indices:
                                if not self._preload_finished_flags[idx]:
                                    all_done = False
                                    val = self._bi_loads_filtered[idx] - self._bi_offsets[idx]
                                    stop = False
                                    if self._preload_target >= 0:
                                        if val >= self._preload_target: stop = True
                                    else:
                                        if val <= self._preload_target: stop = True
                                        
                                    if stop:
                                        if self._serial:
                                            self._serial.send_cmd(f"STOPM{idx+1}")
                                            self._serial.send_cmd(f"STOPM{idx+1}")
                                        self._preload_finished_flags[idx] = True
                            
                            if all_done:
                                self._preload_active = False
                                if self._serial:
                                    self._serial.send_cmd("STOP")
                                self.preload_finished.emit()
                                
                    # Recording
                    if self._is_recording:
                        self._rec_sample_counter += 1
                        if self._rec_sample_counter >= self._rec_decimation:
                            self._rec_sample_counter = 0
                            self._record_snapshot()
                            
                # UI Updates
                current_time = time.perf_counter()
                if current_time - self._last_ui_update >= 0.033:
                    self._emit_ui_update()
                    self._last_ui_update = current_time
                    
                if current_time - self._last_plot_update >= 0.1 and not self._freeze_plots:
                    self._emit_plot_update()
                    self._last_plot_update = current_time
                    
                QCoreApplication.processEvents()
                
            except Exception as e:
                if self._running:
                    self._running = False
                    msg = f"cDAQ read error: {e}"
                    logger.error(msg)
                    self.daq_error.emit(msg)
                break
                
        self._cleanup_task()

    def _cleanup_task(self):
        if self._task is not None:
            try:
                self._task.stop()
            except: pass
            try:
                self._task.close()
            except: pass
            self._task = None
            self._reader = None
            logger.info("cDAQ task closed")

    @Slot()
    def stop_acquisition(self):
        self._running = False

    def is_acquiring(self):
        return self._running

    def _emit_ui_update(self):
        with self._data_lock:
            data = {
                "mode": self._system_mode,
                "uni_load": 0.0,
                "uni_disp": 0.0,
                "bi_loads": [self._bi_loads_filtered[i] - self._bi_offsets[i] for i in range(4)],
                "bi_errors": self._bi_sensor_errors.copy(),
                "uni_zero_L": 0.0,
                "uni_zero_D": 0.0,
                "bi_zeros": self._bi_offsets.copy()
            }
        self.ui_update.emit(data)

    def _emit_plot_update(self):
        with self._data_lock:
            data = {
                "mode": self._system_mode,
                "time": self._time_data.copy(),
                "uni_L": [],
                "uni_D": [],
                "bi_L": [ch.copy() for ch in self._bi_load_data]
            }
        self.plot_update.emit(data)

    def _record_snapshot(self):
        self._rec_total_snapshots += 1
        t_rel = self._rec_total_snapshots / self._sampling_rate
        
        with self._data_lock:
            self._time_data.append(t_rel)
            for i in range(4):
                val = self._bi_loads_filtered[i] - self._bi_offsets[i]
                self._bi_load_data[i].append(val)
                
            if len(self._time_data) > self._max_plot_buffer_size:
                trim = self._max_plot_buffer_size // 5
                self._time_data = self._time_data[trim:]
                for i in range(4):
                    self._bi_load_data[i] = self._bi_load_data[i][trim:]
                    
            if self._csv_writer and self._csv_writer.is_open:
                row = [f"{t_rel:.3f}"] + [f"{self._bi_loads_filtered[i] - self._bi_offsets[i]:.2f}" for i in range(4)]
                if not self._csv_writer.write_row(row):
                    self._is_recording = False
                    self.recording_error.emit("CSV write failed")
                    return
                    
        self.request_image_save.emit()

    def request_start_recording(self, csv_path, mode):
        self._start_recording_requested.emit(csv_path, mode)

    @Slot(str, str)
    def start_recording(self, csv_path, mode):
        with self._data_lock:
            self._system_mode = mode
            self._peak_loads = [0.0] * 4
            self._time_data.clear()
            for l in self._bi_load_data: l.clear()
            
            self._csv_writer = DAQCSVWriter()
            headers = ["Time(s)", "Load 1 (N)", "Load 2 (N)", "Load 3 (N)", "Load 4 (N)"]
            
            if csv_path:
                if not self._csv_writer.open_file(csv_path, headers):
                    logger.error("Failed to open cDAQ CSV")
                    return
            
            self._start_time = time.time()
            self._rec_sample_counter = 0
            self._rec_total_snapshots = 0
            self._is_recording = True

    @Slot()
    def stop_recording(self):
        with self._data_lock:
            self._is_recording = False
            if self._csv_writer:
                self._csv_writer.close_file()
                self._csv_writer = None

    def is_recording(self):
        with self._data_lock:
            return self._is_recording

    def get_current_load(self):
        with self._data_lock:
            return self._bi_loads_filtered[0] - self._bi_offsets[0]

    @Slot(str)
    def set_mode(self, mode):
        with self._data_lock:
            self._system_mode = mode

    @Slot(bool, float)
    def set_break_detection(self, enabled, threshold):
        with self._data_lock:
            self._break_detection_enabled = enabled
            self._break_drop_threshold = abs(threshold)
            if enabled:
                self._peak_loads = [0.0] * 4
                self._break_persist_counts_bi = [0] * 4

    @Slot(int)
    def update_sampling_rate(self, rate):
        with self._data_lock:
            if rate > 0:
                self._sampling_rate = rate
                self._rec_decimation = max(1, self._sample_rate // self._sampling_rate)

    @Slot()
    def zero_uni_load(self):
        pass

    @Slot()
    def zero_uni_disp(self):
        pass

    @Slot(int)
    def zero_bi_single(self, idx):
        with self._data_lock:
            self._bi_offsets[idx] = self._bi_loads_filtered[idx]

    @Slot()
    def zero_bi_all(self):
        with self._data_lock:
            for i in range(4):
                self._bi_offsets[i] = self._bi_loads_filtered[i]

    def request_configure_preload(self, target, indices):
        self._configure_preload_requested.emit(target, indices)

    @Slot(float, list)
    def configure_preload(self, target, indices):
        with self._data_lock:
            self._preload_target = target
            self._preload_indices = indices
            self._preload_finished_flags = [False] * 4
            if indices:
                self._preload_active = True
            else:
                self._preload_active = False
