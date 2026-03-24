# interfaces.py
"""
Formal interface contracts for the InsituMicron GUI worker system.

WHY Protocol INSTEAD OF ABC:
    Both DataWorker and DAQWorker inherit from QObject, whose metaclass
    (type(QObject)) conflicts with ABCMeta. A Protocol gives static type
    checking via mypy/pyright without any Qt metaclass issues.

SIGNAL LIMITATION:
    Qt signals are class-level descriptors, not regular methods. Python's
    Protocol cannot enforce their existence. Signals are documented as
    comments in SensorWorkerProtocol for developer reference. The real
    enforcement for signal payloads comes from UIUpdatePayload and
    PlotUpdatePayload TypedDicts.
"""
from __future__ import annotations
from typing import Protocol, TypedDict, runtime_checkable


# =========================================================
# SIGNAL PAYLOAD CONTRACTS
# =========================================================

class UIUpdatePayload(TypedDict):
    """
    Contract for the dict emitted by ui_update.emit(data).
    Both DataWorker and DAQWorker MUST emit this exact structure.

    NOTE: DataWorker includes an additional "_source": "serial" key
    which is intentionally absent from DAQWorker. See _source key docs.
    """
    mode: str
    uni_load: float
    uni_disp: float
    bi_loads: list[float]       # Always length 4
    bi_errors: list[bool]       # Always length 4
    uni_zero_L: float
    uni_zero_D: float
    bi_zeros: list[float]       # Always length 4


class PlotUpdatePayload(TypedDict):
    """
    Contract for the dict emitted by plot_update.emit(data).
    Both DataWorker and DAQWorker MUST emit this exact structure.

    NOTE: DataWorker includes an additional "_source": "serial" key
    which is intentionally absent from DAQWorker. See _source key docs.
    """
    mode: str
    time: list[float]
    uni_L: list[float]
    uni_D: list[float]
    bi_L: list[list[float]]     # Always length 4 (outer)


# =========================================================
# WORKER PROTOCOL
# =========================================================

@runtime_checkable
class SensorWorkerProtocol(Protocol):
    """
    Shared interface contract for DataWorker and DAQWorker.

    Both workers emit identical signals and implement identical slots so
    that MainWindow, RecordingController, and PreloadController can
    connect to either interchangeably. This Protocol enforces the slot
    (method) signatures at static analysis time.

    SIGNALS (cannot be enforced by Protocol — documented for reference):
        ui_update          = Signal(dict)    # Payload: UIUpdatePayload
        plot_update        = Signal(dict)    # Payload: PlotUpdatePayload
        break_detected_stop = Signal(str)
        overload_detected   = Signal(str)
        request_image_save  = Signal()
        recording_error     = Signal(str)
        preload_finished    = Signal()

    _source KEY CONVENTION:
        DataWorker includes "_source": "serial" in ui_update and
        plot_update payloads. DAQWorker intentionally OMITS this key.
        MainWindow.update_graphs uses this to filter out serial data
        when DAQ is active:

            if data.get("_source") == "serial" and self.daq_ctrl.is_active:
                return

        If DAQWorker ever adds "_source": "serial", its data will be
        silently filtered out of the graph. DO NOT add this key to DAQWorker.
    """

    # --- Configuration Slots ---
    def set_mode(self, mode: str) -> None: ...
    def set_break_detection(self, enabled: bool, threshold: float) -> None: ...
    def update_sampling_rate(self, rate: int) -> None: ...

    # --- Zeroing Slots ---
    def zero_uni_load(self) -> None: ...
    def zero_uni_disp(self) -> None: ...
    def zero_bi_single(self, idx: int) -> None: ...
    def zero_bi_all(self) -> None: ...

    # --- Recording Slots ---
    def request_start_recording(self, csv_path: str, mode: str) -> None: ...
    def start_recording(self, csv_path: str, mode: str) -> None: ...
    def stop_recording(self) -> None: ...
    def is_recording(self) -> bool: ...

    # --- Preload Slots ---
    def request_configure_preload(self, target: float, indices: list) -> None: ...
    def configure_preload(self, target: float, indices: list) -> None: ...

    # --- Live Data ---
    def get_current_load(self) -> float: ...
