# docs/handover/build_uniaxial_handover.py
"""
Generator script for InsituMicron Uniaxial Master Handover Manual.
Produces: docs/handover/InsituMicron_Uniaxial_Technical_Handover_Manual_V1.0.docx
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from builder_common import (
    create_base_document, add_title_page, setup_header_footer,
    add_document_control, add_table_of_contents, add_chapter_heading,
    add_section_heading, add_sub_heading, add_callout, add_code_block,
    add_def_table, add_header_table
)
from docx.shared import Inches, Pt, RGBColor


def build_uniaxial_manual(output_path):
    print("Building Uniaxial Master Handover Manual...")
    doc = create_base_document()

    # Title Page
    logo_path = os.path.abspath("InsituMicronlogo.jpg")
    add_title_page(
        doc,
        main_title="Master Technical Handover Manual: Uniaxial Testing System",
        subtitle="Comprehensive Engineering Guide for Embedded Systems, Software Architecture, and Electronics (IIT Patna Deployment)",
        system_model="InsituMicron Uniaxial Test Rig (NI-DAQ USB-6001 + STM32 Nucleo)",
        doc_version="Software v3.2.1 / Firmware v1.2",
        doc_date="2026-10-23",
        author="Lead Systems and Software Engineer (Departing)",
        reviewer="Engineering Team / Successor",
    )

    # Running Headers and Footers
    setup_header_footer(
        doc,
        short_title="InsituMicron Uniaxial System Handover Manual | IIT Patna",
        doc_version="v3.2.1",
        doc_date="2026-10-23",
        logo_path=logo_path if os.path.exists(logo_path) else None,
    )

    # Table of Contents (Dedicated Page 2)
    add_table_of_contents(doc)

    # =========================================================================
    # CHAPTER 1: SYSTEM ARCHITECTURE AND OPERATING PRINCIPLES
    # =========================================================================
    add_chapter_heading(doc, 1, "System Architecture and Operating Principles")

    add_callout(
        doc, "DANGER", "ELECTRICAL AND MECHANICAL SAFETY INTERLOCKS",
        "The uniaxial system exerts forces up to 5000 N (509 kgf). Never operate the test rig without confirming that the "
        "physical Emergency Stop button and electrical limit switches are operational. Software limits in the GUI (5000 N "
        "load cutoff and 0.5 mm to 9.5 mm displacement limits) act as digital guards; they do not replace hardware interlocks."
    )

    add_callout(
        doc, "NOTE", "PURPOSE OF THIS HANDOVER MANUAL",
        "This document provides the complete engineering knowledge transfer required for an incoming embedded, software, "
        "or instrumentation engineer to operate, build, flash, debug, modify, and release the InsituMicron Uniaxial In-Situ "
        "Mechanical Testing System deployed at IIT Patna. It covers embedded STM32 firmware, the PySide6 Qt GUI application, "
        "high-speed NI-DAQ USB-6001 analog acquisition, Edmund Optics coaxial spot illumination control, FLIR camera integration, "
        "and complete electrical interconnects. Mechanical CAD and machining drawings are excluded by request."
    )

    add_section_heading(doc, "1.1", "Physical and Logical System Topology")
    doc.add_paragraph(
        "[DOC: README.md, Section Deployment Site] The InsituMicron Uniaxial Testing System combines high-precision analog "
        "sensor acquisition, closed-loop optical inspection, and digital servo motion control into a unified desktop instrument. "
        "The system comprises six primary physical sub-assemblies connected to an industrial host PC via USB 3.0:"
    )

    topo_defs = [
        ("Host PC (GUI)", "Runs the PySide6 desktop application under Windows 10/11 x64. Hosts the composition root, real-time plotting, streaming CSV recorder, and post-test stress-strain analysis engine."),
        ("NI-DAQ USB-6001", "Hardware-timed Multifunction Data Acquisition unit. Dedicated to high-speed analog acquisition: AI0 reads the amplified load cell voltage, AI1 reads the LVDT displacement transducer voltage, and AO0 drives the coaxial spot light (0 to 10 V DC)."),
        ("STM32 Nucleo Controller", "STM32F446RE (or F401RE) 32-bit ARM Cortex-M4 microcontroller running bare-metal C firmware. Controls servo motor velocity and start/stop trajectories over an isolated RS-485 Modbus RTU link and streams 20 Hz encoder position feedback to the PC."),
        ("Leadshine Servo Drive & Motor", "ELD2-RS7020B DC servo driver coupled to an ELVM6040V24FH-M17-HD DC brushless servo motor with high-resolution magnetic encoder feedback, controlling the precision mechanical load stage."),
        ("Edmund Optics SL162-WHIIC", "High-intensity coaxial spot illumination unit mounted on the optical rail. Brightness is controlled directly from the GUI Image Setup slider via 0 to 10 V analog output from NI-DAQ AO0."),
        ("FLIR Grasshopper3 Camera", "GS3-U3-23S6M-C monochrome scientific camera (1920 x 1200, 5.86 um pixel pitch) coupled to a Navitar 0.7x to 4.5x optical zoom lens, streaming uncompressed live specimen frames over USB 3.0."),
    ]
    add_def_table(doc, topo_defs)

    add_section_heading(doc, "1.2", "End-to-End Sensor Signal Acquisition Chain")
    doc.add_paragraph(
        "[CODE: daq_handler.py:DAQWorker:_acquisition_loop:L480-563] The Uniaxial system acquires primary mechanical data "
        "(force and stroke) via hardware-timed continuous sampling from the NI-DAQ USB-6001 rather than serial polling. "
        "This architectural choice eliminates serial latency and jitter. The signal processing chain executes deterministically "
        "on each sample at 1000 Hz:"
    )

    sig_chain = [
        ("1. Hardware Sampling", "NI-DAQ USB-6001 converts AI0 (Load) and AI1 (Displacement) differential analog voltages at 1000 Hz using an internal hardware sample clock."),
        ("2. Batch Buffer Ingestion", "nidaqmx AnalogMultiChannelReader transfers 100-sample batches (every 100 ms) into a pre-allocated C-contiguous NumPy float64 buffer without GIL contention."),
        ("3. Linear Interpolation", "Raw voltages are converted to physical engineering units: AI0 (-5V to +5V) maps to -4900 N to +4900 N; AI1 (2V to 10V) maps to 0.0 mm to 10.0 mm LVDT stroke."),
        ("4. Median-3 Filter", "A sliding 3-sample median filter suppresses transient electrical impulse noise and electromagnetic spikes from motor switching."),
        ("5. Moving Average-50 Filter", "A 50-sample moving average filter (50 ms time window) smooths Gaussian noise, producing stable force and displacement signals."),
        ("6. Software Tare Subtraction", "Active zero offsets (_load_offset and _disp_offset) captured during user tare are subtracted from the filtered values."),
        ("7. Safety Limit Verification", "Every sample is tested against the 5000 N hard safety limit and the 9.5 mm / 0.5 mm travel limits. If an exceedance occurs, an immediate serial STOP command is dispatched."),
        ("8. Decimated CSV Streaming", "If recording is active, data is decimated to the user-selected rate (default 4 Hz) and flushed to disk row-by-row via DAQCSVWriter."),
        ("9. Rate-Limited UI Emission", "UI numeric displays are updated via ui_update signal at 30 Hz (every 33 ms). Real-time graphs are updated via plot_update signal at 10 Hz (every 100 ms)."),
    ]
    add_def_table(doc, sig_chain)

    add_section_heading(doc, "1.3", "Motion Command and Actuation Pipeline")
    doc.add_paragraph(
        "[CODE: gui_test_views.py:UniaxialMotorControlPanel:L259-285, Uniaxial_firmware.c:process_command:L100-151] "
        "Motor actuation is initiated from the GUI and executed by the STM32 microcontroller. The command pipeline "
        "enforces unit conversion, velocity validation, and deterministic protocol encoding:"
    )

    doc.add_paragraph(
        "1. User input: Operator enters a linear speed in mm/min (maximum limit 5.0 mm/min).\n"
        "2. Software conversion: The GUI converts mm/min to motor RPM using the mechanical lead equation: "
        "RPM = round(speed_mm_min * 800 / 3).\n"
        "3. Serial dispatch: SerialHandler sends ASCII command VEL:<rpm>\\n over USB-Serial (115200 baud, 8N1) to STM32 USART2.\n"
        "4. Firmware parsing: STM32 interrupt handler receives the line; process_command validates that velocity is within "
        "[-3000, 3000] RPM and updates current_velocity.\n"
        "5. START trigger: When START\\n is received, STM32 generates five 8-byte Modbus RTU frames (Mode, Velocity, Acceleration, "
        "Deceleration, Start Control Word) and transmits them via USART1 to the Leadshine driver at 115200 baud (8N2) with 5 ms inter-frame gaps.\n"
        "6. Motor motion: The Leadshine ELD2-RS7020B driver accelerates the servo motor along the programmed trajectory."
    )

    add_section_heading(doc, "1.4", "Process and Threading Architecture")
    doc.add_paragraph(
        "[DOC: agenst.md, Section Critical Thread-Safety Rules] The software employs a multi-threaded architecture to guarantee "
        "that high-frequency sensor acquisition and large disk writes never block the 60 FPS Qt user interface. Cross-thread "
        "communication strictly obeys Qt Signal/Slot semantics:"
    )

    threads_table = [
        ("Main Thread (GUI)", "QApplication event loop, MainWindow composition root, PySide6 widgets, pyqtgraph rendering, and LightController analog output writes (~1 ms)."),
        ("DAQWorker Thread (QThread)", "Owns continuous NI-DAQmx hardware task, 1000 Hz batch acquisition, digital filtering, 5000 N safety checks, and DAQ CSV streaming."),
        ("CameraWorker Thread (QThread)", "FLIR Spinnaker SDK acquisition loop; pulls raw camera frames, updates live preview at 15-20 FPS, and enqueues capture requests."),
        ("ImageSaveWorker (Daemon Thread)", "Python threading.Thread consuming images from save_queue, applying OpenCV scale bar annotations, and writing uncompressed TIFFs to disk."),
        ("SerialHandler Read Thread", "Background daemon thread running blocking readline() calls on pyserial port; emits data_received signals to DataWorker and HomingController."),
        ("ExcelExportWorker (QThread)", "Background worker converting recorded CSV test files into multi-tab formatted Excel workbooks (.xlsx) with embedded metadata upon test completion."),
    ]
    add_header_table(doc, ["Thread / Worker", "Role and Operating Contract"], threads_table, [Inches(2.2), Inches(4.07)])

    add_callout(
        doc, "WARNING", "THREAD-SAFETY RULE: LIST/DICT COPY BEFORE EMISSION",
        "Rule T-2 strictly applies: Any list or dictionary payload emitted across a thread boundary must be copied "
        "prior to emission (e.g. self.plot_update.emit({'time': self._time_data.copy(), ...})). Failure to copy will cause "
        "intermittent Qt crashes and memory corruption when the GUI thread iterates over arrays being modified by the worker."
    )

    add_section_heading(doc, "1.5", "Engineering Units and Conversion Formats")
    doc.add_paragraph(
        "All calculations across the firmware, software, and configuration files adhere to standard physical units:"
    )

    units_data = [
        ("Tensile / Compressive Force", "Newton (N)", "Load cell output: displayed in N (software converts kN to N when reading serial packets)."),
        ("Stroke / Displacement", "Millimeter (mm)", "LVDT displacement sensor output: displayed and recorded in mm."),
        ("Encoder Position", "Pulses (counts)", "Leadshine servo motor optical/magnetic encoder count (E:<counts>)."),
        ("Encoder-to-Displacement", "mm / pulse", "Conversion formula: mm = (pulses / 10000.0) * (3.0 / 800.0) = pulses * 3.75e-7 mm."),
        ("Motor Linear Speed", "mm/min", "Operator speed input: validated to maximum of 5.0 mm/min."),
        ("Motor Rotary Velocity", "RPM", "Leadshine velocity command: RPM = round(mm_min * 800 / 3). 0.375 mm/min = 100 RPM."),
        ("Spot Light Intensity", "Volts DC (V)", "Edmund Optics coaxial light input: 0.0 V (off) to 10.0 V (100% maximum brightness)."),
        ("Stress", "Megapascal (MPa)", "Calculated in analysis engine: Stress = Force (N) / Cross-Section Area (mm2)."),
        ("Strain", "mm/mm (or %)", "Calculated in analysis engine: Strain = Delta Length (mm) / Gauge Length (mm)."),
        ("Young's Modulus", "Megapascal (MPa)", "Slope of linear elastic stress-strain regression: E = Delta Stress / Delta Strain."),
    ]
    add_header_table(doc, ["Measurement / Parameter", "Engineering Unit", "Mathematical Definition / Conversion"], units_data, [Inches(1.8), Inches(1.3), Inches(3.17)])

    # =========================================================================
    # CHAPTER 2: EMBEDDED FIRMWARE ARCHITECTURE (Uniaxial_firmware.c)
    # =========================================================================
    add_chapter_heading(doc, 2, "Embedded Firmware Architecture (Uniaxial_firmware.c)")

    add_callout(
        doc, "WARNING", "FIRMWARE OPERATIONAL SCOPE: MOTOR AND ENCODER ONLY",
        "[CODE: Uniaxial_firmware.c] In the IIT Patna Uniaxial system, the STM32 firmware is dedicated solely to motor "
        "velocity control, trajectory execution, and encoder polling. It does NOT read the load cell or displacement sensor. "
        "All sensor telemetry originates from the NI-DAQ USB-6001. Although MX_I2C1_Init() is present, I2C is not executed in main()."
    )

    add_section_heading(doc, "2.1", "Microcontroller Core and Clock Configuration")
    doc.add_paragraph(
        "[CODE: Uniaxial_firmware.c:SystemClock_Config:L346-384] The firmware targets an STMicroelectronics STM32 Nucleo board "
        "(STM32F446RE or STM32F401RE ARM Cortex-M4 with FPU). The clock tree is configured from the 16 MHz internal High Speed "
        "Internal (HSI) oscillator via the main Phase-Locked Loop (PLL):"
    )

    clock_defs = [
        ("Oscillator Source", "HSI = 16.0 MHz internal RC oscillator."),
        ("PLL Prescaler (PLLM)", "16 -> 16 MHz / 16 = 1.0 MHz PLL input frequency."),
        ("PLL Multiplier (PLLN)", "336 -> 1.0 MHz * 336 = 336.0 MHz VCO output frequency."),
        ("Main PLL Divider (PLLP)", "DIV4 -> 336 MHz / 4 = 84.0 MHz SYSCLK (System Core Clock)."),
        ("AHB Bus Prescaler", "DIV1 -> HCLK = 84.0 MHz (Core, memory, and DMA clock)."),
        ("APB1 Peripheral Clock (PCLK1)", "DIV2 -> 42.0 MHz (serves USART2, timers; timer clock = 84 MHz)."),
        ("APB2 Peripheral Clock (PCLK2)", "DIV1 -> 84.0 MHz (serves USART1, timers, GPIOs)."),
        ("Flash Latency", "FLASH_LATENCY_2 (2 wait states required for 84 MHz at 3.3V)."),
    ]
    add_def_table(doc, clock_defs)

    add_section_heading(doc, "2.2", "Peripheral Allocation and Pin Mapping")
    doc.add_paragraph(
        "[CODE: Uniaxial_firmware.c:MX_GPIO_Init, MX_USART1_UART_Init, MX_USART2_UART_Init, MX_DMA_Init] "
        "The following microcontroller hardware peripherals and pin assignments are active:"
    )

    pins_table = [
        ("PA2 / PA3", "USART2 (TX/RX)", "PC Link", "115200 8N1", "Interrupt RX byte-by-byte (huart2). ASCII commands from GUI; E:<pos> feedback to GUI."),
        ("PA9 / PA10", "USART1 (TX/RX)", "Leadshine Modbus", "115200 8N2", "Polling TX / DMA RX (DMA2 Stream 2 Channel 4). Sends Modbus RTU motion frames."),
        ("PB3", "GPIO Input", "Kill Switch", "Internal Pull-Up", "Active-low physical kill switch input. Polled in main while(1) loop. No EXTI."),
        ("PA5", "GPIO Output", "Status LED (LD2)", "Push-Pull", "On-board Nucleo user LED. Toggles during firmware initialization."),
        ("PC13", "GPIO Input", "User Button (B1)", "No Pull (Ext IT)", "Nucleo on-board blue push button (configured with falling edge EXTI)."),
    ]
    add_header_table(doc, ["Pin / Port", "Peripheral Function", "External Connection", "Mode / Framing", "Operating Description"], pins_table, [Inches(1.0), Inches(1.3), Inches(1.2), Inches(1.0), Inches(1.77)])

    add_section_heading(doc, "2.3", "Motor Driver Modbus RTU Communication Protocol")
    doc.add_paragraph(
        "[CODE: Uniaxial_firmware.c:process_command:L113-151, modbus_crc:L168-180] Motor control frames use Modbus RTU "
        "transmission mode over USART1 (115200 baud, 8 data bits, no parity, 2 stop bits). Modbus slave address is 0x01. "
        "Every frame ends with a 16-bit CRC calculated with polynomial 0xA001 (initial value 0xFFFF, transmitted LSB first):"
    )

    add_code_block(
        doc,
        "// Modbus RTU Register Addresses for Leadshine ELD2-RS Driver:\n"
        "// 0x6200 : Operation Mode (0x0002 = Velocity Mode)\n"
        "// 0x6203 : Target Velocity (signed 16-bit int, RPM)\n"
        "// 0x6204 : Acceleration (16-bit int, ms / 1000 RPM)\n"
        "// 0x6205 : Deceleration (16-bit int, ms / 1000 RPM)\n"
        "// 0x6002 : Control Word (0x0010 = START, 0x0040 = STOP)\n"
        "// 0x602C : Current Encoder Position (32-bit int across 2 registers)\n\n"
        "// Example Frame: Set Velocity to 1000 RPM (0x03E8)\n"
        "// Slave | Function | Reg High | Reg Low | Val High | Val Low | CRC Low | CRC High\n"
        "// 0x01  | 0x06     | 0x62     | 0x03    | 0x03     | 0xE8    | 0x7A    | 0x14",
        caption="Modbus RTU Frame Structure and Leadshine Register Map"
    )

    add_section_heading(doc, "2.4", "Encoder Polling and Position Readback")
    doc.add_paragraph(
        "[CODE: Uniaxial_firmware.c:L280-291, L308-323] The firmware continuously interrogates the Leadshine driver for "
        "optical encoder position at 20 Hz (every 50 ms):"
    )
    doc.add_paragraph(
        "1. Every 50 ms (ENC_POLL_MS), the main loop sends an 8-byte Modbus read frame: [0x01, 0x03, 0x60, 0x2C, 0x00, 0x02, CRC_L, CRC_H].\n"
        "2. USART1 DMA listener (HAL_UARTEx_ReceiveToIdle_DMA) receives the 9-byte response into modbus_rx_buffer.\n"
        "3. Upon completion, HAL_UARTEx_RxEventCallback verifies the 16-bit CRC. If valid, bytes [3..4] (high word) and "
        "[5..6] (low word) are combined into the signed 32-bit integer g_encoder_position.\n"
        "4. The main loop formats this value into ASCII: E:<position>\\r\\n and transmits it via USART2 to the PC.\n"
        "5. If a DMA or UART framing/overrun error occurs, HAL_UART_ErrorCallback clears error flags and signals "
        "g_dma_needs_restart to re-arm DMA listening."
    )

    add_section_heading(doc, "2.5", "Serial Command Parser Specification")
    doc.add_paragraph(
        "[CODE: Uniaxial_firmware.c:process_command:L100-151] USART2 receives newline-terminated strings. "
        "The command parser evaluates the following exact ASCII instructions:"
    )

    cmd_table = [
        ("VEL:<val>", "Sets motor target velocity in RPM. Clamped to [-3000, 3000].", "VEL:1000\\n", "Stores in current_velocity. Does not start motor."),
        ("ACC:<val>", "Sets acceleration rate. Clamped to [0, 3000].", "ACC:50\\n", "Stores in current_acc."),
        ("DEC:<val>", "Sets deceleration rate. Clamped to [0, 3000].", "DEC:50\\n", "Stores in current_dec."),
        ("START", "Triggers sequence of 5 Modbus frames to start motor.", "START\\n", "Motor accelerates to current_velocity."),
        ("STOP", "Dispatches Modbus stop frame (0x6002 = 0x0040).", "STOP\\n", "Motor decelerates to immediate halt."),
    ]
    add_header_table(doc, ["Command", "Function & Parameter Limits", "Example Syntax", "Firmware Action"], cmd_table, [Inches(1.2), Inches(2.2), Inches(1.2), Inches(1.67)])

    add_section_heading(doc, "2.6", "Firmware Safety Mechanisms and Known Limitations")
    doc.add_paragraph(
        "[CODE: Uniaxial_firmware.c:check_kill_switch:L153-167] The firmware implements basic safety handling with several critical caveats:"
    )

    safety_firmware = [
        ("Kill Switch Polling (PB3)", "The kill switch is checked sequentially in the while(1) loop via check_kill_switch(). If pulled LOW, it transmits a Modbus STOP frame and sends KILL\\r\\n to the PC. CRITICAL: It is NOT attached to a hardware EXTI interrupt."),
        ("Watchdog Timer Absence", "Neither the Independent Watchdog (IWDG) nor Window Watchdog (WWDG) is enabled. If the CPU enters a hard fault or hangs in a blocking loop, motor control frames stop updating."),
        ("Host Disconnect Behavior", "There is no heartbeat or keep-alive handshake between PC and STM32. If the USB cable is disconnected during motion, the motor continues running at its commanded speed until a travel limit or obstacle is hit."),
    ]
    add_def_table(doc, safety_firmware)

    # =========================================================================
    # CHAPTER 3: SOFTWARE (GUI) ARCHITECTURE AND DATA PIPELINE
    # =========================================================================
    add_chapter_heading(doc, 3, "Software (GUI) Architecture and Data Pipeline")

    add_section_heading(doc, "3.1", "Composition Root and Application Startup")
    doc.add_paragraph(
        "[CODE: main.py, gui.py:MainWindow:L1207-1350] main.py serves as the thin entry point. It sets the DPI scale factor "
        "to 0.6667 to normalize Windows 150% display scaling, initializes rotating logging to %APPDATA%/InsituMicron GUI/logs/, "
        "applies GLOBAL_STYLESHEET from theme.py, loads app_icon.ico, and instantiates MainWindow. "
        "MainWindow acts as the composition root, instantiating workers, panels, and controllers in strict sequence:"
    )

    startup_seq = [
        ("1. SerialHandler", "Instantiated on main thread; provides serial link to STM32."),
        ("2. DAQWorker & Thread", "Instantiated and moved to dedicated QThread; connects NI-DAQ USB-6001."),
        ("3. LightController", "Instantiated on main thread; binds to NI-DAQ AO0 (0 to 10 V)."),
        ("4. UI Panels", "Instantiates ConnectionPanel, SamplePanel, MotorControlPage, SensorDisplayPanel, SampleInspectionPanel, TestDashboardPanel, and AnalysisReportingPanel."),
        ("5. Domain Controllers", "Instantiates ErrorManager, DAQController, HomingController, PreloadController, RecordingController, CaptureController, and GraphController, passing panel references."),
        ("6. Signal Interconnects", "Connects worker signals to controller slots, panel displays, and cross-thread handlers."),
    ]
    add_def_table(doc, startup_seq)

    add_section_heading(doc, "3.2", "Domain Controllers Breakdown")
    doc.add_paragraph(
        "[CODE: controllers.py] Business logic is cleanly factored out of MainWindow into modular QObject controllers:"
    )

    ctrl_table = [
        ("ErrorManager", "Debounces device disconnection popups (3-second window). Prevents multiple cascading modal alerts when a USB hub is unplugged."),
        ("DAQController", "Manages DAQ acquisition lifecycle, hot-plug periodic polling (every 3 s), device auto-detection, and hardware diagnostic reporting."),
        ("HomingController", "Executes encoder-based homing routines, checks physical travel limits, and persists home_encoder_position in config/home_config.json."),
        ("PreloadController", "Coordinates specimen pre-loading. Drives motor at target RPM until load reaches user threshold, debouncing across 5 consecutive samples."),
        ("RecordingController", "Coordinates synchronized test recording across sensors and camera. Creates timestamped folders, starts CSV streaming, and triggers Excel export."),
        ("CaptureController", "Manages manual optical image snapshots from the live preview, ensuring captured frames are saved to disk with scale bars."),
        ("GraphController", "Controls pyqtgraph live curves, handles toggle between Load vs. Displacement and Stress vs. Strain, and manages rolling display buffers."),
    ]
    add_header_table(doc, ["Controller Name", "Functional Scope and Ownership"], ctrl_table, [Inches(1.8), Inches(4.47)])

    add_section_heading(doc, "3.3", "High-Speed Analog Acquisition Pipeline (DAQWorker)")
    doc.add_paragraph(
        "[CODE: daq_handler.py:DAQWorker] DAQWorker executes continuous hardware-timed sampling on a dedicated QThread. "
        "Key implementation details include:"
    )
    doc.add_paragraph(
        "- Hardware Timing: Uses DAQ sample clock configured for 1000 Hz continuous acquisition (AcquisitionType.CONTINUOUS) "
        "with a 400-sample onboard circular buffer headroom.\n"
        "- Zero Allocation in Loop: Pre-allocates a 2 x 100 NumPy array (_read_buffer) reused across every batch read, "
        "preventing garbage collection pauses.\n"
        "- Linear Calibration: Converts raw voltages via equations: Load_N = Load_min + ratio * (Load_max - Load_min); "
        "Disp_mm = Disp_min + ratio * (Disp_max - Disp_min).\n"
        "- Streaming CSV: Employs DAQCSVWriter to flush every row directly to disk, ensuring zero data loss if power fails.\n"
        "- Rate-Limited Signal Dispatch: Throttles UI signal emissions to 30 Hz and plot updates to 10 Hz."
    )

    add_section_heading(doc, "3.4", "Optical Imaging and Scale Calibration Subsystem")
    doc.add_paragraph(
        "[CODE: gui.py:CameraWorker, ImageSaveWorker; scale_calibration.py] The optical imaging system captures live video "
        "and synchronized test imagery:"
    )
    doc.add_paragraph(
        "- Camera Worker: Interfaces the FLIR Grasshopper3 camera via PySpin SDK. Pulls monochrome 1920 x 1200 frames, "
        "converts them to QImage for 15-20 FPS preview on the SampleInspectionPanel.\n"
        "- Background Saving: When capturing or auto-recording, frames are enqueued into save_queue. ImageSaveWorker "
        "executes asynchronously on a daemon thread, writing uncompressed TIFF files via OpenCV.\n"
        "- Scale Bar Annotation: If scale_bar_enabled is True, draw_scale_bar() looks up magnification in ZOOM_CALIBRATIONS "
        "(0.7x to 4.5x) and burns a calibrated physical scale bar (with rounded dark box and white text) onto the bottom-right corner."
    )

    add_section_heading(doc, "3.5", "Coaxial Spot Light Intensity Controller")
    doc.add_paragraph(
        "[CODE: light_controller.py:LightController] The Edmund Optics spot light requires a 0 to 10 V DC analog control signal. "
        "LightController runs on the main GUI thread because nidaqmx analog output single-point writes execute in under 1 ms. "
        "When the operator drags the brightness slider, set_voltage() clamps the value to [0.0, 10.0] V and writes directly "
        "to NI-DAQ AO0. On application shutdown, shutdown() automatically zeroes the output to extinguish the light."
    )

    add_section_heading(doc, "3.6", "Material Analysis Engine (execution/material_analysis.py)")
    doc.add_paragraph(
        "[CODE: execution/material_analysis.py:MaterialAnalysisEngine] A pure-math Python engine calculating standard mechanical "
        "tensile properties without GUI dependencies:"
    )

    analysis_steps = [
        ("Toe Region Stripping", "Eliminates initial slack and grip seating artifacts below toe_strain_threshold (default 0.001 strain)."),
        ("Elastic Region Scanning", "Scans stress-strain data with a rolling linear regression window to find the region of maximum linearity (highest R2 correlation coefficient, typically > 0.99)."),
        ("Young's Modulus (E)", "Computed as the linear regression slope over the optimal elastic window: E = Delta Stress / Delta Strain (MPa)."),
        ("Yield Strength (0.2% Offset)", "Constructs an offset line parallel to the elastic line shifted by 0.002 strain. Yield point is determined by finding the intersection with the experimental stress-strain curve."),
        ("Ultimate Tensile Strength", "Identifies peak maximum stress (uts_stress) and corresponding strain (uts_strain)."),
        ("Fracture / Break Point", "Detects final specimen rupture point where load drops precipitously below break threshold."),
    ]
    add_def_table(doc, analysis_steps)

    add_section_heading(doc, "3.7", "PDF Report Generator (execution/pdf_reporter.py)")
    doc.add_paragraph(
        "[CODE: execution/pdf_reporter.py:PDFReporter] Generates formal material test reports using ReportLab Platypus. "
        "The generated report includes the InsituMicron corporate logo, test metadata table (Sample ID, Material Type, Width, "
        "Thickness, Cross-Section Area, Gauge Length, Date), mechanical properties summary table (Young's Modulus, Yield Strength, "
        "UTS, Break Stress), operator comments, and high-resolution stress-strain curve plot."
    )

    add_section_heading(doc, "3.8", "Configuration and Settings Persistence")
    doc.add_paragraph(
        "[CODE: settings.py, config/settings.json, config/home_config.json] User preferences and calibration constants are "
        "managed through settings.py. In development mode, settings are stored in config/settings.json. In frozen PyInstaller "
        "mode, settings are stored in %APPDATA%/InsituMicron GUI/config/settings.json. Atomic JSON writes using tempfile.mkstemp "
        "and shutil.move prevent file corruption if the PC powers off mid-write."
    )

    # =========================================================================
    # CHAPTER 4: ELECTRONICS AND HARDWARE REFERENCE
    # =========================================================================
    add_chapter_heading(doc, 4, "Electronics and Hardware Reference")

    add_section_heading(doc, "4.1", "Electrical Bill of Materials (Uniaxial System)")
    doc.add_paragraph(
        "[CONFIG: Uniaxial Sytem electricals BOM.xlsx] The electrical system comprises the following components, "
        "procured and assembled for the IIT Patna Uniaxial testing rig:"
    )

    bom_rows = [
        ("1", "STM32 Nucleo Board", "Microcontroller coordinator (Cortex-M4)", "ST Microelectronics", "1", "Robu.in", "Runs Uniaxial_firmware.c; Modbus master on USART1, PC link on USART2."),
        ("2", "DC Servo Driver", "Leadshine ELD2-RS7020B Driver", "Leadshine", "1", "MAS Auto Systems", "24V DC servo drive, RS-485 Modbus RTU interface."),
        ("3", "DC Servo Motor", "ELVM6040V24FH-M17-HD Motor", "Leadshine", "1", "MAS Auto Systems", "Brushless DC servo motor with incremental encoder feedback."),
        ("4", "NI-DAQ USB-6001", "Multifunction DAQ Unit", "National Instruments", "1", "NI India", "14-bit analog input (AI0: Load, AI1: LVDT), analog output (AO0: Light)."),
        ("5", "Coaxial Spot Light", "SL162-WHIIC White Spot Light", "Edmund Optics", "1", "Edmund Optics", "Coaxial specimen illumination driven by 0 to 10 V DC from AO0."),
        ("6", "Scientific Camera", "Grasshopper3 GS3-U3-23S6M-C", "FLIR / Teledyne", "1", "FLIR India", "Monochrome 2.3 MP USB 3.0 vision camera."),
        ("7", "Optical Zoom Lens", "Navitar Zoom 6000 (0.7x-4.5x)", "Navitar", "1", "Navitar / Edmund", "Modular precision zoom lens with manual detent collar."),
        ("8", "RC Filter Circuit", "10k/1k Resistors + 22uF Caps", "Generic", "1", "Robu.in", "Custom hardware low-pass filter on 5x7cm perfboard for analog conditioning."),
        ("9", "E-Stop Push Button", "NC Red Push Button Switch", "Generic", "1", "Amazon.in", "Normally Closed red latching emergency stop mushroom switch."),
        ("10", "Start Push Button", "NO Green Push Button Switch", "Generic", "1", "Amazon.in", "Normally Open momentary start push button."),
        ("11", "Aviation Connectors", "GX16 3-Pin & 5-Pin Sockets", "Generic", "2", "Flyrobo.in", "Chassis-mount circular aviation connectors for external sensors."),
        ("12", "USB 3.0 Cable", "BlueRigger Type-A Male to Male", "BlueRigger", "1", "Amazon.in", "High-speed shielded USB connection between PC and internal hub."),
        ("13", "Terminal Blocks", "KF301 & PCT-213 Screw Blocks", "Generic", "6", "Robu.in", "Internal power and signal distribution blocks."),
        ("14", "Power Supply", "24V DC Industrial SMPS", "Mean Well / Generic", "1", "Local Vendor", "Provides 24V DC logic and motor bus power."),
    ]
    add_header_table(doc, ["#", "Part Name", "Description / Purpose", "Manufacturer", "Qty", "Supplier", "Engineering Role"], bom_rows, [Inches(0.4), Inches(1.3), Inches(1.4), Inches(1.0), Inches(0.4), Inches(0.9), Inches(0.87)])

    add_section_heading(doc, "4.2", "Signal Conditioning Circuitry (Custom RC Filter)")
    doc.add_paragraph(
        "[CONFIG: Uniaxial Sytem electricals BOM.xlsx] Analog load cell amplifier outputs are susceptible to high-frequency "
        "electromagnetic switching noise radiated by the servo drive pulse-width modulation (PWM). A hardware RC low-pass "
        "filter is assembled on a 5x7 cm single-sided perfboard between the sensor amplifier and NI-DAQ analog inputs:"
    )
    doc.add_paragraph(
        "- Resistors: 10 kOhm metal film (0.5W) in series with analog signal line; 1 kOhm pull-down resistor.\n"
        "- Capacitors: 22 uF 50V polarized electrolytic capacitors to signal ground.\n"
        "- Cutoff Frequency: fc = 1 / (2 * pi * R * C) = 1 / (2 * 3.14159 * 10000 * 22e-6) approx 0.72 Hz. "
        "This aggressively suppresses all 50 Hz mains hum and motor carrier noise prior to DAQ digitization."
    )

    add_section_heading(doc, "4.3", "NI-DAQ USB-6001 Wiring Pinout")
    doc.add_paragraph(
        "[DOC: NI_DAQ_USB_6001.pdf, README.md] The NI-DAQ USB-6001 terminal blocks are wired in Differential mode (DIFF):"
    )

    daq_pins = [
        ("AI0 (Pin 2)", "Load Cell Amplifier (+)", "Differential analog positive input for force signal."),
        ("AI4 (Pin 3)", "Load Cell Amplifier (-)", "Differential analog negative reference input for force signal."),
        ("AI1 (Pin 5)", "LVDT Conditioner (+)", "Differential analog positive input for displacement stroke signal."),
        ("AI5 (Pin 6)", "LVDT Conditioner (-)", "Differential analog negative reference input for displacement signal."),
        ("AO0 (Pin 14)", "Spot Light Control (+)", "Analog voltage output (0 to 10 V DC) driving light intensity."),
        ("AOGND (Pin 15)", "Spot Light Ground (-)", "Analog output common ground return."),
    ]
    add_header_table(doc, ["Terminal Pin", "Sensor Connection", "Signal Description"], daq_pins, [Inches(1.5), Inches(2.0), Inches(2.77)])

    # =========================================================================
    # CHAPTER 5: OPERATIONS, CALIBRATION AND RUNBOOKS
    # =========================================================================
    add_chapter_heading(doc, 5, "Operations, Calibration and Runbooks")

    add_section_heading(doc, "5.1", "System Cold Startup and Initialization Runbook")
    doc.add_paragraph("Follow this sequence every time the physical testing rig is powered on:")
    doc.add_paragraph(
        "Step 1: Verify Mechanical Clearances\n"
        "Inspect the load frame. Ensure no tools, stray wires, or foreign objects are lodged in the ball screw or crosshead.\n\n"
        "Step 2: Power Up Enclosure\n"
        "Switch on the main 230V AC isolator. Verify that the 24V DC power supply LED illuminates, the Leadshine driver display "
        "shows 'rdy' (ready), and the STM32 Nucleo board power LED turns green.\n\n"
        "Step 3: Connect USB Cables\n"
        "Ensure the USB 3.0 cable from the instrument enclosure is firmly connected to an active USB 3.0 port on the host PC.\n\n"
        "Step 4: Launch Software\n"
        "Double-click the InsituMicron GUI desktop shortcut (or run 'python main.py' in development). Observe the startup log in %APPDATA%/InsituMicron GUI/logs/.\n\n"
        "Step 5: Verify Connection Panel\n"
        "Navigate to the Connection tab. The NI-DAQ status box should display 'Connected (Dev1)'. In the serial port dropdown, "
        "select the detected STM32 COM port and click 'Connect'. The status box will change from red to green ('Connected @ 115200')."
    )

    add_section_heading(doc, "5.2", "Sensor Tare and Offset Zeroing Procedure")
    doc.add_paragraph("Sensors must be zeroed prior to mounting and testing each specimen:")
    doc.add_paragraph(
        "Step 1: Unload Stage Clearance\n"
        "Ensure the grip fixtures are free of specimen contact and no mechanical pre-load is applied.\n\n"
        "Step 2: Tare Load Cell\n"
        "On the Sensor Display panel, click 'Tare Load'. The software captures the current filtered force reading into _load_offset. "
        "The displayed Force (N) will reset to 0.0 N.\n\n"
        "Step 3: Tare LVDT Displacement\n"
        "Click 'Tare Disp'. The software captures the current filtered LVDT reading into _disp_offset. "
        "The displayed Displacement (mm) will reset to 0.000 mm."
    )

    add_section_heading(doc, "5.3", "Motor Homing and Preload Execution Runbook")
    doc.add_paragraph(
        "Step 1: Set Reference Home\n"
        "Jog the crosshead to the desired specimen loading position. In the Uniaxial Motor Control panel, click 'Set Home'. "
        "The current encoder count is saved to config/home_config.json.\n\n"
        "Step 2: Execute Preload\n"
        "Enter Target Load (e.g. 50.0 N) and Preload Speed (e.g. 0.375 mm/min). Click 'Preload'. The motor will advance toward "
        "the specimen. DAQWorker monitors the load cell in real time. Once force reaches 50.0 N for 5 consecutive samples, "
        "the motor halts automatically, and the UI sounds a completion tone."
    )

    add_section_heading(doc, "5.4", "Test Execution and Recording Runbook")
    doc.add_paragraph(
        "Step 1: Configure Sample Parameters\n"
        "In the Sample Details panel, input Sample ID (e.g. Al6061_T6_01), select geometry (Rectangular or Circular), "
        "and enter dimensions (Width, Thickness, Gauge Length).\n\n"
        "Step 2: Start Recording\n"
        "On the Test Dashboard, click 'Start Rec'. The UI creates a timestamped folder: {SampleID}_{YYYYMMDD_HHMMSS}/. "
        "CSV data streaming begins at 4 Hz, and synchronized camera TIFF saving is initiated.\n\n"
        "Step 3: Start Motor Motion\n"
        "Set the desired testing speed (e.g. 1.0 mm/min) in the Uniaxial Motor Control panel and click 'Start Motor'. "
        "Observe the real-time Load vs. Displacement curve updating on the pyqtgraph canvas.\n\n"
        "Step 4: Specimen Rupture & Stop\n"
        "If Break Detection is enabled, the motor halts automatically upon specimen rupture. Otherwise, click 'Stop Motor'. "
        "Click 'Stop Rec' to flush CSV buffers and trigger the automated Excel export."
    )

    add_section_heading(doc, "5.5", "Post-Test Analysis and PDF Report Export Runbook")
    doc.add_paragraph(
        "Step 1: Open Analysis Tab\n"
        "Navigate to the 'Analysis & Reporting' tab. Click 'Load Test Data (CSV)' and select the recorded CSV file.\n\n"
        "Step 2: Verify Dimensions\n"
        "Confirm that Cross-Section Area (mm2) and Gauge Length (mm) match the physical specimen.\n\n"
        "Step 3: Run Analysis\n"
        "Click 'Run Analysis'. The MaterialAnalysisEngine calculates Young's Modulus, 0.2% Offset Yield Strength, UTS, and Break point. "
        "The fitted modulus line and 0.2% offset curve are plotted on the canvas.\n\n"
        "Step 4: Generate Report\n"
        "Click 'Generate PDF Report'. Select destination folder. A professional PDF report is compiled via ReportLab."
    )

    # =========================================================================
    # CHAPTER 6: FUNCTIONAL SAFETY, KNOWN ISSUES AND RISK REGISTER
    # =========================================================================
    add_chapter_heading(doc, 6, "Functional Safety, Known Issues and Risk Register")

    add_section_heading(doc, "6.1", "Functional Safety Architecture")
    doc.add_paragraph(
        "[CODE: daq_handler.py:L537-563] The Uniaxial system implements automated multi-tiered software safety guards:"
    )

    safety_tiers = [
        ("5000 N Hard Force Cutoff", "Checks both displayed tared load and raw non-tared load every millisecond. If force >= +5000 N (compression) and driving forward, or <= -5000 N (tension) and driving reverse, an immediate STOP command is dispatched, motor direction is forced to 0, and a critical modal dialog is raised."),
        ("Displacement Upper Limit (9.5 mm)", "Monitors raw LVDT displacement. If position >= 9.5 mm, compression motion is immediately halted. Motion is permitted only in the tension (retract) direction."),
        ("Displacement Lower Warning (0.5 mm)", "Warns the operator if displacement drops below 0.5 mm (indicating sensor probe loss of contact). Does not stop motor to allow manual recovery."),
        ("Automated Break Detection", "Tracks peak specimen load. If load drops by more than break_threshold_n (default 1000 N) across 10 consecutive samples, the motor is halted immediately."),
    ]
    add_def_table(doc, safety_tiers)

    add_section_heading(doc, "6.2", "Comprehensive Known Issues and Risk Register")
    doc.add_paragraph(
        "The following register documents all verified open technical risks, functional safety defects, and architectural gaps "
        "identified in the Uniaxial system codebase:"
    )

    risk_headers = ["ID", "Area", "Severity & Class", "Symptom & Impact", "Root Cause", "Workaround", "Permanent Fix Required"]
    risk_data = [
        ("RSK-01", "Firmware / GUI", "CRITICAL\nFunctional Safety", "Kill switch pressed on hardware stops motor but GUI shows no popup and remains in running state.", "Uniaxial_firmware.c transmits KILL\\r\\n; DataWorker.process_line() has no handler for this string and drops it silently.", "Operator must visually observe hardware stop and manually click UI Stop.", "Add explicit 'if line.startswith(\"KILL\"): self.overload_detected.emit(...)' handler in DataWorker and DAQWorker."),
        ("RSK-02", "Firmware", "HIGH\nFunctional Safety", "Kill switch response is delayed if main loop hangs or blocks in HAL_Delay.", "Kill switch on PB3 is polled in while(1) loop via check_kill_switch(); it is not assigned to an EXTI hardware interrupt.", "Ensure main loop contains no long blocking delays.", "Reconfigure PB3 to EXTI3 falling-edge interrupt in STM32CubeIDE to execute immediate motor stop in ISR."),
        ("RSK-03", "Firmware", "HIGH\nReliability", "If STM32 firmware crashes or enters hard fault during test, motor continues running indefinitely.", "No Independent Watchdog (IWDG) or Window Watchdog (WWDG) is initialized in Uniaxial_firmware.c.", "Operator must remain at machine and press physical E-stop if CPU hangs.", "Initialize IWDG with a 500 ms timeout window; refresh watchdog in the main while(1) loop."),
        ("RSK-04", "Software / Build", "MEDIUM\nMaintainability", "ModuleNotFoundError: No module named 'execution' in certain frozen or clean-clone environments.", "execution/ folder lacks an __init__.py file, causing Python to treat it as an unresolvable namespace package.", "Run from repo root with execution/ in working directory.", "Add an empty __init__.py file into execution/ and commit to repository."),
        ("RSK-05", "Packaging", "MEDIUM\nDeployment", "Installed application fails to launch on clean Windows machines without prior developer setup.", "installer.iss [Run] section is empty; NI-DAQmx runtime, STM32 VCP driver, and FLIR Spinnaker SDK are not bundled.", "Manually install NI-DAQmx runtime and Spinnaker SDK prior to running setup.", "Bundle driver installers into installer.iss [Files] and invoke silent installations in [Run] section."),
        ("RSK-06", "Software / GUI", "LOW\nData Quality", "Redundant settings.json file in root directory causes confusion over active configuration.", "settings.py writes to config/settings.json (or APPDATA); root settings.json is an unreferenced leftover.", "Edit settings exclusively via GUI Settings tab.", "Delete orphaned settings.json from repository root."),
    ]
    add_header_table(doc, risk_headers, risk_data, [Inches(0.6), Inches(0.8), Inches(1.1), Inches(1.2), Inches(1.0), Inches(0.8), Inches(0.77)])

    # =========================================================================
    # CHAPTER 7: ENVIRONMENT SETUP, BUILD, RELEASE AND ROADMAP
    # =========================================================================
    add_chapter_heading(doc, 7, "Environment Setup, Build, Release and Roadmap")

    add_section_heading(doc, "7.1", "Clean Machine Setup Procedure")
    doc.add_paragraph("To configure a new developer or production workstation from scratch:")
    doc.add_paragraph(
        "1. Install Python 3.10.x 64-bit from python.org. Ensure 'Add Python to PATH' is checked.\n"
        "2. Install NI-DAQmx Runtime (v21.0 or newer) from ni.com to install nicaiu.dll.\n"
        "3. Install Teledyne FLIR Spinnaker SDK (v3.1+) for camera USB drivers.\n"
        "4. Create and activate virtual environment:\n"
        "   python -m venv venv310\n"
        "   venv310\\Scripts\\activate\n"
        "5. Install Python dependencies:\n"
        "   pip install -r requirements.txt\n"
        "6. Install PySpin wheel matching Python 3.10:\n"
        "   pip install spinnaker_python-3.10.0.121-cp310-cp310-win_amd64.whl\n"
        "7. Launch application:\n"
        "   python main.py"
    )

    add_section_heading(doc, "7.2", "PyInstaller and Inno Setup Release Build Protocol")
    doc.add_paragraph(
        "To compile a standalone production installer from source:\n"
        "Step 1: Execute PyInstaller compilation:\n"
        "   pyinstaller build.spec\n"
        "This outputs the onedir binary collection into dist/InsituMicronGUI/.\n\n"
        "Step 2: Compile Inno Setup Installer:\n"
        "Open installer.iss in Inno Setup Compiler 6.x and click Compile (or run: 'iscc installer.iss'). "
        "The finalized setup executable is output to Output/InsituMicron_GUI_v3.2.1_Setup.exe."
    )

    add_section_heading(doc, "7.3", "Successor Roadmap: 30, 60, and 90-Day Engineering Priorities")
    doc.add_paragraph("Recommended technical priorities for the incoming engineer:")

    roadmap_items = [
        ("First 30 Days (Immediate Stabilization)", 
         "1. Add 'KILL' serial message handling to DataWorker.process_line() to resolve Safety Risk RSK-01.\n"
         "2. Create execution/__init__.py and verify clean PyInstaller compilation.\n"
         "3. Add STM32 Independent Watchdog (IWDG) to Uniaxial_firmware.c with 500 ms timeout.\n"
         "4. Verify physical E-stop wiring cut path directly on the IIT Patna machine."),
        ("Next 60 Days (Robustness & Automation)", 
         "1. Migrate PB3 kill switch from polling to EXTI3 falling-edge interrupt in firmware.\n"
         "2. Bundle NI-DAQmx minimal runtime and STM32 VCP drivers into Inno Setup installer.iss.\n"
         "3. Implement automated motor stall detection (stop if motor commanded but encoder moves < 10 pulses in 2 s).\n"
         "4. Establish automated unit tests for MaterialAnalysisEngine across full test matrices."),
        ("Next 90 Days (Product Maturation)", 
         "1. Locate and commit authoritative STM32CubeIDE project files (.ioc, linker script, startup assembly).\n"
         "2. Integrate continuous hardware-triggered camera snapshot synchronization via NI-DAQ digital outputs.\n"
         "3. Complete empirical micrometer calibration across all Navitar zoom positions and commit updated scale table."),
    ]
    add_header_table(doc, ["Milestone Window", "Detailed Engineering Objectives and Deliverables"], roadmap_items, [Inches(1.8), Inches(4.47)])

    # =========================================================================
    # CHAPTER 8: QUICK REFERENCE CARD
    # =========================================================================
    add_chapter_heading(doc, 8, "Quick Reference Card")

    add_section_heading(doc, "8.1", "Serial Command and Message Reference")
    qrc_cmds = [
        ("VEL:<rpm>", "PC -> STM32", "Command target motor velocity in RPM (clamped -3000 to +3000)."),
        ("START", "PC -> STM32", "Initiate motor trajectory at current velocity."),
        ("STOP", "PC -> STM32", "Immediately halt motor motion."),
        ("E:<counts>", "STM32 -> PC", "20 Hz encoder position telemetry (signed 32-bit integer)."),
        ("KILL", "STM32 -> PC", "Transmitted when physical PB3 kill switch is triggered."),
        ("OVERLOAD:...", "STM32 -> PC", "Transmitted when firmware overload threshold is reached."),
    ]
    add_header_table(doc, ["Message String", "Direction", "Functional Purpose"], qrc_cmds, [Inches(1.5), Inches(1.2), Inches(3.57)])

    add_section_heading(doc, "8.2", "System Limits and Default Settings")
    qrc_limits = [
        ("Max Linear Speed", "5.0 mm/min (corresponds to 1333 RPM)."),
        ("Hard Force Limit", "+/- 5000.0 N (compression and tension)."),
        ("Displacement Upper Guard", "9.5 mm raw non-tared LVDT position (blocks compression)."),
        ("Displacement Lower Guard", "0.5 mm raw non-tared LVDT position (warns of probe detachment)."),
        ("Break Detection Threshold", "1000.0 N drop across 10 consecutive samples."),
        ("Default Acquisition Rate", "1000 Hz continuous hardware-timed sampling via NI-DAQ USB-6001."),
        ("Default UI Display Rate", "30 Hz rate-limited Qt signal dispatch."),
        ("Default Plot Refresh Rate", "10 Hz rate-limited pyqtgraph canvas update."),
        ("Default CSV Recording Rate", "4 Hz (decimated 1:250 from 1000 Hz hardware stream)."),
    ]
    add_def_table(doc, qrc_limits)

    # Save document
    doc.save(output_path)
    print(f"Uniaxial Master Handover Manual saved successfully to: {output_path}")


if __name__ == "__main__":
    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "docs", "handover"))
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "InsituMicron_Uniaxial_Technical_Handover_Manual_V1.0.docx")
    build_uniaxial_manual(out_file)
