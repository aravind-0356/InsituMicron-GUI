---
name: knowledge-transfer-content
description: Use when asked to prepare, audit, or extend a knowledge transfer (handover) document set for the InsituMicron creep / tensile test systems. Defines what must be covered (firmware, software, hardware, architecture, operations, risks), how to gather evidence from the repo, and how to mark gaps instead of guessing.
---

# Knowledge Transfer Content Skill

## 1. Purpose

Produce handover material that lets a competent embedded/Qt engineer who has never met the author build, flash, run, debug, release and safely modify the system. The code already shows WHAT. The document must capture WHY, HOW TO OPERATE, WHAT IS BROKEN, and WHAT IS ONLY IN THE OWNER'S HEAD.

Layout and visual style are handled by the `handover-document-style` skill. This skill decides CONTENT only.

## 2. Operating rules (follow in order)

1. Read before writing. Open the repo, `directives/`, `AGENTS.md`, `config/`, firmware sources, build specs (`build.spec`, `installer.iss`), `requirements.txt`, tests, and existing manuals. Do not write from memory or assumption.
2. Never invent. If a fact is not in the code, config, or an existing document, do not state it. Mark it `[UNKNOWN]` and add it to the Owner Questions list (section 8).
3. Tag every non-trivial claim with its evidence:
   - `[CODE: file:function]` read directly from source
   - `[CONFIG: file:key]` read from a config file
   - `[DOC: document name, section]` taken from an existing manual
   - `[OWNER]` stated by the owner in this session
   - `[INFERRED]` reasoned from code, not confirmed. Must be listed for owner confirmation.
   - `[UNKNOWN]` gap
4. Where code and comments disagree, record BOTH and flag it in the Known Issues register. Do not silently pick one.
5. Safety-relevant items come first in every section (motor control, E-stop, load limits, watchdogs, stall detection).
6. Ask the owner before any step that touches hardware, serial commands, or flashing. Documenting is read-only.
7. Never write credentials, tokens, passwords, customer data, or personal data into any document. Record WHERE they are stored and WHO controls them.
8. Short documents with one purpose each beat one giant document. Do not describe code line by line.
9. Ask follow-up questions when information is missing. Batch them (section 8). Do not stall the whole task on one gap.

## 3. Document set to produce

| # | Document | Audience | Core content |
| :---- | :---- | :---- | :---- |
| 0 | Handover Index | Everyone | Reading order, owner of each item, where every document and repo lives, status of each document |
| 1 | System Architecture Overview | Engineers | Block diagram, data flow, message formats, threading model, component list |
| 2 | Firmware Guide | Firmware engineer | MCU, peripherals, pin map, protocols, timing, safety, build and flash |
| 3 | Software (GUI) Guide | Software engineer | Modules, thread model, signals, config and persistence files, build and release |
| 4 | Hardware and Components Reference | Hardware / service | BOM, wiring, sensors, motor drive, calibration, spares, vendors |
| 5 | Operations and Runbooks | Operators / service | Power-up, test, recovery, update, failure symptoms |
| 6 | Known Issues and Risk Register | Everyone | Every open defect and risk with severity and workaround |
| 7 | Decision Log | Future maintainers | Why things are the way they are |
| 8 | Access, Ownership and Licences | Manager | Repos, CI, accounts, licences, vendors, contacts |
| 9 | In-Flight Work and Next Steps | Successor | Unfinished work, branches, blockers, recommended order |
| 10 | Handover Verification Record | Manager | Cold-read test results, sign-off |

Existing operator manuals (DAQ Operator Manual, Creep GUI User Manual) are linked from document 5, not duplicated.

## 4. Content checklist by area

