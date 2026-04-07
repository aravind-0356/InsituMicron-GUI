# light_controller.py
"""
Light Intensity Controller for Edmund Optics SL162-WHIIC Coaxial Spot Light.

Controls the light via NI DAQ USB-6001 analog output channel AO0.
The light accepts 0–10V DC for intensity control (0V = off, 10V = max).

Design Notes:
    - Completely independent of the DAQ acquisition task in daq_handler.py.
    - nidaqmx analog output writes are near-instantaneous (~1ms), so this
      runs on the main thread — no dedicated QThread needed.
    - Gracefully degrades if NI-DAQmx driver/device is unavailable.
    - Always resets to 0V on shutdown (light off).
"""

from logging_config import get_logger

logger = get_logger(__name__)

# Conditional import — app runs without NI-DAQmx driver
try:
    import nidaqmx
    from nidaqmx.constants import TerminalConfiguration
    HAS_NIDAQMX = True
except Exception:
    HAS_NIDAQMX = False


class LightController:
    """
    Controls the Edmund Optics coaxial spot light via NI DAQ AO0.

    Usage:
        ctrl = LightController()
        ctrl.set_voltage(5.0)   # Set to 50% intensity
        ctrl.shutdown()         # Turn off light and release hardware
    """

    AO_CHANNEL = "ao0"       # Analog output channel
    MIN_VOLTAGE = 0.0        # Light off
    MAX_VOLTAGE = 10.0       # Maximum intensity

    def __init__(self, device_name="Dev1"):
        self._device_name = device_name
        self._task = None
        self._current_voltage = 0.0
        self._available = False

        if not HAS_NIDAQMX:
            logger.warning("LightController: NI-DAQmx not available — light control disabled.")
            return

        # Try to initialise the AO task
        try:
            self._task = nidaqmx.Task("LightIntensity")
            phys_channel = f"{self._device_name}/{self.AO_CHANNEL}"
            self._task.ao_channels.add_ao_voltage_chan(
                phys_channel,
                name_to_assign_to_channel="Light",
                min_val=self.MIN_VOLTAGE,
                max_val=self.MAX_VOLTAGE,
            )
            # Write initial 0V (light off)
            self._task.write(0.0)
            self._available = True
            logger.info("LightController: Initialised on %s (0V — light off)", phys_channel)
        except Exception as e:
            logger.warning("LightController: Could not initialise AO task: %s", e)
            self._cleanup_task()

    @property
    def is_available(self) -> bool:
        """True if the DAQ analog output is ready for writes."""
        return self._available

    def set_voltage(self, voltage: float) -> bool:
        """
        Set the analog output voltage (clamped to 0–10V).

        Args:
            voltage: Desired voltage (0.0 to 10.0).

        Returns:
            True if the write succeeded, False otherwise.
        """
        voltage = max(self.MIN_VOLTAGE, min(voltage, self.MAX_VOLTAGE))

        if not self._available or self._task is None:
            logger.debug("LightController: write skipped (not available)")
            return False

        try:
            self._task.write(voltage)
            self._current_voltage = voltage
            return True
        except Exception as e:
            logger.error("LightController: write failed: %s", e)
            return False

    def shutdown(self):
        """Turn off the light (0V) and release the DAQ task."""
        if self._available and self._task is not None:
            try:
                self._task.write(0.0)
                logger.info("LightController: Light set to 0V on shutdown.")
            except Exception as e:
                logger.warning("LightController: Could not zero on shutdown: %s", e)
        self._cleanup_task()

    def _cleanup_task(self):
        """Stop and close the nidaqmx Task."""
        if self._task is not None:
            try:
                self._task.stop()
            except Exception:
                pass
            try:
                self._task.close()
            except Exception:
                pass
            self._task = None
        self._available = False
