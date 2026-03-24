# INSITU MICRON UNIAXIAL TEST SYSTEM

## COMPREHENSIVE SOFTWARE USER MANUAL
**Software Version**: Current GUI Release  
**Model**: Uniaxial Test System

---

## Chapter 1: Hardware Setup & Driver Installation

Before launching the InsituMicron software, it is critical to ensure that all hardware components are physically connected and that the computer can properly communicate with the devices.

### 1.1 Physical Connections
Please ensure the following connections are secure before proceeding:
- **Microcontroller (STM32)**: Connect the USB module from the Component Box to your computer’s USB port. This is the system’s microcontroller responsible for actuation and data acquisition.
- **Camera**: Connect the high-speed camera to a USB 3.0 port on your computer.

### 1.2 Microcontroller (STM32) Verification
To allow the software to communicate with the controller, Windows must recognize the STM32 microcontroller as a Virtual COM Port.

1. **Open Device Manager**: Right-click the Start Button (Windows Logo) -> Select Device Manager.
2. **Verify Port**: Locate and expand `Ports (COM & LPT)`. Look for a device named `STMicroelectronics Virtual COM Port` and note the COM number (e.g., COM3, COM4).

*Troubleshooting*: If not found, download and install the STM32 Virtual COM Port Driver (STSW-STM32102) from STMicroelectronics.

### 1.3 Camera Setup & Driver Installation
Your system includes a high-performance FLIR Grasshopper3 camera.

1. **Install Spinnaker SDK**: Download and install the Spinnaker SDK from Teledyne FLIR. Choose "Application Development" during installation.
2. **Verify Camera Connection**: Use the `SpinView` application to verify the camera works and is in focus.
3. **CRITICAL**: You MUST close the SpinView application entirely before launching the InsituMicron software.

---

## Chapter 2: Software Launch & Connection

### 2.1 Launching the Application
Double-click the `InsituMicronGUI` application icon on your Desktop or Installation folder. The system will start in a "Disconnected" state.

### 2.2 Establishing the Connection
Navigate to the **Connection** tab on the left sidebar.
1. Click the **Refresh** button to scan for connected devices.
2. Select the correct **COM Port** (identified in Chapter 1) from the dropdown.
3. Click **Connect**. The status label will change from "Not Connected" (Red) to "Connected" (Green).

*If connection fails, check cables, verify the port is not used by another program, and try restarting the device.*

---

## Chapter 3: Sample Setup & Camera Configuration

### 3.1 Test Configuration
Navigate to the **Test Configuration** tab.

1. **Select Output Location**: Click the `Browse...` button to select a folder where your test data will be saved. The software will create a timestamped sub-folder for every test.
2. **Data Recording Options**: Choose to record sensor data (Time, Load, Displacement saved to `.xlsx`) and Camera Test Images `.tiff`.
3. **Sample Dimensions**: 
   - Enter a **Sample ID**
   - Select the **Sample Type** (Rectangular/Circular) and input the dimensions (Width, Thickness, Gauge Length, or Radius). These values are critical to calculate Stress/Strain parameters correctly later.

### 3.2 Image Setup & Inspection
Navigate to the **Image Setup** tab to view the live camera feed and adjust optical settings.

1. **Start Live Feed**: Click the `Start Stream` button.
2. **Adjust Quality**: Use the sliders for Exposure, Gain, Gamma, and BlackLevel on the right panel. Manual mode is recommended during actual tests to prevent brightness fluctuations.
3. **Physical Focus**: Manually rotate the camera's focus ring to ensure the sample texture is sharp for DIC.
4. **Important**: The camera stream must be Live in this tab before recording can start.

---

## Chapter 4: Test Setup (Uniaxial Mode)

This tab is the control center for your uniaxial experiment. Ensure the GUI mode selector is set to **Uniaxial**.

### 4.1 Crucial Operating Rules
1. **Velocity Logic**:
   - **Negative Value (e.g., -1.5)** = TENSION. The actuator pulls the sample.
   - **Positive/No Sign (e.g., 1.5)** = COMPRESSION. The actuator pushes against the sample.
2. **Speed Limits**: Maximum Recommended Speed is **5.0 mm/min**.

### 4.2 Actuator Controls
This section allows you to jog the single uniaxial actuator.
- **Speed (mm/min)**: Enter the desired velocity. Remember the velocity sign (+/-) determines Tension or Compression.
- **START**: Begin movement.
- **STOP**: Halt movement immediately.

### 4.3 Home Position Setup & Homing
Use these features to set a repeatable reference point for your loading axis.
- **Set Home**: Captures the current encoder position as your "Zero" or Home point.
- **Clear**: Removes the saved home position.
- **Go Home**: Enter a return speed (mm/min) and click this button to automatically retract the actuator back to the saved Home position.
- **Cancel**: Stops the automated homing process safely.

### 4.4 Preload Function
The Preload function applies a light, consistent force (e.g., 5N or 10N) to the sample to remove slack before the actual test begins.
- **Load (N)**: Enter the target force (respecting the +/- sign convention for Tension/Compression).
- **Speed (mm/min)**: Enter the approach velocity.
- **Start / Stop**: Controls the automated sequence. The actuator stops autonomously when the target load is reached.

### 4.5 Sensor Readings & Taring
Located on the right side, displaying **Load** (N) and **Displacement** (mm).
- **Tare**: Zeros out the specific sensor. **Do this before starting a test or applying preload**, ensuring the sample isn't bearing load yet.

### 4.6 Data Recording & Break Detection
- **Data Recording**: Manage Sampling Rate (between 1-10 Hz). Use `Start Rec` to log data to the chosen directory and begin the live graph plot. It is highly recommended to check `Sync Record at Start` so data collection starts exactly when motor movement begins.
- **Break Detection (Safety Stop)**: Automatically halts the machine if a sharp load drop (defined by the `Drop Threshold (N)`) is detected. Check `Auto-Stop` to enable.

### 4.7 Live Graphing
Visualizes Load vs. Time. 
- You can pan by left-clicking and dragging, or zoom by right-clicking and dragging.
- Use the **Reset** button (bottom-left) to auto-scale and fit all data perfectly back into view.

---

## Chapter 5: Test Dashboard

The Dashboard acts as your consolidated mission control during the test, saving you from navigating across multiple tabs mid-test.

### 5.1 Dashboard Layout
- **Specimen Live View (Left)**: The real-time camera feed. Quality and exposure correspond to your `Image Setup` tab settings.
- **Live Graph (Right)**: Real-time plot of the Uniaxial Load vs. Time / Displacement. 

### 5.2 Instant Action Controls
For ultimate safety and response time, the bottom of the dashboard features instantaneous override buttons:
- **Stop All Motors**: Immediately kills actuator movement. Use this in an emergency or when the sample fails.
- **Stop Data Recording**: Ends data logging safely without disrupting the live position holding of the motors.

> **Routine Workflow Summary**: 
> Connect Device -> Configure Save Path & Dimensions -> Start & Adjust Image Stream -> Tare Sensors in Test Setup -> Enter Speed Parameters -> Check Sync Record -> Start Motor -> Monitor in Dashboard -> Stop Data and Motor after specimen failure.