### 4.1 System Architecture Overview
- One block diagram: PC/touchscreen GUI, controller (MCU), motor drive, encoder, displacement sensor, load cell, camera, power and E-stop path.
- End-to-end data flow for one sample: sensor read, MCU packet, serial transport, parse, filter, tare, record, display.
- Command flow for one motion command: GUI action, serial command, MCU parse, motor driver frame, motor.
- Every message format with an example line (telemetry, encoder, fault messages, every command with range and units).
- Thread and process model: which object runs on which thread, how threads communicate, which rules apply (Signal/Slot only, copy payloads, no UI from workers).
- Units and conversions in one table (N, kg to N, mm, pulses to mm, mm/s to RPM, samples per hour).
- Operating modes supported by this repo vs other InsituMicron products (creep, tensile, DAQ), and what is shared.

### 4.2 Firmware Guide
Capture all of the following. Each row needs an evidence tag.
- MCU part number, board revision, clock tree (source, PLL, resulting SYSCLK, bus clocks), IDE/toolchain and version, HAL version, generator project file (.ioc) location.
- Peripheral map table: peripheral, role, mode (IT / DMA / polling), baud, framing, pins, interrupt priority.
- Full pin table (name, port/pin, function, pull, active level) tied to a schematic revision.
- Protocols: PC link, motor driver Modbus RTU (register map used, function codes, CRC, inter-frame gap), encoder read, load cell I2C protocol (address, command, wait time, data format and endianness), displacement sensor binary frame (request, response layout, checksum, which bytes are used).
- Main loop structure: order of tasks, polling intervals, which are time-critical, what blocks (e.g. blocking transmits and delays inside motor sends) and for how long worst case.
- Command parser: full command table, ranges, rejection behaviour, queue depth and overflow behaviour.
- Safety functions, each with: trigger, detection method (polled / interrupt), action, notification, recovery, and test evidence. Include kill switch, stall detection, software RPM clamp, watchdog (state present or absent), behaviour on host disconnect.
- Hard-coded constants that matter physically (tare offsets, limits, scale factors) with where they must match PC-side config.
- Boot sequence and known start-up artefacts (e.g. uninitialised first packets).
- Build, flash and debug procedure from a clean machine. Debug probe, reset behaviour, how to confirm firmware version on a deployed unit, and the version-numbering scheme.
- Known firmware limitations and what must change before the next hardware revision.

### 4.3 Software (GUI) Guide
- Module map: one line per file, what it owns, what it must not do.
- Composition root and wiring: what the main window connects and in what order.
- Threading: every QThread, every `threading.Thread`, every timer, with lifetime and shutdown order. State the shutdown sequence and why it is order-dependent.
- Signal catalogue: signal, payload keys, emitter, receivers, rate limits.
- Data pipeline: parsing, filtering, tare and offset logic, stress/strain conversion inputs, recording loop and sampling-rate logic, CSV and Excel export, image save path.
- Persistence: every file the software reads or writes, its location in dev vs frozen install, format, who writes it, what breaks if it is missing or stale (e.g. presets, crash-recovery session, settings, machine limits).
- Configuration: every key in settings and machine config, default, owner, and whether it must match firmware.
- Safety-relevant UI behaviour: speed limits, confirmation dialogs, stop paths, what happens on disconnect, overload, stall, kill.
- Analysis engines: algorithm summary, assumptions, parameters, validation tests, known weaknesses.
- Reporting: PDF generator inputs and layout dependencies.
- Camera: SDK, version, install profile, thread model, recovery from forced termination.
- Dependencies: pinned versions, non-PyPI items, drivers, Python version.
- Build and release: PyInstaller spec, installer script, driver bundling, versioning rules, output names, code-signing status, how to produce a release from a clean machine, and how to verify the installer on a clean VM.
- Test suite: what exists, how to run it, what is NOT covered.
- Stale artefacts: placeholder files, unused modules, outdated comments and docs, with a recommendation (delete, finish, ignore).

