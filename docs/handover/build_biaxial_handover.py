# docs/handover/build_biaxial_handover.py
"""
Generator script for InsituMicron Biaxial Master Handover Manual.
Produces: docs/handover/InsituMicron_Biaxial_Technical_Handover_Manual_V1.0.docx
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


def build_biaxial_manual(output_path):
    print("Building Biaxial Master Handover Manual...")
    doc = create_base_document()

    # Title Page
    logo_path = os.path.abspath("InsituMicronlogo.jpg")
    add_title_page(
        doc,
        main_title="Master Technical Handover Manual: Biaxial Testing System",
        subtitle="Comprehensive Engineering Guide for Embedded Systems, Multi-Axis Motion, and Electronics (cDAQ & STM32 Architecture)",
        system_model="InsituMicron Biaxial Planar Test Rig (NI cDAQ-9174 + 4-Motor Modbus)",
        doc_version="Software v3.2.1 / Firmware v2.1",
        doc_date="2026-10-23",
        author="Lead Systems and Software Engineer (Departing)",
        reviewer="Engineering Team / Successor",
    )

    # Running Headers and Footers
    setup_header_footer(
        doc,
        short_title="InsituMicron Biaxial System Handover Manual | Technical Reference",
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
        doc, "DANGER", "MULTI-AXIS MECHANICAL BINDING AND PINCH HAZARDS",
        "The biaxial testing system drives four independent high-torque servo motors simultaneously across orthogonal axes (X and Y). "
        "Unsynchronized motion or unequal crosshead displacement can induce severe mechanical skewing, binding the linear guides "
        "and damaging precision load cells. Always ensure emergency stop switches are verified before commanding multi-axis motion."
    )

    add_callout(
        doc, "NOTE", "PURPOSE OF THIS HANDOVER MANUAL",
        "This document provides the complete engineering knowledge transfer required for an incoming embedded, software, "
        "or instrumentation engineer to operate, build, flash, debug, modify, and release the InsituMicron Biaxial Planar "
        "Mechanical Testing System. It covers embedded 4-axis STM32 firmware (Biaxial_firmware.c), non-blocking Modbus RTU "
        "queuing, I2C sensor scanning, the PySide6 Qt GUI biaxial views, NI cDAQ-9174 / NI-9219 bridge acquisition, "
        "multi-axis preload sequencing, and the complete 4-motor electrical hardware bill of materials. Mechanical CAD and "
        "machining drawings are excluded by request."
    )

    add_section_heading(doc, "1.1", "Physical and Logical System Topology")
    doc.add_paragraph(
        "[DOC: README.md, Section Biaxial Mode] The InsituMicron Biaxial Testing System is engineered for planar cruciform "
        "specimen testing. It provides synchronized or independent dual-axis tensile/compressive loading. The instrument "
        "comprises six primary sub-assemblies connected to an industrial host PC:"
    )

    topo_defs = [
        ("Host PC (GUI)", "Runs the PySide6 desktop application under Windows. Hosts the BiaxialMotorControlPanel, CDAQWorker bridge acquisition thread, 4-channel real-time plotting canvas, and multi-channel CSV/Excel streaming engine."),
        ("NI cDAQ-9174 Chassis", "4-slot USB CompactDAQ chassis housing NI C Series measurement modules. Connects directly to host PC over USB 2.0/3.0."),
        ("NI-9219 Bridge Module", "24-bit universal analog input module configured for full-bridge strain gauge load cells (LC1 to LC4). Reads calibrated V/V ratios at up to 100 S/s aggregate hardware rate."),
        ("STM32 Nucleo Controller", "STM32F446RE 32-bit ARM Cortex-M4 microcontroller running Biaxial_firmware.c. Coordinates 4 servo drives over multi-drop RS-485 Modbus RTU, scans 4 auxiliary I2C load cells, and polls PB5 kill switch."),
        ("4x Leadshine Servo Drives", "Four ELD2-RS7020B DC servo drives addressed as Modbus slaves 0x01 (M1), 0x02 (M2), 0x03 (M3), and 0x04 (M4) over a shared RS-485 differential pair."),
        ("4x Leadshine DC Motors", "Four ELVM6040V24FH-M17-HD brushless DC servo motors coupled to precision ballscrews on orthogonal axes: Motors 1 and 2 actuate the Y-axis; Motors 3 and 4 actuate the X-axis."),
    ]
    add_def_table(doc, topo_defs)

    add_section_heading(doc, "1.2", "Multi-Axis Sensor Signal Acquisition Pipeline")
    doc.add_paragraph(
        "[CODE: cdaq_handler.py:CDAQWorker; config/sensors_config.json] Biaxial load measurement supports two distinct "
        "acquisition paths depending on hardware build:"
    )
    doc.add_paragraph(
        "1. Primary Path (NI cDAQ-9174 + NI-9219):\n"
        "   - CDAQWorker runs continuous acquisition on a dedicated QThread at 100 Hz.\n"
        "   - Configured from config/sensors_config.json, which defines sensitivity_vv, intercept_n, and span_n per load cell.\n"
        "   - Linear scaling: Force_N = intercept_n + (raw_vv / sensitivity_vv) * (span_n - intercept_n).\n"
        "   - Each of the 4 channels passes through an independent sliding 3-sample median filter (_bi_med_bufs).\n"
        "   - Offsets (_bi_offsets) are subtracted to display tared loads.\n"
        "   - Emits ui_update (30 Hz) and plot_update (10 Hz) with 4-element load vectors.\n\n"
        "2. Secondary Fallback Path (STM32 I2C2 Stream via SerialHandler):\n"
        "   - If cDAQ is absent, STM32 firmware reads 4 load cells via I2C2 and streams CSV lines: <load1>,<load2>,<load3>,<load4>\\r\\n.\n"
        "   - DataWorker parses these values, scales kN to N (* 1000.0), and flags failed sensors displaying 'ERR'."
    )

    add_section_heading(doc, "1.3", "4-Motor Coordinated Actuation Pipeline")
    doc.add_paragraph(
        "[CODE: gui_test_views.py:BiaxialMotorControlPanel:L529-625; Biaxial_firmware.c:process_command:L444-520] "
        "The Biaxial motor control panel allows independent manual jogging, axial synchronized jogging, or global 4-motor motion:"
    )

    jog_modes = [
        ("Individual Motor Jog", "Operator enters speed in mm/min for Motor i (1 to 4). Converted via: rpm = int((abs(mm_min) * 225) / 4). Dispatches VELi:<rpm>\\n followed by STARTMi\\n."),
        ("X-Axis Axial Jog", "Synchronizes Motors 3 and 4. Converted via: rpm = int((abs(mm_min) * 225) / 8). Dispatches VELX:<rpm>\\n followed by STARTX\\n. STM32 starts both slaves simultaneously."),
        ("Y-Axis Axial Jog", "Synchronizes Motors 1 and 2. Converted via: rpm = int((abs(mm_min) * 225) / 8). Dispatches VELY:<rpm>\\n followed by STARTY\\n. STM32 starts both slaves simultaneously."),
        ("Global Coordinated Jog", "Dispatches VEL:<rpm>\\n followed by START\\n. STM32 broadcasts start command 0x00 to all 4 drives simultaneously."),
        ("Coordinated Preload", "PreloadController advances selected axes until each corresponding load cell reaches target_preload_force. As each motor hits threshold, its individual STOPMi command is sent."),
    ]
    add_def_table(doc, jog_modes)

    add_section_heading(doc, "1.4", "Process and Multi-Axis Threading Model")
    doc.add_paragraph(
        "[DOC: agenst.md] Threading architecture strictly follows the PySide6 Signal/Slot contract to prevent cross-thread deadlocks:"
    )

    threads_biaxial = [
        ("Main Thread (GUI)", "Runs QApplication event loop, BiaxialMotorControlPanel, pyqtgraph 4-curve canvas, and button slot handlers."),
        ("CDAQWorker Thread (QThread)", "Owns continuous NI-DAQmx bridge task, 100 Hz multi-channel reading, digital median filtering, and CSV recording decimation."),
        ("DataWorker Thread (Fallback)", "Parses incoming serial lines from SerialHandler when operating without cDAQ hardware; emits tagged _source='serial' data."),
        ("SerialHandler Read Thread", "Daemon thread reading serial responses from STM32 USART2; handles thread-safe TX command queuing with _write_lock."),
        ("ExcelExportWorker (QThread)", "Background thread generating multi-tab Excel workbooks containing 4-channel load columns and test metadata."),
    ]
    add_header_table(doc, ["Thread / Component", "Operating Contract and Responsibility"], threads_biaxial, [Inches(2.2), Inches(4.07)])

    add_section_heading(doc, "1.5", "Coordinate System and Mechanical Units")
    doc.add_paragraph(
        "Biaxial planar geometry assigns specific physical actuators and load cells to orthogonal axes:"
    )

    geom_table = [
        ("X-Axis (Horizontal)", "Motors 3 & 4 (Leadshine Slaves 0x03 & 0x04)", "Load Cells 3 & 4 (Addresses 0x16 & 0x17 / cDAQ ai2 & ai3)", "Tension pulls outward; Compression pushes inward."),
        ("Y-Axis (Vertical)", "Motors 1 & 2 (Leadshine Slaves 0x01 & 0x02)", "Load Cells 1 & 2 (Addresses 0x14 & 0x15 / cDAQ ai0 & ai1)", "Tension pulls upward/downward; Compression pushes inward."),
        ("Individual Motor Velocity", "RPM = (abs(mm_min) * 225) / 4", "Maximum allowed velocity: 10.0 mm/min (corresponds to 281 RPM).", "Limits enforced in _validate_velocity()."),
        ("Axial Pair Velocity", "RPM = (abs(mm_min) * 225) / 8", "Maximum allowed velocity: 10.0 mm/min (corresponds to 281 RPM).", "Limits enforced in _validate_velocity()."),
    ]
    add_header_table(doc, ["Axis / Motion Type", "Actuator Assignment", "Sensor Assignment", "Kinematic Relationship"], geom_table, [Inches(1.5), Inches(1.6), Inches(1.6), Inches(1.57)])

    # =========================================================================
    # CHAPTER 2: EMBEDDED FIRMWARE ARCHITECTURE (Biaxial_firmware.c)
    # =========================================================================
    add_chapter_heading(doc, 2, "Embedded Firmware Architecture (Biaxial_firmware.c)")

    add_callout(
        doc, "NOTE", "BIAXIAL FIRMWARE SCOPE: 4-MOTOR MODBUS & I2C SENSOR SCAN",
        "[CODE: Biaxial_firmware.c] Unlike the Uniaxial firmware, Biaxial_firmware.c contains active code for BOTH "
        "multi-motor Modbus actuation AND load cell data acquisition (via I2C2). It implements a non-blocking Modbus TX "
        "queue and a non-blocking I2C scan state machine to prevent multi-motor command delays."
    )

    add_section_heading(doc, "2.1", "Microcontroller Core and Clock Configuration")
    doc.add_paragraph(
        "[CODE: Biaxial_firmware.c:SystemClock_Config:L1000-1045] Firmware runs on an STM32 Nucleo-F446RE board. "
        "The clock tree is configured for 84 MHz SYSCLK using the 16 MHz HSI oscillator and PLL:"
    )

    clk_b = [
        ("SYSCLK Core Clock", "84.0 MHz (HSI = 16 MHz / PLLM=16 * PLLN=336 / PLLP=4)."),
        ("AHB Bus Clock (HCLK)", "84.0 MHz (Prescaler DIV1)."),
        ("APB1 Peripheral Clock (PCLK1)", "42.0 MHz (Prescaler DIV2) -> Serves USART2, I2C1, I2C2."),
        ("APB2 Peripheral Clock (PCLK2)", "84.0 MHz (Prescaler DIV1) -> Serves USART1."),
        ("Flash Latency", "FLASH_LATENCY_2 (2 wait states at 3.3V)."),
    ]
    add_def_table(doc, clk_b)

    add_section_heading(doc, "2.2", "Peripheral Allocation and Pin Mapping")
    doc.add_paragraph(
        "[CODE: Biaxial_firmware.c:MX_GPIO_Init, MX_USART1_UART_Init, MX_USART2_UART_Init, MX_I2C2_Init] "
        "Active peripherals and hardware pin assignments:"
    )

    pins_biaxial = [
        ("PA9 / PA10", "USART1 (TX/RX)", "RS-485 Modbus Bus", "115200 8N2", "Multi-drop link to 4 Leadshine servo drives (slaves 0x01 to 0x04)."),
        ("PA2 / PA3", "USART2 (TX/RX)", "Host PC Link", "115200 8N1", "Interrupt RX byte-by-byte (huart2). ASCII commands from GUI; streaming telemetry to GUI."),
        ("PB10 / PB11", "I2C2 (SCL/SDA)", "Load Cell Bus", "100 kHz 7-bit", "Interrogates 4 auxiliary load cell ADCs at 7-bit addresses 0x14, 0x15, 0x16, 0x17."),
        ("PB5", "GPIO Input", "Kill Switch", "Internal Pull-Up", "Active-low physical kill switch input. Polled in main while(1) loop via check_kill_switch()."),
        ("PB8 / PB9", "I2C1 (SCL/SDA)", "Auxiliary I2C", "100 kHz 7-bit", "Configured in MX_I2C1_Init() but unused at runtime."),
    ]
    add_header_table(doc, ["Pin / Port", "Peripheral Function", "Bus / Device Connection", "Mode / Framing", "Operational Role"], pins_biaxial, [Inches(1.0), Inches(1.3), Inches(1.4), Inches(1.0), Inches(1.57)])

    add_section_heading(doc, "2.3", "Non-Blocking Modbus RTU Transmit Queue")
    doc.add_paragraph(
        "[CODE: Biaxial_firmware.c:L99-109, L700-760] Because commanding four motors sequentially with 5 ms inter-frame gaps "
        "would stall the CPU for 20-30 ms, Biaxial_firmware.c implements an asynchronous circular transmit buffer:"
    )
    doc.add_paragraph(
        "- Queue Buffer: mb_tx_queue[32][8] holds up to 32 pre-computed 8-byte Modbus frames.\n"
        "- Modbus_Enqueue(frame, len): Enqueues frames atomically. Drops frames and logs warning if buffer is full.\n"
        "- Modbus_Process(): Called on every iteration of the main loop. Manages state machine (MB_IDLE, MB_TX_IN_PROGRESS, MB_WAITING_GAP).\n"
        "- Inter-Frame Timing: Enforces exactly 5 ms gap (MB_INTER_FRAME_GAP_MS) between consecutive frames using non-blocking HAL_GetTick() comparison."
    )

    add_section_heading(doc, "2.4", "Non-Blocking I2C Load Cell Sensor Scan State Machine")
    doc.add_paragraph(
        "[CODE: Biaxial_firmware.c:L112-121, L213-265, L600-660] Aux load cell digitizers are scanned over I2C2 without "
        "blocking motor commands:"
    )
    doc.add_paragraph(
        "- Slave Addresses: lc_slave_addresses[4] = {0x14, 0x15, 0x16, 0x17}.\n"
        "- Scan State Machine: Transitions through I2C_IDLE -> I2C_TX_CMD -> I2C_WAIT_DELAY -> I2C_RX_DATA.\n"
        "- Sensor Read Protocol: Transmits command byte 0x01 (CMD_READ_LOAD), delays 20 ms (I2C_RESPONSE_DELAY_MS) for the slave "
        "ADC conversion to complete, and reads 4 bytes.\n"
        "- Little-Endian Float Assembly: float_from_le_bytes() unpacks 4 raw bytes into an IEEE 754 32-bit single-precision float.\n"
        "- NaN/Inf Validation: get_load_as_float() checks isnan() and isinf(). If invalid, it backs off 200 ms and re-attempts read."
    )

    add_section_heading(doc, "2.5", "Serial Command Parser Specification (Biaxial)")
    doc.add_paragraph(
        "[CODE: Biaxial_firmware.c:process_command:L444-520] USART2 receives newline-terminated strings. "
        "The parser supports comprehensive multi-motor syntax:"
    )

    b_cmds = [
        ("VEL1:<rpm> to VEL4:<rpm>", "Sets target velocity for Motor 1, 2, 3, or 4 individually.", "VEL1:150\\n", "Stores in motor_velocities[idx]."),
        ("VELX:<rpm>", "Sets synchronized velocity for X-axis pair (Motors 3 & 4).", "VELX:200\\n", "Stores in motor_velocities[2] and [3]."),
        ("VELY:<rpm>", "Sets synchronized velocity for Y-axis pair (Motors 1 & 2).", "VELY:200\\n", "Stores in motor_velocities[0] and [1]."),
        ("VEL:<rpm>", "Sets global velocity for all four motors simultaneously.", "VEL:100\\n", "Updates all 4 elements in motor_velocities."),
        ("STARTM1 to STARTM4", "Starts specific individual motor.", "STARTM1\\n", "Enqueues Modbus start frames for slave 0x01."),
        ("STARTX", "Starts X-axis motor pair (Motors 3 & 4).", "STARTX\\n", "Enqueues start frames for slaves 0x03 and 0x04."),
        ("STARTY", "Starts Y-axis motor pair (Motors 1 & 2).", "STARTY\\n", "Enqueues start frames for slaves 0x01 and 0x02."),
        ("START", "Broadcasts global start to all motors.", "START\\n", "Broadcasts to address 0x00 to start all drives."),
        ("STOPM1 to STOPM4", "Halts specific individual motor.", "STOPM1\\n", "Enqueues Modbus stop frame for specific slave."),
        ("STOPX / STOPY", "Halts specific axial pair.", "STOPX\\n", "Enqueues stop frames for axial motor pair."),
        ("STOP", "Emergency halt for all four motors.", "STOP\\n", "Broadcasts Modbus stop frame 0x00 to halt all drives."),
    ]
    add_header_table(doc, ["Command String", "Functional Scope", "Example Syntax", "Firmware Action"], b_cmds, [Inches(1.5), Inches(2.0), Inches(1.1), Inches(1.67)])

    add_section_heading(doc, "2.6", "Direction-Aware Overload Protection (handle_overload)")
    doc.add_paragraph(
        "[CODE: Biaxial_firmware.c:handle_overload:L401-436] A critical safety feature implemented in the Biaxial firmware "
        "is Direction-Aware Overload Detection:"
    )
    doc.add_paragraph(
        "- Threshold: OVERLOAD_KN_THRESHOLD = 10.0 kN (10,000 N).\n"
        "- Direction Awareness: Overload triggers ONLY if the motor is actively driving into the load (increasing force):\n"
        "  is_loading = (velocity > 0 and force > 0) or (velocity < 0 and force < 0).\n"
        "- Unloading Clearance: If the crosshead is driving in the opposite direction (unloading), the motion is permitted "
        "even if load exceeds 10 kN, allowing the operator to safely back out of an overload condition.\n"
        "- Consecutive Debounce: Requires OVERLOAD_CONSECUTIVE_COUNT (typically 5-10) consecutive exceedances before stopping.\n"
        "- Action on Overload: Transmits broadcast stop (0x00) to halt all motors, resets system state to STATE_IDLE, "
        "and logs OVERLOAD: LC<idx> = <val> KN to USART2."
    )

    # =========================================================================
    # CHAPTER 3: SOFTWARE (GUI) ARCHITECTURE AND MULTI-AXIS PIPELINE
    # =========================================================================
    add_chapter_heading(doc, 3, "Software (GUI) Architecture and Multi-Axis Pipeline")

    add_section_heading(doc, "3.1", "Biaxial User Interface Structure")
    doc.add_paragraph(
        "[CODE: gui_test_views.py:BiaxialMotorControlPanel:L358-683] The Biaxial test view organizes controls into "
        "four dedicated sub-panels:"
    )
    doc.add_paragraph(
        "1. Individual Motor Group: Four independent motor control rows (M1, M2, M3, M4). Each provides a velocity entry "
        "box (mm/min), Forward button, Reverse button, and Stop button.\n"
        "2. Axial Pair Group: Two paired motor controllers (X-Axis: M3+M4; Y-Axis: M1+M2) providing synchronized dual-motor motion.\n"
        "3. Coordinated Preload Group: Allows the operator to select preloading mode (X-Axis, Y-Axis, or Both Axes), "
        "specify Target Load (N) and Preload Velocity (mm/min), and click 'Start Preload'.\n"
        "4. Sensor Display Panel: Displays real-time numeric readouts for Load 1, Load 2, Load 3, and Load 4, with individual "
        "'Zero' buttons and a global 'Zero All' button."
    )

    add_section_heading(doc, "3.2", "NI cDAQ-9174 Acquisition Worker (CDAQWorker)")
    doc.add_paragraph(
        "[CODE: cdaq_handler.py:CDAQWorker] CDAQWorker implements the SensorWorkerProtocol for seamless plug-and-play "
        "integration with MainWindow and RecordingController:"
    )
    doc.add_paragraph(
        "- Bridge Task Configuration: Configures NI-9219 channels for full-bridge strain measurement (BridgeConfiguration.FULL_BRIDGE, "
        "ExcitationSource.INTERNAL, 2.5V excitation voltage).\n"
        "- Batch Reader: Uses AnalogMultiChannelReader reading 10 samples per batch at 100 S/s aggregate rate.\n"
        "- Noise Suppression: Maintains 4 independent sliding 3-sample median buffers (_bi_med_bufs).\n"
        "- Real-Time Preload Checking: Evaluates whether active preload indices have reached the programmed threshold.\n"
        "- Multi-Channel CSV Streaming: Formats streaming CSV rows: [Time, Load1, Load2, Load3, Load4] and flushes each row to disk."
    )

    add_section_heading(doc, "3.3", "Sensor Calibration Configuration (config/sensors_config.json)")
    doc.add_paragraph(
        "[CONFIG: config/sensors_config.json] Biaxial load cell calibration factors are stored in JSON format:"
    )

    add_code_block(
        doc,
        '{\n'
        '  "acquisition": {\n'
        '    "sample_rate_hz": 100,\n'
        '    "batch_size": 10\n'
        '  },\n'
        '  "sensor_0": {\n'
        '    "physical_channel": "ai0",\n'
        '    "name": "LC1",\n'
        '    "sensitivity_vv": 0.00081309,\n'
        '    "intercept_n": -226.25,\n'
        '    "span_n": 9773.75\n'
        '  },\n'
        '  "sensor_1": {\n'
        '    "physical_channel": "ai1",\n'
        '    "name": "LC2",\n'
        '    "sensitivity_vv": 0.00080917,\n'
        '    "intercept_n": 0.0,\n'
        '    "span_n": 10000.0\n'
        '  }\n'
        '}',
        caption="Sample Biaxial Load Cell Calibration Block (config/sensors_config.json)"
    )

    add_section_heading(doc, "3.4", "Multi-Axis Preload Sequencing Controller")
    doc.add_paragraph(
        "[CODE: controllers.py:PreloadController:L426-528] During cruciform specimen mounting, both axes must be preloaded "
        "without inducing diagonal skew. The PreloadController executes a robust multi-motor sequence:"
    )
    doc.add_paragraph(
        "1. Mode selection: Operator selects 'X-Axis' (indices 2, 3), 'Y-Axis' (indices 0, 1), or 'Both Axes' (indices 0, 1, 2, 3).\n"
        "2. Arming worker: PreloadController invokes worker.request_configure_preload(target, indices).\n"
        "3. Motion start: Velocity commands are dispatched to all selected motors.\n"
        "4. Independent latching: As each individual load cell reaches target force, the worker sends STOPMi for that specific motor, "
        "allowing slower motors to catch up.\n"
        "5. Completion: When all selected motors reach target load, a global STOP is dispatched, and preload_finished is emitted."
    )

    # =========================================================================
    # CHAPTER 4: ELECTRONICS AND ELECTRICAL HARDWARE REFERENCE
    # =========================================================================
    add_chapter_heading(doc, 4, "Electronics and Electrical Hardware Reference")

    add_section_heading(doc, "4.1", "Electrical Bill of Materials (Biaxial System)")
    doc.add_paragraph(
        "[CONFIG: Biaxial Electricals BOM.xlsx] The electrical actuation and control system comprises the following components:"
    )

    bom_biaxial = [
        ("1", "DC Servo Driver", "Leadshine ELD2-RS7020B Driver", "Leadshine", "4", "MAS Auto Systems", "24V DC servo drive, RS-485 Modbus RTU interface (slaves 0x01 to 0x04)."),
        ("2", "DC Servo Motor", "ELVM6040V24FH-M17-HD Motor", "Leadshine", "4", "MAS Auto Systems", "Brushless DC servo motors driving 4 ballscrews."),
        ("3", "STM32 Nucleo Board", "Nucleo-F446RE Microcontroller", "ST Microelectronics", "1", "Robu.in", "ARM Cortex-M4 master coordinator running Biaxial_firmware.c."),
        ("4", "Driver Power Cable", "CABLE-RZD1M5-143 (1.5m)", "Leadshine", "4", "MAS Auto Systems", "Shielded 4-conductor power cable connecting driver to motor windings."),
        ("5", "Encoder Cable", "CABLE-BMD1M5-213 (1.5m)", "Leadshine", "4", "MAS Auto Systems", "Shielded differential encoder feedback cable connecting driver to motor."),
        ("6", "NI cDAQ-9174", "4-Slot CompactDAQ Chassis", "National Instruments", "1", "NI India", "USB chassis streaming bridge data to host PC."),
        ("7", "NI-9219 Module", "24-Bit Universal AI Module", "National Instruments", "1", "NI India", "4-channel full-bridge strain measurement for LC1 to LC4."),
        ("8", "Power Supply", "24V 350W Industrial SMPS", "Mean Well", "1", "Local Vendor", "Provides main 24V DC motor bus power."),
        ("9", "Terminal Blocks", "PCT-213 & PCT-215 Lever Blocks", "Generic", "4", "Robu.in", "Power and communication bus distribution blocks."),
        ("10", "Kill Switch", "NC Red Push Button Switch", "Generic", "1", "Local Vendor", "Normally Closed emergency stop button wired to PB5."),
    ]
    add_header_table(doc, ["#", "Part Name", "Description / Purpose", "Manufacturer", "Qty", "Supplier", "Engineering Role"], bom_biaxial, [Inches(0.4), Inches(1.3), Inches(1.4), Inches(1.0), Inches(0.4), Inches(0.9), Inches(0.87)])

    add_section_heading(doc, "4.2", "Power Distribution and Bus Wiring Architecture")
    doc.add_paragraph(
        "[CONFIG: Biaxial Electricals BOM.xlsx] The 24V DC Mean Well power supply must deliver sufficient current to drive "
        "all four servo motors during peak simultaneous acceleration. Wiring guidelines:"
    )
    doc.add_paragraph(
        "- Bus Sizing: The main 24V DC trunk line uses 14 AWG multi-strand copper wire from the power supply terminals.\n"
        "- Star Distribution: Power branches to each of the four Leadshine drives via terminal blocks in a star configuration "
        "to prevent voltage drops across upstream drives during high current draws.\n"
        "- Fuse Protection: Each drive power branch is protected by a 10A fast-acting blade fuse.\n"
        "- Logic Grounding: The STM32 Nucleo ground (GND), 24V power ground (V-), and RS-485 signal ground must be tied together "
        "at a single central star ground point inside the enclosure to eliminate ground loops."
    )

    add_section_heading(doc, "4.3", "RS-485 Modbus Daisy-Chain Bus Topology")
    doc.add_paragraph(
        "[CODE: Biaxial_firmware.c:MX_USART1_UART_Init] All four Leadshine servo drives connect to the STM32 USART1 via a half-duplex RS-485 network:"
    )
    doc.add_paragraph(
        "- Transceiver: An on-board MAX485 (or SN65HVD) RS-485 transceiver translates TTL UART levels (PA9/PA10) to differential RS-485 (A and B lines).\n"
        "- Bus Layout: Wired in a true daisy-chain bus (Driver 1 -> Driver 2 -> Driver 3 -> Driver 4). Star wiring is strictly avoided.\n"
        "- Termination: A 120 Ohm 0.25W termination resistor is installed across A and B terminals at the final drive (Driver 4) "
        "to prevent signal reflections.\n"
        "- Modbus Addresses: Rotary switches or software parameters on the drives are set to addresses: 0x01 (M1), 0x02 (M2), 0x03 (M3), 0x04 (M4)."
    )

    # =========================================================================
    # CHAPTER 5: OPERATIONS, MULTI-AXIS CALIBRATION AND RUNBOOKS
    # =========================================================================
    add_chapter_heading(doc, 5, "Operations, Multi-Axis Calibration and Runbooks")

    add_section_heading(doc, "5.1", "System Cold Startup and Initialization Runbook")
    doc.add_paragraph(
        "Step 1: Inspect 4-Axis Stage Clearances\n"
        "Ensure all four crossheads are positioned away from mechanical hard stops and cruciform grips are clear.\n\n"
        "Step 2: Power Up Enclosure\n"
        "Switch on the main AC isolator. Verify that all four Leadshine drive LED displays show 'rdy', the STM32 board power "
        "LED turns green, and the cDAQ chassis status LED illuminates solid green.\n\n"
        "Step 3: Connect Communications\n"
        "Verify both USB cables (STM32 USB-Serial and NI cDAQ USB) are connected to the PC.\n\n"
        "Step 4: Launch Software and Select Biaxial Mode\n"
        "Launch the InsituMicron GUI. In the top navigation bar, select 'Biaxial' mode. In the Connection tab, connect to the "
        "detected STM32 COM port. Verify that the cDAQ worker connects to NI cDAQ-9174."
    )

    add_section_heading(doc, "5.2", "4-Channel Load Cell Zeroing Procedure")
    doc.add_paragraph(
        "Step 1: Release Specimen Clamps\n"
        "Ensure grips are unclamped and no mechanical force is acting on any load cell.\n\n"
        "Step 2: Execute Global Zero\n"
        "On the Biaxial Sensor Display panel, click 'Zero All'. CDAQWorker captures offsets for LC1, LC2, LC3, and LC4. "
        "Verify that all four displayed loads read 0.0 N (+/- 0.5 N noise band)."
    )

    add_section_heading(doc, "5.3", "Dual-Axis Coordinated Preload Runbook")
    doc.add_paragraph(
        "Step 1: Mount Cruciform Specimen\n"
        "Clamp the cruciform specimen into the four opposing grips, ensuring horizontal and vertical arm alignment.\n\n"
        "Step 2: Configure Preload Parameters\n"
        "Select 'Both Axes' in the Preload panel. Enter Target Load (e.g. 100.0 N) and Preload Velocity (e.g. 0.5 mm/min).\n\n"
        "Step 3: Initiate Preload\n"
        "Click 'Start Preload'. Observe the real-time load bars. As each axis reaches 100.0 N, its corresponding motor pair "
        "halts automatically. Once all 4 load cells reach the threshold, the sequence concludes with an audible prompt."
    )

    add_section_heading(doc, "5.4", "Multi-Channel Test Recording and Export")
    doc.add_paragraph(
        "Step 1: Click 'Start Rec' on the Test Dashboard. The UI generates a timestamped test session folder.\n"
        "Step 2: Click 'Start X' and 'Start Y' (or global 'Start') to begin tension testing.\n"
        "Step 3: Observe all four force curves plotting simultaneously in different colors on the pyqtgraph canvas.\n"
        "Step 4: Upon test completion, click 'Stop Rec'. The ExcelExportWorker generates an Excel file containing individual "
        "columns for Time, Load 1, Load 2, Load 3, and Load 4."
    )

    # =========================================================================
    # CHAPTER 6: FUNCTIONAL SAFETY, KNOWN ISSUES AND RISK REGISTER
    # =========================================================================
    add_chapter_heading(doc, 6, "Functional Safety, Known Issues and Risk Register")

    add_section_heading(doc, "6.1", "Functional Safety and Overload Mechanisms")
    doc.add_paragraph(
        "[CODE: Biaxial_firmware.c:handle_overload:L401-436] Biaxial functional safety is governed by firmware-level overload checking:"
    )
    doc.add_paragraph(
        "- 10 kN Overload Clamp: If any load cell exceeds 10.0 kN while loading, the firmware broadcasts an emergency stop (0x00) "
        "to all four drives, halting motion within milliseconds.\n"
        "- Safe Back-Out Logic: The firmware allows reverse (unloading) motion even while in an overload condition, preventing "
        "mechanical lockup where crossheads cannot be retracted.\n"
        "- Polled Kill Switch: The PB5 kill switch is polled in the main while(1) loop. If triggered, it halts all motors and "
        "transmits an alert string to USART2."
    )

    add_section_heading(doc, "6.2", "Comprehensive Known Issues and Risk Register (Biaxial)")
    doc.add_paragraph(
        "The following register documents verified technical risks and architectural gaps in the Biaxial system:"
    )

    b_risk_headers = ["ID", "Area", "Severity & Class", "Symptom & Impact", "Root Cause", "Workaround", "Permanent Fix Required"]
    b_risk_data = [
        ("RSK-B1", "Firmware", "CRITICAL\nFunctional Safety", "Kill switch response is delayed if I2C bus encounters NACK or timeout.", "Kill switch on PB5 is polled sequentially in while(1); I2C read retries execute blocking HAL_Delay(200).", "Ensure I2C sensor wiring is shielded and noise-free.", "Migrate PB5 kill switch to an EXTI5 hardware interrupt to execute immediate motor stop in ISR."),
        ("RSK-B2", "Firmware", "HIGH\nReliability", "CPU hang during 4-motor motion leaves all 4 servo motors running unmonitored.", "No Independent Watchdog (IWDG) is configured in Biaxial_firmware.c.", "Operator must remain at test rig and use physical AC isolator if CPU locks up.", "Initialize IWDG with 500 ms timeout window; refresh watchdog in the main loop."),
        ("RSK-B3", "Firmware / Kinematics", "HIGH\nEquipment Safety", "Unequal motor speeds across an axial pair (e.g. M1 vs M2) can twist the crosshead and bind linear rails.", "Motors receive individual velocity frames across Modbus; mechanical tolerances can cause slight velocity discrepancies.", "Regularly calibrate ballscrew alignment and inspect linear guides for binding.", "Implement encoder synchronization checking in firmware to stop both motors if positional skew exceeds limit."),
        ("RSK-B4", "Hardware / I2C", "MEDIUM\nReliability", "I2C bus hangs (HAL_I2C_ERROR_BERR or ARLO), halting sensor updates.", "I2C bus noise from servo PWM lines locks up the STM32 I2C peripheral.", "Cycle power to the STM32 controller enclosure.", "Implement I2C software bus recovery (toggle SCL 9 times to clear stuck slave) before re-initializing."),
        ("RSK-B5", "Software / GUI", "MEDIUM\nMaintainability", "Biaxial UI is retained as legacy in GUI v3.2; primary active testing at IIT Patna is Uniaxial.", "Single codebase serves both IIT Jammu Biaxial and IIT Patna Uniaxial deployments.", "Use mode selector on top bar to switch between Uniaxial and Biaxial views.", "Maintain formal separation in interfaces.py and consider branching repository if hardware diverges further."),
    ]
    add_header_table(doc, b_risk_headers, b_risk_data, [Inches(0.6), Inches(0.8), Inches(1.1), Inches(1.2), Inches(1.0), Inches(0.8), Inches(0.77)])

    # =========================================================================
    # CHAPTER 7: ENVIRONMENT SETUP, RELEASE AND MAINTENANCE
    # =========================================================================
    add_chapter_heading(doc, 7, "Environment Setup, Release and Maintenance")

    add_section_heading(doc, "7.1", "Workstation Configuration and Driver Prerequisites")
    doc.add_paragraph(
        "To configure a workstation for Biaxial testing:\n"
        "1. Install NI-DAQmx Runtime (v21.0+) to support cDAQ-9174 chassis communication.\n"
        "2. Connect cDAQ-9174 over USB. Open NI Measurement & Automation Explorer (NI MAX). "
        "Verify that the chassis and NI-9219 module appear under 'Devices and Interfaces'.\n"
        "3. Install Python 3.10 x64 and activate venv310.\n"
        "4. Install dependencies: pip install -r requirements.txt.\n"
        "5. Launch GUI: python main.py."
    )

    add_section_heading(doc, "7.2", "Successor Roadmap: 30, 60, and 90-Day Engineering Priorities")
    doc.add_paragraph("Recommended roadmap for maintaining and upgrading the Biaxial system:")

    b_roadmap = [
        ("First 30 Days (Immediate Stabilization)", 
         "1. Migrate PB5 kill switch to EXTI5 hardware interrupt to resolve Risk RSK-B1.\n"
         "2. Enable STM32 IWDG watchdog with 500 ms timeout.\n"
         "3. Add automated I2C bus recovery routine in Biaxial_firmware.c to handle noisy environments.\n"
         "4. Verify star grounding across all 4 servo drives to eliminate communication noise."),
        ("Next 60 Days (Robustness & Synchrony)", 
         "1. Implement firmware positional skew detection between Motor pairs (M1/M2 and M3/M4).\n"
         "2. Add Modbus queue overflow detection to prevent silent command dropping during rapid jog clicks.\n"
         "3. Update sensors_config.json with certified factory load cell calibration factors."),
        ("Next 90 Days (System Modernization)", 
         "1. Locate and commit the authoritative STM32CubeIDE project files (.ioc, linker script).\n"
         "2. Investigate CAN bus migration for servo drives to replace multi-drop RS-485 for higher bandwidth.\n"
         "3. Standardize automated cruciform test routines with programmable crosshead displacement profiles."),
    ]
    add_header_table(doc, ["Milestone Window", "Detailed Engineering Objectives and Deliverables"], b_roadmap, [Inches(1.8), Inches(4.47)])

    # =========================================================================
    # CHAPTER 8: QUICK REFERENCE CARD
    # =========================================================================
    add_chapter_heading(doc, 8, "Quick Reference Card")

    add_section_heading(doc, "8.1", "Modbus Drive and Sensor Address Mapping")
    qrc_b_addrs = [
        ("Motor 1 (Y-Axis Top)", "0x01", "RS-485 Modbus Slave Address", "VEL1:<rpm>, STARTM1, STOPM1"),
        ("Motor 2 (Y-Axis Bottom)", "0x02", "RS-485 Modbus Slave Address", "VEL2:<rpm>, STARTM2, STOPM2"),
        ("Motor 3 (X-Axis Left)", "0x03", "RS-485 Modbus Slave Address", "VEL3:<rpm>, STARTM3, STOPM3"),
        ("Motor 4 (X-Axis Right)", "0x04", "RS-485 Modbus Slave Address", "VEL4:<rpm>, STARTM4, STOPM4"),
        ("Global Broadcast", "0x00", "RS-485 Broadcast Address", "VEL:<rpm>, START, STOP"),
        ("Load Cell 1 (Y-Axis Top)", "0x14 (7-bit)", "I2C2 Slave Address / cDAQ ai0", "Measures Force on Motor 1"),
        ("Load Cell 2 (Y-Axis Bottom)", "0x15 (7-bit)", "I2C2 Slave Address / cDAQ ai1", "Measures Force on Motor 2"),
        ("Load Cell 3 (X-Axis Left)", "0x16 (7-bit)", "I2C2 Slave Address / cDAQ ai2", "Measures Force on Motor 3"),
        ("Load Cell 4 (X-Axis Right)", "0x17 (7-bit)", "I2C2 Slave Address / cDAQ ai3", "Measures Force on Motor 4"),
    ]
    add_header_table(doc, ["Subsystem / Channel", "Hardware Address", "Bus Interface", "Command / Signal Assignment"], qrc_b_addrs, [Inches(1.6), Inches(1.1), Inches(1.8), Inches(1.77)])

    add_section_heading(doc, "8.2", "Kinematic Formulas and Velocity Limits")
    qrc_b_limits = [
        ("Individual Velocity Limit", "10.0 mm/min (corresponds to 281 RPM)."),
        ("Axial Pair Velocity Limit", "10.0 mm/min (corresponds to 281 RPM)."),
        ("Individual RPM Formula", "RPM = int((abs(mm_min) * 225) / 4)"),
        ("Axial Pair RPM Formula", "RPM = int((abs(mm_min) * 225) / 8)"),
        ("Firmware Overload Cutoff", "10.0 kN (10,000 N) on any individual load cell."),
        ("Modbus Inter-Frame Gap", "5 ms non-blocking delay between transmitted frames."),
        ("I2C Scan Refresh Rate", "50 Hz scheduler tick (SCAN_PERIOD_MS = 20 ms)."),
        ("cDAQ Acquisition Rate", "100 S/s aggregate hardware sampling rate on NI-9219."),
    ]
    add_def_table(doc, qrc_b_limits)

    # Save document
    doc.save(output_path)
    print(f"Biaxial Master Handover Manual saved successfully to: {output_path}")


if __name__ == "__main__":
    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "docs", "handover"))
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "InsituMicron_Biaxial_Technical_Handover_Manual_V1.0.docx")
    build_biaxial_manual(out_file)