### 4.4 Hardware and Components Reference
- Bill of materials: component, manufacturer, part number, key specs, quantity, supplier, lead time, known alternates.
- Sensors: displacement sensor and load cell with range, resolution, interface, calibration method, last calibration date and values, and where calibration data lives.
- Motor and drive: model, key parameters, drive settings changed from defaults, communication settings, encoder resolution, mechanical conversion (pulses per mm).
- Controller enclosure: front panel controls, power path, E-stop wiring (state clearly whether E-stop physically removes motor power independently of software), fuses, connectors, cable list with pinouts.
- PCB: schematic and layout file locations, tool and version, revision history, known errata, test points, assembly notes.
- Mechanical: load path, travel limits, hard stops, dead-weight arrangement, fixture list.
- Spares and consumables list with part numbers.

### 4.5 Operations and Runbooks
Each runbook = purpose, preconditions, numbered steps, expected result, failure branches.
- Cold start and shutdown. Normal test. Emergency stop and recovery. Controller disconnect and reconnect. Interrupted test and crash recovery. Sensor tare and calibration check. Firmware update. Software update and rollback. Camera fault recovery. Data retrieval and backup.
- Symptom to cause to fix table, built from real incidents the owner remembers.
- Preventive maintenance and calibration schedule.

### 4.6 Known Issues and Risk Register
Columns: ID, area (firmware / software / hardware / process), title, symptom, impact, root cause (or UNKNOWN), workaround, suggested fix, severity, class (FUNCTIONAL SAFETY / RELIABILITY / DATA QUALITY / USABILITY), evidence tag.
- Always list functional-safety items separately and first.
- Include negative knowledge: things tried and abandoned, and why.

### 4.7 Decision Log
Entry: date, decision, alternatives considered, reason, consequences, who decided. Cover at least: MCU and sensor interface choices, polling vs interrupt choices, filter choice and window, sampling-rate model, crash-recovery design, library choices, what was deliberately left out.

### 4.8 Access, Ownership and Licences
Repos and branches, issue tracker, CI, build machines, cloud/storage, licences (CAD, EDA, SDKs), vendor contacts, who holds admin rights. Record location and custodian of secrets. Never the secrets.

### 4.9 In-Flight Work and Next Steps
Branches and uncommitted work, half-built features, blockers and owners, recommended order for the first 30, 60 and 90 days, quick wins, and items that must NOT be touched without hardware access.

### 4.10 Handover Verification Record
- Cold-read test: someone not involved builds the GUI, builds and flashes firmware, and runs a test using only the documents. Log every stumble and fix the document.
- Supervised session: successor performs key tasks while owner observes.
- Sign-off table: reviewer, date, result, open actions.

## 5. Seed facts (verify every one against current source before using)

Collected from a prior reading of the creep repo. Treat as leads, not truth. Re-verify and tag properly.

| Area | Seed fact | Check |
| :---- | :---- | :---- |
| Firmware | USART1 DMA to motor drive Modbus RTU 115200 8N2; USART2 to PC 115200 8N1; USART3 to displacement sensor 256000 9-bit even; load cell on I2C at 7-bit address 0x17 | Header comment says I2C1 but runtime code uses `hi2c2`. Confirm which bus is physically wired |
| Firmware | Clock config suggests 84 MHz SYSCLK from HSI via PLL | Confirm MCU part and clock |
| Firmware | Kill switch on PB4, active low, internal pull-up, polled in main loop | No interrupt (EXTI) path. Confirm wiring to motor power |
| Firmware | Stall rule: motor commanded and encoder moves under 10 pulses in 2 s | Confirm intended thresholds |
| Firmware | Velocity clamp 1500 RPM; ACC/DEC 0 to 3000 | PC side limit comes from machine config. No automated consistency check |
| Firmware | Header and notes list `TARE_DISP` command | Parser shows no handler for it. Confirm and document |
| Firmware | Hard-coded displacement tare offset in firmware | Document the value, origin and when it must change |
| Firmware | Telemetry 20 Hz, load poll 10 Hz, displacement poll 20 Hz | Load value is updated slower than telemetry rate, so repeats occur. Document effect |
| Firmware | No independent or window watchdog | Confirm and record as risk |
| Software | Telemetry line format `LOAD:<N>,DISP:<mm>`; encoder `E:<int>`; faults `KILL`, `OVERLOAD...`, `ERR:STALL` | Confirm no other message types |
| Software | 3-sample median filter on load; boot-packet rejection within 3 s of reconnect | Document the rationale |
| Software | Recording loop on a plain thread, rate in samples per hour, direct calls into the worker from the GUI thread | Known deviation from Signal/Slot rule |
| Software | Crash recovery file `current_test_session.json` stored next to source | Location may be wrong in a frozen install |
| Software | `preset_positions.json` in user config dir; up to 10 load presets plus 1 unload; pulses to mm = pulses / 10000 * 2.0; mm/s to RPM = mm/s * 30 | Confirm mechanical lead and gearing |
| Software | Overload latch `_overload_fired` is reset inside the per-sample path | Confirm intended behaviour |
| Repo hygiene | `AGENTS.md` still describes DAQ, biaxial, NI-DAQmx and an unrelated installer name | Update or mark outdated |
| Repo hygiene | `interfaces.py`, `gui_method_builder.py`, `gui_execution.py` empty or placeholders; `test_engine.py` appears unused | Confirm and label |
| Repo hygiene | `execution/` import path mismatch for analysis and reporting modules | Confirm in frozen build |
| Build | PyInstaller onedir, Inno Setup installer, camera SDK and COM driver not bundled in installer per user manual | Reconcile with `installer.iss` and `drivers/` |

Previously tracked open items to carry into the register unless proven fixed:
- Functional safety: polled kill switch; E-stop wiring architecture unanswered; no watchdog; firmware clamp vs `machine_config.json` drift.
- Reliability: Qt dialogs created with parent and never released (multi-day growth); per-row `fsync` cost and disk wear at high rates; crash recovery does not restart the camera stream, leaving image path columns pointing at files never written; import path mismatch.

## 6. Writing rules for content

- State units everywhere. State ranges and defaults.
- Prefer tables for parameters and message formats, numbered steps for procedures, short prose for rationale.
- Explain each technical term once on first use (e.g. DMA, EXTI, Modbus RTU CRC, median filter) in one plain sentence.
- Every procedure must be executable by someone who has not seen the machine. Name the exact UI label or command.
- Mark each document with version, date, author, reviewer, status.
- No marketing language. No unexplained abbreviations. No em dashes.

## 7. Definition of done

- Every section in 4.1 to 4.10 exists or has an explicit "Not applicable, because ..." line.
- Zero untagged claims. All `[INFERRED]` and `[UNKNOWN]` items are in the Owner Questions list.
- Every Known Issue has severity, class and workaround or "none".
- Build-from-clean-machine steps for GUI and firmware have been run or are explicitly marked "not yet verified".
- No credentials or personal data present.
- Cross-references resolve (section numbers and file names).

## 8. Owner Questions (ask these first, batch the rest)

1. Who receives the handover and what is their firmware / Qt / hardware experience?
2. Which products are in scope: creep only, or also tensile, DAQ, kiosk, PCB designs?
3. Does the E-stop physically cut motor power independently of the MCU? Provide wiring or schematic page.
4. Exact MCU part, board revision, toolchain version, and where the .ioc and schematics live.
5. Which I2C bus carries the load cell in the deployed hardware?
6. Is `TARE_DISP` intended to exist? What sets the firmware displacement tare offset?
7. Where is the authoritative copy of the repo, and which branch is release?
8. Which calibration values and dates apply to units already in the field?
9. Which incidents (field failures, past bugs) should seed the troubleshooting table?
10. Where must documents be stored, and is there a company template or review process?
11. What may NOT be shared outside the company (check contract and IP clauses)?
