# gui_test_views.py
import time
from functools import partial
import pyqtgraph as pg

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFormLayout, QMessageBox, QComboBox, QGroupBox, QSizePolicy,
    QGridLayout, QCheckBox, QStackedWidget, QListWidget, QStyle, QStyleOptionButton,
    QSpinBox, QFrame
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, Slot, QSize, QRect
from PySide6.QtGui import QDoubleValidator, QIntValidator, QFont, QPixmap, QImage, QPainter, QPen, QColor

from gui_panels import setup_plot_style

# --- Corporate Colors (centralized) ---
from constants import PRIMARY_COLOR, ACCENT_COLOR

from logging_config import get_logger
logger = get_logger(__name__)


# =========================================================
# STYLED CHECKBOX WITH TICK-MARK
# =========================================================
class StyledCheckBox(QCheckBox):
    """
    Custom checkbox that displays an elegant black tick-mark when checked.
    """
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(f"""
            StyledCheckBox {{
                font-size: 18px;
                spacing: 8px;
            }}
            StyledCheckBox::indicator {{
                width: 20px;
                height: 20px;
            }}
        """)

    def paintEvent(self, event):
        # Let the base class paint the text
        super().paintEvent(event)
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Get the indicator rectangle
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        indicator_rect = self.style().subElementRect(QStyle.SE_CheckBoxIndicator, opt, self)
        
        # Draw checkbox background
        if self.isChecked():
            painter.setPen(QPen(QColor(PRIMARY_COLOR), 2))
            painter.setBrush(QColor("#ffffff"))
        else:
            painter.setPen(QPen(QColor("#bdc3c7"), 2))
            painter.setBrush(QColor("#f7f7f7"))
        
        painter.drawRoundedRect(indicator_rect.adjusted(1, 1, -1, -1), 4, 4)
        
        # Draw tick-mark if checked
        if self.isChecked():
            pen = QPen(QColor("#2c3e50"))  # Black tick
            pen.setWidth(3)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            
            # Calculate tick points within indicator rect
            x = indicator_rect.x()
            y = indicator_rect.y()
            w = indicator_rect.width()
            h = indicator_rect.height()
            
            # Tick mark coordinates (relative to indicator)
            start_x = x + w * 0.2
            start_y = y + h * 0.5
            mid_x = x + w * 0.4
            mid_y = y + h * 0.75
            end_x = x + w * 0.8
            end_y = y + h * 0.25
            
            painter.drawLine(int(start_x), int(start_y), int(mid_x), int(mid_y))
            painter.drawLine(int(mid_x), int(mid_y), int(end_x), int(end_y))
        
        painter.end()

# =========================================================
# UNIAXIAL MOTOR CONTROL PANEL
# =========================================================
class UniaxialMotorControlPanel(QWidget):
    set_home = Signal()              # User wants to capture current encoder as home
    clear_home = Signal()            # User wants to clear saved home position
    go_home = Signal(int)            # User wants to go home at given RPM
    cancel_home = Signal()           # User wants to cancel homing
    motor_started = Signal()  # Signal when motor starts
    motor_direction_changed = Signal(int)  # 1 (Compression), -1 (Tension), 0 (Stopped)
    preload_start = Signal(float, int)  # target_load_N, velocity_rpm
    preload_stop = Signal()

    def __init__(self, serial_handler):
        super().__init__()
        self.serial = serial_handler
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        STD_BTN = "min-width: 70px; max-width: 70px;"

        # --- Actuator Controls (grouped with velocity row) ---
        grp_actuator = QGroupBox("Actuator Controls")
        act_lay = QHBoxLayout(grp_actuator)
        act_lay.setContentsMargins(8, 12, 8, 8)
        act_lay.setSpacing(8)

        act_lay.addWidget(QLabel("Speed (mm/min):"))
        self.vel = QLineEdit("0")
        self.vel.setPlaceholderText("mm/min")
        self.vel.setValidator(QDoubleValidator())
        act_lay.addWidget(self.vel)

        self.btn_start = QPushButton("START")
        self.btn_start.setStyleSheet(f"QPushButton {{ {STD_BTN} }}")
        self.btn_stop = QPushButton("STOP")
        self.btn_stop.setStyleSheet(
            f"QPushButton {{ background-color: #c0392b; color: white; font-weight: bold; {STD_BTN} }}"
            "QPushButton:hover { background-color: #e74c3c; }"
        )
        act_lay.addWidget(self.btn_start)
        act_lay.addWidget(self.btn_stop)

        layout.addWidget(grp_actuator)

        # Hidden status label — kept for programmatic updates
        self.lbl_status = QLabel("Status: IDLE")
        self.lbl_status.setVisible(False)

        # --- Home Position Setup + Homing (two side-by-side group boxes) ---
        home_row_widget = QWidget()
        home_row_layout = QHBoxLayout(home_row_widget)
        home_row_layout.setContentsMargins(0, 0, 0, 0)
        home_row_layout.setSpacing(8)

        WIDE_BTN = "min-width: 90px; max-width: 90px;"

        # Left box: Home Position Setup
        grp_setup = QGroupBox("Home Position Setup")
        setup_lay = QVBoxLayout(grp_setup)
        setup_lay.setContentsMargins(8, 12, 8, 8)
        setup_lay.setSpacing(6)

        setup_btns = QHBoxLayout()
        self.btn_set_home = QPushButton("Set Home")
        self.btn_set_home.setStyleSheet(
            f"QPushButton {{ background-color: {ACCENT_COLOR}; color: white; font-weight: bold; {WIDE_BTN} }}"
            f"QPushButton:hover {{ background-color: {PRIMARY_COLOR}; }}"
        )
        self.btn_clear_home = QPushButton("Clear")
        self.btn_clear_home.setStyleSheet(
            f"QPushButton {{ background-color: #c0392b; color: white; font-weight: bold; {STD_BTN} }}"
            "QPushButton:hover { background-color: #e74c3c; }"
        )
        setup_btns.addWidget(self.btn_set_home)
        setup_btns.addWidget(self.btn_clear_home)
        setup_btns.addStretch()
        setup_lay.addLayout(setup_btns)

        self.lbl_home_pos = QLabel("Saved: Not Set")
        self.lbl_home_pos.setStyleSheet("font-weight: bold; color: #2c3e50;")
        setup_lay.addWidget(self.lbl_home_pos)

        home_row_layout.addWidget(grp_setup)

        # Right box: Homing
        grp_homing = QGroupBox("Homing")
        homing_lay = QVBoxLayout(grp_homing)
        homing_lay.setContentsMargins(8, 12, 8, 8)
        homing_lay.setSpacing(6)

        homing_btns = QHBoxLayout()
        homing_btns.addWidget(QLabel("Speed (mm/min):"))
        self.home_speed = QLineEdit("0.375")
        self.home_speed.setPlaceholderText("mm/min")
        self.home_speed.setValidator(QDoubleValidator())
        homing_btns.addWidget(self.home_speed)
        self.btn_go_home = QPushButton("Go Home")
        self.btn_go_home.setStyleSheet(f"QPushButton {{ {WIDE_BTN} }}")
        self.btn_cancel_home = QPushButton("Cancel")
        self.btn_cancel_home.setStyleSheet(
            f"QPushButton {{ background-color: #c0392b; color: white; font-weight: bold; {STD_BTN} }}"
            "QPushButton:hover { background-color: #e74c3c; }"
        )
        homing_btns.addWidget(self.btn_go_home)
        homing_btns.addWidget(self.btn_cancel_home)
        homing_lay.addLayout(homing_btns)

        self.lbl_live_encoder = QLabel("")
        self.lbl_live_encoder.setStyleSheet("font-weight: bold; color: #7f8c8d;")
        self.lbl_live_encoder.setVisible(False)
        homing_lay.addWidget(self.lbl_live_encoder)

        home_row_layout.addWidget(grp_homing)

        layout.addWidget(home_row_widget)

        # --- Preload (grouped, single row) ---
        pre_grp = QGroupBox("Preload")
        pre_row = QHBoxLayout(pre_grp)
        pre_row.setContentsMargins(8, 12, 8, 8)
        pre_row.setSpacing(8)

        pre_row.addWidget(QLabel("Load (N):"))
        self.pre_load = QLineEdit("0")
        self.pre_load.setPlaceholderText("N")
        self.pre_load.setMaximumWidth(16777215)
        self.pre_load.setValidator(QDoubleValidator())
        pre_row.addWidget(self.pre_load)
        pre_row.addWidget(QLabel("Speed (mm/min):"))
        self.pre_vel = QLineEdit("0")
        self.pre_vel.setPlaceholderText("mm/min")
        self.pre_vel.setMaximumWidth(16777215)
        self.pre_vel.setValidator(QDoubleValidator())
        pre_row.addWidget(self.pre_vel)
        self.btn_pre_start = QPushButton("Start")
        self.btn_pre_start.setStyleSheet(
            f"QPushButton {{ background-color: {ACCENT_COLOR}; color: white; font-weight: bold; {STD_BTN} }}"
            f"QPushButton:hover {{ background-color: {PRIMARY_COLOR}; }}"
        )
        self.btn_pre_stop = QPushButton("Stop")
        self.btn_pre_stop.setStyleSheet(
            f"QPushButton {{ background-color: #c0392b; color: white; font-weight: bold; {STD_BTN} }}"
            "QPushButton:hover { background-color: #e74c3c; }"
        )
        pre_row.addWidget(self.btn_pre_start)
        pre_row.addWidget(self.btn_pre_stop)

        layout.addWidget(pre_grp)

        layout.addStretch()
        self.setLayout(layout)

        self.btn_start.clicked.connect(self.send_start)
        self.btn_stop.clicked.connect(self.send_stop)
        self.btn_set_home.clicked.connect(self.set_home_clicked)
        self.btn_clear_home.clicked.connect(self.clear_home_clicked)
        self.btn_go_home.clicked.connect(self.go_home_clicked)
        self.btn_cancel_home.clicked.connect(self.cancel_home.emit)
        self.btn_pre_start.clicked.connect(self.emit_preload)
        self.btn_pre_stop.clicked.connect(self.preload_stop.emit)

    MAX_SPEED_MM_MIN = 5.0  # Maximum allowed speed in mm/min

    @staticmethod
    def _mm_min_to_rpm(mm_min):
        """Convert mm/min to RPM: rpm = mm_min * 800 / 3."""
        return int(round(mm_min * 800.0 / 3.0))

    def send_start(self):
        if not self.serial.is_connected():
            QMessageBox.critical(self, "Connection Error", "USB is disconnected!")
            return
        try:
            mm_min = float(self.vel.text())
            if abs(mm_min) > self.MAX_SPEED_MM_MIN:
                QMessageBox.warning(self, "Speed Limit Exceeded",
                                    f"Speed exceeds the maximum limit of ±{self.MAX_SPEED_MM_MIN} mm/min.")
                return
            rpm = self._mm_min_to_rpm(mm_min)
            direction = 1 if rpm > 0 else -1 if rpm < 0 else 0
            self.motor_direction_changed.emit(direction)
            self.serial.send_cmd(f"VEL:{rpm}")
            self.serial.send_cmd("START")
            self.lbl_status.setText("Status: RUNNING")
            self.lbl_status.setStyleSheet(
                "background-color: #2ecc71; color: white; padding: 8px; border-radius: 4px; font-weight: bold;")
            logger.info("Uniaxial motor STARTED at %.3f mm/min (%d RPM)", mm_min, rpm)
            self.motor_started.emit()
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Enter a valid speed value.")

    def send_stop(self):
        if not self.serial.is_connected():
            QMessageBox.critical(self, "Connection Error", "USB is disconnected!")
            return
        self.motor_direction_changed.emit(0)
        self.serial.send_cmd("STOP")
        self.lbl_status.setText("Status: IDLE")
        self.lbl_status.setStyleSheet(
            "background-color: #bdc3c7; color: #2c3e50; padding: 8px; border-radius: 4px; font-weight: bold;")
        logger.info("Uniaxial motor STOPPED")

    def set_home_clicked(self):
        self.set_home.emit()

    def clear_home_clicked(self):
        self.clear_home.emit()

    def go_home_clicked(self):
        if not self.serial.is_connected():
            QMessageBox.critical(self, "Connection Error", "USB is disconnected!")
            return
        try:
            mm_min = float(self.home_speed.text())
            if abs(mm_min) > self.MAX_SPEED_MM_MIN:
                QMessageBox.warning(self, "Speed Limit Exceeded",
                                    f"Speed exceeds the maximum limit of ±{self.MAX_SPEED_MM_MIN} mm/min.")
                return
            rpm = self._mm_min_to_rpm(mm_min)
            if rpm == 0:
                QMessageBox.warning(self, "Input Error", "Speed too low — results in 0 RPM.")
                return
            self.go_home.emit(rpm)
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Enter a valid speed value.")

    @staticmethod
    def _pulses_to_mm(pulses):
        """Convert encoder pulses to mm: (pulses/10000) * (3/800)."""
        return (pulses / 10000.0) * (3.0 / 800.0)

    def update_home_label(self, pos):
        """Update the saved home position display."""
        if pos is None:
            self.lbl_home_pos.setText("Saved: Not Set")
        else:
            mm = self._pulses_to_mm(pos)
            self.lbl_home_pos.setText(f"Saved: {mm:.4f} mm ({pos:,} pulses)")

    def emit_preload(self):
        if not self.serial.is_connected():
            QMessageBox.critical(self, "Connection Error", "USB is disconnected!")
            return
        try:
            target = float(self.pre_load.text())
            mm_min = float(self.pre_vel.text())
            if abs(mm_min) > self.MAX_SPEED_MM_MIN:
                QMessageBox.warning(self, "Speed Limit Exceeded",
                                    f"Speed exceeds the maximum limit of ±{self.MAX_SPEED_MM_MIN} mm/min.")
                return
            rpm = self._mm_min_to_rpm(mm_min)
            logger.info("Uniaxial PRELOAD started - Target: %.1f N, Speed: %.3f mm/min (%d RPM)", target, mm_min, rpm)
            self.preload_start.emit(target, rpm)
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Please enter valid numeric values for Load and Speed.")


# =========================================================
# BIAXIAL MOTOR CONTROL PANEL
# =========================================================
class BiaxialMotorControlPanel(QWidget):
    preload_start = Signal(str, float, int)
    preload_stop = Signal()
    motor_started = Signal()  # Signal when any motor starts

    def __init__(self, serial_handler):
        super().__init__()
        self.serial = serial_handler
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(8)

        grp_ind = QGroupBox("Individual Actuator Controls")
        grid_ind = QGridLayout(grp_ind)
        grid_ind.setContentsMargins(4, 8, 4, 8)
        grid_ind.setSpacing(10)

        self.motors = {}
        for i in range(1, 5):
            m_widget = QWidget()
            m_lay = QHBoxLayout(m_widget)
            m_lay.setContentsMargins(0, 0, 0, 0)
            m_lay.setSpacing(8)

            lbl = QLabel(f"Motor {i} (mm/min):")
            lbl.setMinimumWidth(160)

            vel = QLineEdit("0")
            vel.setPlaceholderText("mm/min")
            vel.setMinimumWidth(60)
            vel.setValidator(QDoubleValidator())

            btn_s = QPushButton("Start")
            btn_s.setStyleSheet(
                f"QPushButton {{ background-color: {PRIMARY_COLOR}; color: white; font-weight: bold; }}"
                f"QPushButton:hover {{ background-color: {ACCENT_COLOR}; }}"
            )

            btn_x = QPushButton("Stop")
            btn_x.setStyleSheet(
                "QPushButton { background-color: #c0392b; color: white; font-weight: bold; }"
                "QPushButton:hover { background-color: #e74c3c; }"
            )

            m_lay.addWidget(lbl)
            m_lay.addWidget(vel)
            m_lay.addWidget(btn_s)
            m_lay.addWidget(btn_x)

            row = (i - 1) // 2
            col = (i - 1) % 2
            grid_ind.addWidget(m_widget, row, col)

            self.motors[i] = (vel, btn_s, btn_x)
            btn_s.clicked.connect(partial(self.start_m, i))
            btn_x.clicked.connect(partial(self.stop_m, i))

        layout.addWidget(grp_ind)

        grp_axial = QGroupBox("Axial/Global Actuator Controls")
        lay_axial = QVBoxLayout(grp_axial)
        lay_axial.setContentsMargins(8, 8, 8, 8)
        lay_axial.setSpacing(10)

        ax_inps = QHBoxLayout()
        self.vel_x = QLineEdit("0")
        self.vel_x.setValidator(QDoubleValidator())
        self.vel_y = QLineEdit("0")
        self.vel_y.setValidator(QDoubleValidator())
        for inp in [self.vel_x, self.vel_y]:
            inp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            inp.setPlaceholderText("mm/min")

        ax_inps.addWidget(QLabel("X-axis Motor (mm/min):"))
        ax_inps.addWidget(self.vel_x)
        ax_inps.addSpacing(10)
        ax_inps.addWidget(QLabel("Y-axis Motor (mm/min):"))
        ax_inps.addWidget(self.vel_y)
        lay_axial.addLayout(ax_inps)

        # --- Axial Control Buttons (FIXED: Natural sizing) ---
        ax_btns = QHBoxLayout()
        btn_start_x = QPushButton("Start X")
        btn_stop_x = QPushButton("Stop X")
        btn_start_y = QPushButton("Start Y")
        btn_stop_y = QPushButton("Stop Y")
        btn_uni_start = QPushButton("Start All")
        btn_uni_stop = QPushButton("Stop All")

        blue_btn_style = f"QPushButton {{ background-color: {PRIMARY_COLOR}; color: white; font-weight: bold; }} QPushButton:hover {{ background-color: {ACCENT_COLOR}; }}"
        red_btn_style = "QPushButton { background-color: #c0392b; color: white; font-weight: bold; } QPushButton:hover { background-color: #e74c3c; }"

        for b in [btn_start_x, btn_start_y, btn_uni_start]:
            b.setStyleSheet(blue_btn_style)
            b.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        for b in [btn_stop_x, btn_stop_y, btn_uni_stop]:
            b.setStyleSheet(red_btn_style)
            b.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        ax_btns.addWidget(btn_start_x)
        ax_btns.addWidget(btn_stop_x)
        ax_btns.addWidget(btn_start_y)
        ax_btns.addWidget(btn_stop_y)
        ax_btns.addWidget(btn_uni_start)
        ax_btns.addWidget(btn_uni_stop)
        lay_axial.addLayout(ax_btns)

        layout.addWidget(grp_axial)

        pre_grp = QGroupBox("PRELOAD")
        pre_lay = QHBoxLayout(pre_grp)
        pre_lay.setContentsMargins(8, 8, 8, 8)
        pre_lay.setSpacing(8)

        lbl_load = QLabel("Load(N):")
        self.pre_target = QLineEdit("0")
        self.pre_target.setPlaceholderText("0")
        self.pre_target.setMinimumWidth(80)
        self.pre_target.setValidator(QDoubleValidator())

        lbl_vel = QLabel("Velocity(mm/min):")
        self.pre_vel = QLineEdit("0")
        self.pre_vel.setPlaceholderText("0")
        self.pre_vel.setMinimumWidth(80)
        self.pre_vel.setValidator(QDoubleValidator())

        pre_lay.addWidget(lbl_load)
        pre_lay.addWidget(self.pre_target)
        pre_lay.addSpacing(10)
        pre_lay.addWidget(lbl_vel)
        pre_lay.addWidget(self.pre_vel)

        btn_pre_x = QPushButton("X-axes")
        btn_pre_y = QPushButton("Y-axes")
        btn_pre_all = QPushButton("ALL")
        btn_pre_stop = QPushButton("STOP")

        for b in [btn_pre_x, btn_pre_y, btn_pre_all]:
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setStyleSheet(
                f"QPushButton {{ background-color: {ACCENT_COLOR}; color: white; font-weight: bold; }}"
                f"QPushButton:hover {{ background-color: {PRIMARY_COLOR}; }}"
            )
            pre_lay.addWidget(b)

        btn_pre_stop.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn_pre_stop.setStyleSheet(
            "QPushButton { background-color: #c0392b; color: white; font-weight: bold; }"
            "QPushButton:hover { background-color: #e74c3c; }"
        )
        pre_lay.addWidget(btn_pre_stop)

        layout.addWidget(pre_grp)
        layout.addStretch()
        self.setLayout(layout)

        btn_start_x.clicked.connect(self.start_axial_x)
        btn_start_y.clicked.connect(self.start_axial_y)
        btn_stop_x.clicked.connect(lambda: self.send("STOPX"))
        btn_stop_y.clicked.connect(lambda: self.send("STOPY"))
        btn_uni_start.clicked.connect(self.start_all_motors)
        btn_uni_stop.clicked.connect(lambda: self.send("STOP"))
        btn_pre_x.clicked.connect(lambda: self.emit_preload("X"))
        btn_pre_y.clicked.connect(lambda: self.emit_preload("Y"))
        btn_pre_all.clicked.connect(lambda: self.emit_preload("ALL"))
        btn_pre_stop.clicked.connect(self.preload_stop.emit)

    # Motor speed constants (10 mm/min = 281 RPM for axial)
    MAX_VELOCITY_MM_MIN = 10.0
    MAX_RPM = 281  # Maximum RPM for axial motors (corresponds to 10 mm/min)

    def mm_to_rpm_ind(self, mm_val):
        return int((float(mm_val) * 225) / 4)

    def mm_to_rpm_axial(self, mm_val):
        return int((float(mm_val) * 225) / 8)

    def rpm_to_mm_ind(self, rpm):
        """Convert RPM to mm/min for individual motors"""
        return (abs(rpm) * 4) / 225

    def rpm_to_mm_axial(self, rpm):
        """Convert RPM to mm/min for axial motors"""
        return (abs(rpm) * 8) / 225

    def _validate_velocity(self, vel_mm_min):
        """
        Validate velocity against max limit (10 mm/min).
        If exceeded, show popup and return False (blocked).
        Returns True if valid, False if exceeded.
        """
        if abs(vel_mm_min) > self.MAX_VELOCITY_MM_MIN:
            QMessageBox.warning(
                self,
                "Velocity Exceeded",
                f"The entered velocity exceeds the maximum speed limit.\n\n"
                f"Maximum velocity: ±{self.MAX_VELOCITY_MM_MIN:.1f} mm/min\n\n"
                f"Please reduce your velocity to {self.MAX_VELOCITY_MM_MIN:.1f} mm/min or below."
            )
            return False
        return True

    def start_m(self, i):
        try:
            val = float(self.motors[i][0].text())
            if not self._validate_velocity(val):
                return  # Block motor start
            rpm = self.mm_to_rpm_ind(val)
            self.send(f"VEL{i}:{rpm}", f"STARTM{i}")
            logger.info("Motor %d STARTED at %.1f mm/min", i, val)
        except ValueError:
            pass

    def stop_m(self, i):
        self.send(f"STOPM{i}")
        logger.info("Motor %d STOPPED", i)

    def start_axial_x(self):
        try:
            vel_mm = float(self.vel_x.text())
            if not self._validate_velocity(vel_mm):
                return  # Block motor start
            rpm = self.mm_to_rpm_axial(vel_mm)
            self.send(f"VELX:{rpm}", "STARTX")
            logger.info("X-axis motors STARTED at %.1f mm/min", vel_mm)
            self.motor_started.emit()
        except ValueError:
            pass

    def start_axial_y(self):
        try:
            vel_mm = float(self.vel_y.text())
            if not self._validate_velocity(vel_mm):
                return  # Block motor start
            rpm = self.mm_to_rpm_axial(vel_mm)
            self.send(f"VELY:{rpm}", "STARTY")
            logger.info("Y-axis motors STARTED at %.1f mm/min", vel_mm)
            self.motor_started.emit()
        except ValueError:
            pass

    def start_all_motors(self):
        if not self.serial.is_connected():
            QMessageBox.critical(self, "Connection Error", "USB is disconnected!")
            return
        try:
            vel_x = float(self.vel_x.text())
            vel_y = float(self.vel_y.text())
            
            # Validate both axes - abort if either exceeds limit
            if not self._validate_velocity(vel_x):
                return  # Block motor start
            if not self._validate_velocity(vel_y):
                return  # Block motor start
            
            rpm_x = self.mm_to_rpm_axial(vel_x)
            rpm_y = self.mm_to_rpm_axial(vel_y)
            
            self.sequence_commands = [
                (f"VELX:{rpm_x}", 10),
                (f"VELY:{rpm_y}", 10),
                ("STARTX", 10),
                ("STARTY", 10)
            ]
            self._process_command_sequence()
            logger.info("ALL motors STARTED - X: %.1f mm/min, Y: %.1f mm/min", vel_x, vel_y)
            self.motor_started.emit()
        except ValueError:
            pass

    def _process_command_sequence(self):
        if not self.sequence_commands:
            return

        cmd, delay = self.sequence_commands.pop(0)
        self.serial.send_cmd(cmd)
        if self.sequence_commands:
            QTimer.singleShot(delay, self._process_command_sequence)

    def send(self, *cmds):
        if not self.serial.is_connected():
            QMessageBox.critical(self, "Connection Error", "USB is disconnected!")
            return
        self.sequence_commands = []
        for i, c in enumerate(cmds):
            delay = 10 if i > 0 else 0
            self.sequence_commands.append((c, delay))
        self._process_command_sequence()

    def emit_preload(self, mode):
        if not self.serial.is_connected():
            QMessageBox.critical(self, "Connection Error", "USB is disconnected!")
            return

        try:
            target = float(self.pre_target.text())
            vel_mm = float(self.pre_vel.text())
            rpm_mag = abs(self.mm_to_rpm_axial(vel_mm))

            # Validate preload velocity
            if rpm_mag > self.MAX_RPM:
                max_mm_min = self.rpm_to_mm_axial(self.MAX_RPM)
                QMessageBox.warning(
                    self,
                    "Velocity Out of Range",
                    f"The entered preload velocity exceeds the maximum motor speed limit.\n\n"
                    f"Maximum motor speed: ±{self.MAX_RPM} RPM\n"
                    f"Maximum velocity: {max_mm_min:.2f} mm/min\n\n"
                    f"Operation Aborted."
                )
                return

            final_rpm = rpm_mag if target >= 0 else -rpm_mag
            logger.info("PRELOAD started - Mode: %s, Target: %.1f N, Velocity: %.1f mm/min", mode, target, vel_mm)
            self.preload_start.emit(mode, target, final_rpm)
        except ValueError as e:
            logger.error("Invalid preload parameters: %s", e)
            QMessageBox.warning(self, "Input Error", "Please enter valid numeric values for Load and Velocity.")

# =========================================================
# MOTOR CONTROL PAGE
# =========================================================
class MotorControlPage(QWidget):
    mode_changed_sig = Signal(str)

    def __init__(self, uni_panel, bi_panel):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 0)

        top = QHBoxLayout()
        top.setContentsMargins(5, 0, 5, 0)

        top.addStretch()

        title_box = QVBoxLayout()
        self.title_lbl = QLabel("Uniaxial Controls")
        self.title_lbl.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {PRIMARY_COLOR};")
        self.title_lbl.setAlignment(Qt.AlignCenter)

        self.note_lbl = QLabel("(-ve = Tension, No Sign = Compression)")
        self.note_lbl.setStyleSheet("color: #7f8c8d; font-weight: normal;")
        self.note_lbl.setAlignment(Qt.AlignCenter)

        title_box.addWidget(self.title_lbl)
        title_box.addWidget(self.note_lbl)

        top.addLayout(title_box)
        top.addStretch()
        layout.addLayout(top)

        self.stack = QStackedWidget()
        self.stack.addWidget(uni_panel)
        self.stack.addWidget(bi_panel)
        layout.addWidget(self.stack)

    def on_switch(self, text):
        self.stack.setCurrentIndex(0 if text == "Uniaxial" else 1)
        self.title_lbl.setText(f"{text} Controls")
        self.mode_changed_sig.emit(text)


# =========================================================
# SENSOR DISPLAY PANEL
# =========================================================
class SensorDisplayPanel(QWidget):
    request_start_rec = Signal()
    request_stop_rec = Signal()
    set_zero_uni_load = Signal()
    set_zero_uni_disp = Signal()
    set_zero_bi_single = Signal(int)
    set_zero_bi_all = Signal()
    sampling_rate_changed = Signal(int)
    break_detection_changed = Signal(bool, float)
    auto_record_changed = Signal(bool)  # Signal for auto-record toggle

    def __init__(self):
        super().__init__()
        self.is_recording = False
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        top = QVBoxLayout()
        title = QLabel("Sensor Readings")
        title.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {PRIMARY_COLOR};")
        title.setAlignment(Qt.AlignCenter)

        note = QLabel("(-ve = Tension, No Sign = Compression)")
        note.setStyleSheet("color: #7f8c8d; font-weight: normal;")
        note.setAlignment(Qt.AlignCenter)

        top.addWidget(title)
        top.addWidget(note)
        layout.addLayout(top)

        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        # Uniaxial View
        self.uni_view = QWidget()
        uni_lay = QVBoxLayout(self.uni_view)
        uni_lay.setContentsMargins(0, 0, 0, 0)
        uni_grp = QGroupBox("Sensor Data")
        uni_grid = QFormLayout(uni_grp)
        uni_grid.setSpacing(12)

        self.lbl_uni_load = QLabel("0 N")
        self.lbl_uni_load.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {PRIMARY_COLOR};")
        self.lbl_uni_load_zero = QLabel("(Zero: 0)")

        btn_tare_load = QPushButton("Tare")
        btn_tare_load.setMinimumWidth(80)
        btn_tare_load.clicked.connect(self.set_zero_uni_load.emit)

        l_row = QHBoxLayout()
        l_row.addWidget(self.lbl_uni_load)
        l_row.addWidget(self.lbl_uni_load_zero)
        l_row.addStretch()
        l_row.addWidget(btn_tare_load)
        uni_grid.addRow(QLabel("Load:"), l_row)

        self.lbl_uni_disp = QLabel("0.00 mm")
        self.lbl_uni_disp.setStyleSheet("font-size: 24px; font-weight: bold; color: #27ae60;")
        self.lbl_uni_disp_zero = QLabel("(Zero: 0.00)")

        btn_tare_disp = QPushButton("Tare")
        btn_tare_disp.setMinimumWidth(80)
        btn_tare_disp.clicked.connect(self.set_zero_uni_disp.emit)

        d_row = QHBoxLayout()
        d_row.addWidget(self.lbl_uni_disp)
        d_row.addWidget(self.lbl_uni_disp_zero)
        d_row.addStretch()
        d_row.addWidget(btn_tare_disp)
        uni_grid.addRow(QLabel("Disp:"), d_row)

        uni_lay.addWidget(uni_grp)

        # --- Top Row: Data Sampling Rate + Break Detection (side by side) ---
        top_row_uni = QWidget()
        top_row_uni_layout = QHBoxLayout(top_row_uni)
        top_row_uni_layout.setContentsMargins(0, 0, 0, 0)
        top_row_uni_layout.setSpacing(12)

        # Data Sampling Rate
        samp_grp_uni = QGroupBox("Data Sampling Rate")
        samp_lay_uni = QHBoxLayout(samp_grp_uni)
        samp_lay_uni.setContentsMargins(12, 12, 12, 12)
        samp_lay_uni.setSpacing(10)

        lbl_rate_uni = QLabel("Samples/sec (1-10):")
        lbl_rate_uni.setStyleSheet("color: #2c3e50; font-weight: bold;")

        self.inp_rate_uni = QLineEdit("4")
        self.inp_rate_uni.setValidator(QIntValidator(0, 100))
        self.inp_rate_uni.setMaximumWidth(60)

        samp_lay_uni.addWidget(lbl_rate_uni)
        samp_lay_uni.addWidget(self.inp_rate_uni)
        samp_lay_uni.addStretch()

        # Break Detection
        bd_grp_uni = QGroupBox("Break Detection")
        bd_lay_uni = QHBoxLayout(bd_grp_uni)
        bd_lay_uni.setContentsMargins(12, 12, 12, 12)

        bd_lay_uni.addWidget(QLabel("Drop Threshold (N):"))
        self.inp_bd_uni = QLineEdit("1000")
        self.inp_bd_uni.setMinimumWidth(70)
        self.inp_bd_uni.setValidator(QDoubleValidator())
        self.chk_bd_uni = StyledCheckBox("Auto-Stop")

        bd_lay_uni.addWidget(self.inp_bd_uni)
        bd_lay_uni.addWidget(self.chk_bd_uni)
        bd_lay_uni.addStretch()

        top_row_uni_layout.addWidget(samp_grp_uni)
        top_row_uni_layout.addWidget(bd_grp_uni)
        uni_lay.addWidget(top_row_uni)

        # --- Data Recording (below the top row) ---
        rec_grp_uni = QGroupBox("Data Recording")
        rec_lay_uni = QHBoxLayout(rec_grp_uni)
        rec_lay_uni.setContentsMargins(12, 12, 12, 12)

        self.btn_rec_uni = QPushButton("Start Rec")
        self.btn_rec_uni.setMinimumWidth(80)
        self.btn_stop_rec_uni = QPushButton("Stop Rec")
        self.btn_stop_rec_uni.setMinimumWidth(80)
        self.btn_stop_rec_uni.setEnabled(False)
        self.btn_stop_rec_uni.setStyleSheet(
            "QPushButton { background-color: #c0392b; color: white; font-weight: bold; }"
            "QPushButton:hover { background-color: #e74c3c; }"
        )

        # Auto-record toggle
        self.chk_auto_rec_uni = StyledCheckBox("Sync Record at Start")
        self.chk_auto_rec_uni.setChecked(False)
        self.chk_auto_rec_uni.toggled.connect(self._sync_auto_record)

        self.lbl_rec_status_uni = QLabel("IDLE")
        self.lbl_rec_status_uni.setStyleSheet("font-weight: bold; margin-left: 5px;")

        rec_lay_uni.addWidget(self.btn_rec_uni)
        rec_lay_uni.addWidget(self.btn_stop_rec_uni)
        rec_lay_uni.addWidget(self.chk_auto_rec_uni)
        rec_lay_uni.addStretch()
        rec_lay_uni.addWidget(self.lbl_rec_status_uni)

        uni_lay.addWidget(rec_grp_uni)

        uni_lay.addStretch()
        self.stack.addWidget(self.uni_view)

        # Biaxial View
        self.bi_view = QWidget()
        bi_lay = QVBoxLayout(self.bi_view)
        bi_lay.setContentsMargins(0, 0, 0, 0)
        bi_grp = QGroupBox("Sensor Data")

        bi_grid = QGridLayout(bi_grp)
        bi_grid.setContentsMargins(8, 8, 8, 8)
        bi_grid.setSpacing(10)

        self.bi_labels = []
        self.bi_zero_labels = []
        colors = ['#c0392b', '#27ae60', '#2980b9', '#8e44ad']

        for i in range(4):
            sensor_widget = QWidget()
            sensor_layout = QHBoxLayout(sensor_widget)
            sensor_layout.setContentsMargins(0, 0, 0, 0)
            sensor_layout.setSpacing(5)

            lbl_name = QLabel(f"Load {i + 1}:")

            val = QLabel("0 N")
            val.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {colors[i]};")
            # Removed fixed width to allow natural sizing

            z_lbl = QLabel("(Zero: 0)")
            z_lbl.setStyleSheet("color: grey;")

            btn = QPushButton("Tare")
            # Removed fixed width to prevent overlap
            btn.clicked.connect(partial(self.set_zero_bi_single.emit, i))

            sensor_layout.addWidget(lbl_name)
            sensor_layout.addWidget(val)
            sensor_layout.addWidget(z_lbl)
            sensor_layout.addWidget(btn)
            sensor_layout.addStretch()

            self.bi_labels.append(val)
            self.bi_zero_labels.append(z_lbl)

            row = 0 if i < 2 else 1
            col = i % 2
            bi_grid.addWidget(sensor_widget, row, col)

        btn_tare_all = QPushButton("Tare All")
        btn_tare_all.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn_tare_all.setStyleSheet(
            f"QPushButton {{ background-color: {PRIMARY_COLOR}; color: white; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {ACCENT_COLOR}; }}")
        btn_tare_all.clicked.connect(self.set_zero_bi_all.emit)
        bi_grid.addWidget(btn_tare_all, 2, 0, 1, 2)

        bi_lay.addWidget(bi_grp)

        bottom_row_widget = QWidget()
        bottom_row_layout = QHBoxLayout(bottom_row_widget)
        bottom_row_layout.setContentsMargins(0, 0, 0, 0)
        bottom_row_layout.setSpacing(12)

        samp_grp = QGroupBox("Data Sampling Rate")
        samp_lay = QHBoxLayout(samp_grp)
        samp_lay.setContentsMargins(12, 12, 12, 12)
        samp_lay.setSpacing(10)

        lbl_rate = QLabel("Samples/sec (1-10):")
        lbl_rate.setStyleSheet("color: #2c3e50; font-weight: bold;")

        self.inp_rate = QLineEdit("4")
        self.inp_rate.setValidator(QIntValidator(0, 100))
        self.inp_rate.setMaximumWidth(60)

        samp_lay.addWidget(lbl_rate)
        samp_lay.addWidget(self.inp_rate)
        samp_lay.addStretch()

        bd_grp_bi = QGroupBox("Break Detection")
        bd_lay_bi = QHBoxLayout(bd_grp_bi)
        bd_lay_bi.setContentsMargins(12, 12, 12, 12)

        bd_lay_bi.addWidget(QLabel("Drop Threshold (N):"))
        self.inp_bd_bi = QLineEdit("1000")
        self.inp_bd_bi.setMinimumWidth(70)
        self.inp_bd_bi.setValidator(QDoubleValidator())
        self.chk_bd_bi = StyledCheckBox("Auto-Stop")

        bd_lay_bi.addWidget(self.inp_bd_bi)
        bd_lay_bi.addWidget(self.chk_bd_bi)
        bd_lay_bi.addStretch()

        bottom_row_layout.addWidget(samp_grp)
        bottom_row_layout.addWidget(bd_grp_bi)

        bi_lay.addWidget(bottom_row_widget)

        self.inp_rate.editingFinished.connect(self._on_rate_changed_bi)
        self.inp_rate_uni.editingFinished.connect(self._on_rate_changed_uni)


        rec_grp_box = QGroupBox("Data Recording")
        rec_lay = QHBoxLayout(rec_grp_box)
        rec_lay.setContentsMargins(12, 12, 12, 12)

        self.btn_rec = QPushButton("Start Rec")
        self.btn_stop = QPushButton("Stop Rec")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet(
            "QPushButton { background-color: #c0392b; color: white; font-weight: bold; }"
            "QPushButton:hover { background-color: #e74c3c; }"
        )

        self.btn_rec.setMinimumWidth(80)
        self.btn_stop.setMinimumWidth(80)

        # Auto-record toggle (synced with Uniaxial toggle)
        self.chk_auto_rec = StyledCheckBox("Sync Record at Start")
        self.chk_auto_rec.setChecked(False)
        self.chk_auto_rec.toggled.connect(self._sync_auto_record)

        self.lbl_rec_status = QLabel("IDLE")
        self.lbl_rec_status.setStyleSheet("font-weight: bold; margin-left: 5px;")

        rec_lay.addWidget(self.btn_rec)
        rec_lay.addWidget(self.btn_stop)
        rec_lay.addWidget(self.chk_auto_rec)
        rec_lay.addStretch()  # Push status to right
        rec_lay.addWidget(self.lbl_rec_status)

        bi_lay.addWidget(rec_grp_box)

        bi_lay.addStretch()
        self.stack.addWidget(self.bi_view)

        layout.addWidget(self.stack)
        self.setLayout(layout)

        self.btn_rec.clicked.connect(self.request_start_rec.emit)
        self.btn_stop.clicked.connect(self.request_stop_rec.emit)
        self.btn_rec_uni.clicked.connect(self.request_start_rec.emit)
        self.btn_stop_rec_uni.clicked.connect(self.request_stop_rec.emit)

        self.chk_bd_uni.toggled.connect(lambda c: self.emit_bd_change(c, self.inp_bd_uni.text()))
        self.inp_bd_uni.editingFinished.connect(
            lambda: self.emit_bd_change(self.chk_bd_uni.isChecked(), self.inp_bd_uni.text()))

        self.chk_bd_bi.toggled.connect(lambda c: self.emit_bd_change(c, self.inp_bd_bi.text()))
        self.inp_bd_bi.editingFinished.connect(
            lambda: self.emit_bd_change(self.chk_bd_bi.isChecked(), self.inp_bd_bi.text()))

    def _validate_rate(self, text):
        """Validate and return sampling rate, or show warning."""
        try:
            val = int(text)
        except ValueError:
            return 4
        if val < 1:
            QMessageBox.warning(self, "Sampling Rate", "Minimum sampling rate is 1 sample/sec.")
            return 1
        if val > 10:
            QMessageBox.warning(self, "Sampling Rate", "Maximum sampling rate is 10 samples/sec.")
            return 10
        return val

    def _on_rate_changed_bi(self):
        """Biaxial input changed — validate, sync uniaxial, and emit."""
        val = self._validate_rate(self.inp_rate.text())
        self.inp_rate.blockSignals(True)
        self.inp_rate.setText(str(val))
        self.inp_rate.blockSignals(False)
        self.inp_rate_uni.blockSignals(True)
        self.inp_rate_uni.setText(str(val))
        self.inp_rate_uni.blockSignals(False)
        self.sampling_rate_changed.emit(val)

    def _on_rate_changed_uni(self):
        """Uniaxial input changed — validate, sync biaxial, and emit."""
        val = self._validate_rate(self.inp_rate_uni.text())
        self.inp_rate_uni.blockSignals(True)
        self.inp_rate_uni.setText(str(val))
        self.inp_rate_uni.blockSignals(False)
        self.inp_rate.blockSignals(True)
        self.inp_rate.setText(str(val))
        self.inp_rate.blockSignals(False)
        self.sampling_rate_changed.emit(val)

    def emit_bd_change(self, checked, threshold_text):
        try:
            val = float(threshold_text)
            self.break_detection_changed.emit(checked, val)
        except ValueError:
            pass

    def _sync_auto_record(self, checked):
        """Sync auto-record toggle state between Uniaxial and Biaxial modes and emit signal"""
        # Block signals to prevent infinite loop
        self.chk_auto_rec_uni.blockSignals(True)
        self.chk_auto_rec.blockSignals(True)
        
        self.chk_auto_rec_uni.setChecked(checked)
        self.chk_auto_rec.setChecked(checked)
        
        self.chk_auto_rec_uni.blockSignals(False)
        self.chk_auto_rec.blockSignals(False)
        
        self.auto_record_changed.emit(checked)

    def set_mode(self, mode):
        self.stack.setCurrentIndex(0 if mode == "Uniaxial" else 1)

    def set_recording_state(self, is_recording):
        self.is_recording = is_recording

        self.btn_rec_uni.setEnabled(not is_recording)
        self.btn_stop_rec_uni.setEnabled(is_recording)

        self.btn_rec.setEnabled(not is_recording)
        self.btn_stop.setEnabled(is_recording)

        status_text = "REC" if is_recording else "IDLE"
        status_style = "color: #27ae60; font-weight: bold;" if is_recording else "color: #2c2f33; font-weight: bold;"

        self.lbl_rec_status_uni.setText(status_text)
        self.lbl_rec_status_uni.setStyleSheet(status_style)

        self.lbl_rec_status.setText(status_text)
        self.lbl_rec_status.setStyleSheet(status_style)
        
        # Reset auto-record toggle when recording stops
        if not is_recording:
            self.chk_auto_rec_uni.blockSignals(True)
            self.chk_auto_rec.blockSignals(True)
            self.chk_auto_rec_uni.setChecked(False)
            self.chk_auto_rec.setChecked(False)
            self.chk_auto_rec_uni.blockSignals(False)
            self.chk_auto_rec.blockSignals(False)
            
            # Notify main window that sync record is disabled
            self.auto_record_changed.emit(False)

    def update_uni(self, load, disp):
        self.lbl_uni_load.setText(f"{load:.0f} N")
        self.lbl_uni_disp.setText(f"{disp:.3f} mm")

    def update_uni_offset(self, load_off, disp_off):
        self.lbl_uni_load_zero.setText(f"(Zero: {load_off:.0f})")
        self.lbl_uni_disp_zero.setText(f"(Zero: {disp_off:.3f})")

    def update_bi(self, loads, errors=None):
        """Update biaxial load displays. Shows ERROR in red if sensor has error."""
        if errors is None:
            errors = [False] * 4
        
        # Color palette for normal values
        colors = ['#c0392b', '#27ae60', '#2980b9', '#8e44ad']
        
        for i, val in enumerate(loads):
            if i < 4:
                if errors[i]:
                    # Sensor error - display ERROR in red
                    self.bi_labels[i].setText("ERROR")
                    self.bi_labels[i].setStyleSheet("font-size: 20px; font-weight: bold; color: #e74c3c;")
                else:
                    # Normal value
                    self.bi_labels[i].setText(f"{val:.0f} N")
                    self.bi_labels[i].setStyleSheet(f"font-size: 20px; font-weight: bold; color: {colors[i]};")

    def update_bi_offset(self, idx, val):
        if 0 <= idx < 4:
            self.bi_zero_labels[idx].setText(f"(Zero: {val:.0f})")


# =========================================================
# SAMPLE INSPECTION PANEL
# =========================================================
class SampleInspectionPanel(QWidget):
    camera_error = Signal(str)  # Emitted on camera disconnect/error
    def __init__(self):
        super().__init__()
        from gui import CameraWorker

        # --- QObject + moveToThread pattern (matches DAQWorker, DataWorker) ---
        self._cam_thread = QThread()
        self.worker = CameraWorker()
        self.worker.moveToThread(self._cam_thread)

        self.worker.image_received.connect(self.update_image)
        self.worker.error_occurred.connect(self.handle_error)
        self.worker.stats_updated.connect(self.update_stats)
        self.worker.limits_ready.connect(self.on_limits_received)

        self._cam_thread.start()

        self._shutting_down = False  # Double-shutdown guard
        self.init_ui()
        self.limits = {}
        self.last_image_update = 0.0

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(20)

        image_container = QWidget()
        image_container.setStyleSheet("background-color: transparent; border: none;")
        image_layout = QVBoxLayout(image_container)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setAlignment(Qt.AlignCenter)

        self.image_label = QLabel("Camera Feed Offline")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet(
            "color: #bdc3c7; font-size: 22px; font-weight: bold; border: 2px dashed #bdc3c7;")
        self.image_label.setMinimumSize(640, 480)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        image_layout.addWidget(self.image_label)
        layout.addWidget(image_container, stretch=3)

        controls_container = QWidget()
        controls_layout = QVBoxLayout(controls_container)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(18)

        title = QLabel("Image Setup")
        title.setStyleSheet(f"font-size: 28px; font-weight: bold; color: {PRIMARY_COLOR}; margin-bottom: 10px;")
        controls_layout.addWidget(title)

        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("Start Stream")
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.clicked.connect(self.start_camera)

        self.btn_stop = QPushButton("Stop Stream")
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.setStyleSheet(
            "QPushButton { background-color: #c0392b; color: white; font-weight: bold; }"
            "QPushButton:hover { background-color: #e74c3c; }"
        )
        self.btn_stop.clicked.connect(self.stop_camera)
        self.btn_stop.setEnabled(False)

        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        controls_layout.addLayout(btn_layout)

        from PySide6.QtWidgets import QSlider

        self.controls_group = QGroupBox("Camera Parameters")
        self.controls_group.setEnabled(False)
        form_layout = QVBoxLayout(self.controls_group)
        form_layout.setSpacing(18)
        form_layout.setContentsMargins(12, 22, 12, 12)

        self.sliders = {}
        self.labels = {}
        self.autos = {}

        def add_control(name, has_auto=True):
            row_widget = QWidget()
            h_layout = QVBoxLayout(row_widget)
            h_layout.setContentsMargins(0, 0, 0, 0)
            h_layout.setSpacing(6)

            header = QHBoxLayout()
            lbl_name = QLabel(name)
            lbl_name.setStyleSheet("font-weight: bold;")
            lbl_val = QLabel("0.0")
            lbl_val.setStyleSheet(
                "font-weight: bold; color: #2c2f33; background-color: #f7f7f7; border: 1px solid #bdc3c7; border-radius: 4px; padding: 6px; min-width: 70px;")
            lbl_val.setAlignment(Qt.AlignCenter)

            header.addWidget(lbl_name)
            header.addStretch()

            if has_auto:
                chk_auto = QCheckBox("Auto")
                chk_auto.setCursor(Qt.PointingHandCursor)
                chk_auto.setChecked(False)
                chk_auto.toggled.connect(lambda v: self.on_auto_changed(name, v))
                self.autos[name] = chk_auto
                header.addWidget(chk_auto)

            header.addWidget(lbl_val)

            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 1000)
            slider.setCursor(Qt.PointingHandCursor)
            slider.valueChanged.connect(lambda v: self.on_slider_changed(name, v))

            h_layout.addLayout(header)
            h_layout.addWidget(slider)
            form_layout.addWidget(row_widget)

            self.sliders[name] = slider
            self.labels[name] = lbl_val

        add_control("Gain")
        add_control("Exposure")
        add_control("BlackLevel", has_auto=False)
        add_control("Gamma", has_auto=False)

        controls_layout.addWidget(self.controls_group)

        controls_layout.addStretch()

        self.status_lbl = QLabel("Ready")
        self.status_lbl.setStyleSheet(
            "background-color: #e0e0e0; color: #2c2f33; padding: 10px; font-weight: bold; border-radius: 4px;")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        controls_layout.addWidget(self.status_lbl)

        layout.addWidget(controls_container, stretch=1)

    def start_camera(self):
        """Start camera stream. Non-blocking — dispatches to worker thread."""
        self._shutting_down = False
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.image_label.setText("Initializing Camera...")
        self.status_lbl.setText("Starting...")
        self.worker.request_start()

    def stop_camera(self):
        """
        Stop camera stream asynchronously. Does NOT block the main thread.
        UI cleanup happens in _on_stream_stopped() when the thread finishes work.
        """
        if self._shutting_down:
            return
        self._shutting_down = True

        # Disable both buttons immediately to prevent re-clicks
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.status_lbl.setText("Stopping...")

        self.worker.request_stop()

        # Use a timer to check when the worker has finished cleanup,
        # since the QThread event loop is still running for slot dispatch
        self._stop_check_timer = QTimer(self)
        self._stop_check_timer.setInterval(100)
        self._stop_check_timer.timeout.connect(self._check_stream_stopped)
        self._stop_check_count = 0
        self._stop_check_timer.start()

    def _check_stream_stopped(self):
        """Poll until the worker's running flag is cleared (cleanup finished)."""
        self._stop_check_count += 1
        if not self.worker.running or self._stop_check_count > 30:  # 3s max wait
            self._stop_check_timer.stop()
            self._on_stream_stopped()

    def _on_stream_stopped(self):
        """Async callback: camera stream has fully stopped."""
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.controls_group.setEnabled(False)
        self.image_label.setText("Stream Stopped")
        self.image_label.setStyleSheet(
            "color: #bdc3c7; font-size: 22px; font-weight: bold; border: 2px dashed #bdc3c7;")
        self.status_lbl.setText("Stopped")
        self.status_lbl.setStyleSheet(
            "background-color: #e0e0e0; color: #2c2f33; padding: 10px; font-weight: bold; border-radius: 4px;")
        self._shutting_down = False

    def shutdown_camera(self):
        """
        Synchronous shutdown for app exit (closeEvent).
        Blocks the main thread briefly — acceptable only at application exit.
        """
        self.worker.shutdown()
        self._cam_thread.quit()
        self._cam_thread.wait(5000)  # 5s max



    def is_live(self):
        """Check if camera stream is active."""
        return self.worker.running

    @Slot(dict)
    def on_limits_received(self, limits):
        self.limits = limits
        if not limits:
            self.status_lbl.setText("Error: No limits")
            return

        self.controls_group.setEnabled(True)
        for name, slider in self.sliders.items():
            if name in self.limits:
                slider.setEnabled(True)
        self.status_lbl.setText("Camera Active")
        self.status_lbl.setStyleSheet(
            "background-color: #2ecc71; color: white; padding: 10px; font-weight: bold; border-radius: 4px;")

    def on_slider_changed(self, name, val):
        if name not in self.limits: return
        min_val, max_val = self.limits[name]
        mapped_val = min_val + (val / 1000.0) * (max_val - min_val)
        self.labels[name].setText(f"{mapped_val:.2f}")

        is_auto = False
        if name in self.autos:
            is_auto = self.autos[name].isChecked()

        # Direct method calls — thread-safe dispatchers emit internal signals
        if name == "Gain":
            self.worker.set_gain(mapped_val, is_auto)
        elif name == "Exposure":
            self.worker.set_exposure(mapped_val, is_auto)
        elif name == "BlackLevel":
            self.worker.set_black_level(mapped_val, False)
        elif name == "Gamma":
            self.worker.set_gamma(mapped_val)

    def on_auto_changed(self, name, is_checked):
        self.sliders[name].setEnabled(not is_checked)
        self.on_slider_changed(name, self.sliders[name].value())

    @Slot(QImage)
    def update_image(self, q_img):
        current_time = time.time()
        if current_time - self.last_image_update < 0.033:
            return
        self.last_image_update = current_time

        pixmap = QPixmap.fromImage(q_img)
        if not pixmap.isNull():
            scaled_pixmap = pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)
            self.image_label.setStyleSheet("border: none;")

    @Slot(float)
    def update_stats(self, fps):
        self.status_lbl.setText(f"● LIVE | FPS: {fps:.2f}")

    @Slot(str)
    def handle_error(self, msg):
        """Handle camera errors with double-shutdown protection."""
        logger.error("Camera handle_error received: %s (shutting_down=%s)", msg, self._shutting_down)
        if self._shutting_down:
            return  # Already shutting down — don't re-enter
        self.stop_camera()
        self.camera_error.emit(msg)  # Route through debounce system
        self.status_lbl.setText("Error occurred")
        self.status_lbl.setStyleSheet(
            "background-color: #c0392b; color: white; padding: 10px; font-weight: bold; border-radius: 4px;")


# =========================================================
# TEST DASHBOARD PANEL
# =========================================================
class TestDashboardPanel(QWidget):
    stop_all_requested = Signal()
    stop_rec_requested = Signal()
    bl_graph_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.last_image_update = 0.0
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # --- Shared camera label (reparented on mode switch) ---
        self.image_label = QLabel("Camera Feed")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet(
            "color: #bdc3c7; font-size: 18px; font-weight: bold; border: 2px dashed #bdc3c7;")
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # ========== PAGE 0: Uniaxial — 2×2 Grid ==========
        uni_page = QWidget()
        uni_lay = QVBoxLayout(uni_page)
        uni_lay.setContentsMargins(0, 0, 0, 0)

        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        # Force equal 50/50 split for columns and rows
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)

        # Top-Left: Camera container with side control panel
        self.uni_cam_container = QWidget()
        ucl = QHBoxLayout(self.uni_cam_container)
        ucl.setContentsMargins(0, 0, 0, 0)
        ucl.setSpacing(0)

        # --- Side Control Panel (uses dead pillarbox space) ---
        self.side_panel = QWidget()
        self.side_panel.setFixedWidth(140)
        self.side_panel.setStyleSheet(
            "QWidget#side_panel { background-color: #f4f6f7; border: 1px solid #dce1e5; border-radius: 6px; }")
        self.side_panel.setObjectName("side_panel")
        sp_lay = QVBoxLayout(self.side_panel)
        sp_lay.setContentsMargins(8, 10, 8, 10)
        sp_lay.setSpacing(8)

        # Stop Motor button
        self.btn_stop_all = QPushButton("Stop Motor")
        self.btn_stop_all.setStyleSheet(
            "QPushButton { background-color: #c0392b; color: white; font-weight: bold;"
            " padding: 10px 4px; font-size: 12px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #e74c3c; }")
        self.btn_stop_all.setMinimumHeight(40)
        self.btn_stop_all.setCursor(Qt.PointingHandCursor)
        self.btn_stop_all.clicked.connect(self.stop_all_requested.emit)
        sp_lay.addWidget(self.btn_stop_all)

        # Stop Recording button
        self.btn_stop_rec_dash = QPushButton("Stop\nRecording")
        self.btn_stop_rec_dash.setStyleSheet(
            "QPushButton { background-color: #c0392b; color: white; font-weight: bold;"
            " padding: 10px 4px; font-size: 12px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #e74c3c; }")
        self.btn_stop_rec_dash.setMinimumHeight(40)
        self.btn_stop_rec_dash.setCursor(Qt.PointingHandCursor)
        self.btn_stop_rec_dash.clicked.connect(self.stop_rec_requested.emit)
        sp_lay.addWidget(self.btn_stop_rec_dash)

        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet("background-color: #dce1e5; max-height: 1px;")
        sp_lay.addWidget(sep1)

        # Live Load readout
        lbl_load_title = QLabel("Load")
        lbl_load_title.setStyleSheet(
            f"color: {PRIMARY_COLOR}; font-size: 11px; font-weight: bold; background: transparent;")
        lbl_load_title.setAlignment(Qt.AlignCenter)
        sp_lay.addWidget(lbl_load_title)
        self.side_load_lbl = QLabel("-- N")
        self.side_load_lbl.setStyleSheet(
            "color: #2c3e50; font-size: 16px; font-weight: bold; background: transparent;")
        self.side_load_lbl.setAlignment(Qt.AlignCenter)
        sp_lay.addWidget(self.side_load_lbl)

        # Live Displacement readout
        lbl_disp_title = QLabel("Displacement")
        lbl_disp_title.setStyleSheet(
            f"color: {PRIMARY_COLOR}; font-size: 11px; font-weight: bold; background: transparent;")
        lbl_disp_title.setAlignment(Qt.AlignCenter)
        sp_lay.addWidget(lbl_disp_title)
        self.side_disp_lbl = QLabel("-- mm")
        self.side_disp_lbl.setStyleSheet(
            "color: #2c3e50; font-size: 16px; font-weight: bold; background: transparent;")
        self.side_disp_lbl.setAlignment(Qt.AlignCenter)
        sp_lay.addWidget(self.side_disp_lbl)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("background-color: #dce1e5; max-height: 1px;")
        sp_lay.addWidget(sep2)

        # Recording duration
        lbl_rec_title = QLabel("Rec Duration")
        lbl_rec_title.setStyleSheet(
            f"color: {PRIMARY_COLOR}; font-size: 11px; font-weight: bold; background: transparent;")
        lbl_rec_title.setAlignment(Qt.AlignCenter)
        sp_lay.addWidget(lbl_rec_title)
        self.side_rec_timer_lbl = QLabel("--:--")
        self.side_rec_timer_lbl.setStyleSheet(
            "color: #95a5a6; font-size: 18px; font-weight: bold; background: transparent;")
        self.side_rec_timer_lbl.setAlignment(Qt.AlignCenter)
        sp_lay.addWidget(self.side_rec_timer_lbl)

        # Recording status indicator
        self.side_rec_status_lbl = QLabel("IDLE")
        self.side_rec_status_lbl.setStyleSheet(
            "color: #95a5a6; font-size: 12px; font-weight: bold; background: transparent;")
        self.side_rec_status_lbl.setAlignment(Qt.AlignCenter)
        sp_lay.addWidget(self.side_rec_status_lbl)

        sp_lay.addStretch()

        # Recording timer (1s interval)
        self._rec_timer = QTimer(self)
        self._rec_timer.setInterval(1000)
        self._rec_timer.timeout.connect(self._tick_rec_timer)
        self._rec_elapsed = 0

        ucl.addWidget(self.side_panel)

        # --- Camera area (right of side panel) ---
        self.uni_cam_area = QWidget()
        cam_lay = QVBoxLayout(self.uni_cam_area)
        cam_lay.setContentsMargins(4, 0, 0, 0)
        cam_lay.setSpacing(4)
        lbl1 = QLabel("Specimen Live View")
        lbl1.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {PRIMARY_COLOR};")
        lbl1.setAlignment(Qt.AlignCenter)
        cam_lay.addWidget(lbl1)
        ucl.addWidget(self.uni_cam_area, stretch=1)

        grid.addWidget(self.uni_cam_container, 0, 0)

        # Top-Right: Load vs Time
        self.plot_load_time = pg.PlotWidget()
        setup_plot_style(self.plot_load_time, "Load vs Time", "Time (s)", "Load (N)")
        grid.addWidget(self.plot_load_time, 0, 1)

        # Bottom-Left: Switchable graph (Load vs Disp / Stress vs Strain)
        self.plot_load_disp = pg.PlotWidget()
        setup_plot_style(self.plot_load_disp, "", "Displacement (mm)", "Load (N)")
        self.plot_load_disp.plotItem.setContentsMargins(0, 28, 0, 0)  # Top margin for dropdown

        # Overlay dropdown as the title — sits on top of the plot like a native title
        self.bl_graph_combo = QComboBox(self.plot_load_disp)
        self.bl_graph_combo.addItems(["Load vs Displacement", "Stress vs Strain"])
        self.bl_graph_combo.setStyleSheet(f"""
            QComboBox {{
                font-size: 16pt;
                font-weight: bold;
                color: #2c2f33;
                background: #e8edf2;
                border: 1px solid #bdc3c7;
                border-radius: 4px;
                padding: 3px 10px;
            }}
            QComboBox:hover {{
                background: #dce3eb;
                border-color: {PRIMARY_COLOR};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 30px;
                background: {PRIMARY_COLOR};
                border-top-right-radius: 3px;
                border-bottom-right-radius: 3px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 6px solid transparent;
                border-right: 6px solid transparent;
                border-top: 8px solid white;
            }}
            QComboBox QAbstractItemView {{
                font-size: 16pt;
                color: #2c2f33;
                background: white;
                selection-background-color: #e8edf2;
            }}
        """)
        self.bl_graph_combo.adjustSize()
        self.bl_graph_combo.currentTextChanged.connect(self._on_bl_graph_switch)

        # Position combo at top-center of the plot
        def _reposition_bl_combo(event=None):
            if hasattr(self, 'bl_graph_combo'):
                cw = self.bl_graph_combo.sizeHint().width()
                x = (self.plot_load_disp.width() - cw) // 2
                self.bl_graph_combo.move(max(0, x), 4)
        self.plot_load_disp._bl_reposition = _reposition_bl_combo

        orig_resize = self.plot_load_disp.resizeEvent
        def _bl_resize(event):
            if orig_resize:
                orig_resize(event)
            _reposition_bl_combo()
        self.plot_load_disp.resizeEvent = _bl_resize
        _reposition_bl_combo()

        grid.addWidget(self.plot_load_disp, 1, 0)

        # Bottom-Right: Displacement vs Time
        self.plot_disp_time = pg.PlotWidget()
        setup_plot_style(self.plot_disp_time, "Displacement vs Time", "Time (s)", "Displacement (mm)")
        grid.addWidget(self.plot_disp_time, 1, 1)

        self.plot_widget = self.plot_load_time  # Backward compat
        uni_lay.addWidget(grid_widget)

        # ========== PAGE 1: Biaxial — Camera + Graph Split ==========
        bi_page = QWidget()
        bi_lay = QHBoxLayout(bi_page)
        bi_lay.setContentsMargins(0, 0, 0, 0)
        bi_lay.setSpacing(10)

        # Left: Camera container
        self.bi_cam_container = QWidget()
        bcl = QVBoxLayout(self.bi_cam_container)
        bcl.setContentsMargins(0, 0, 0, 0)
        lbl2 = QLabel("Specimen Live View")
        lbl2.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {PRIMARY_COLOR};")
        lbl2.setAlignment(Qt.AlignCenter)
        bcl.addWidget(lbl2)
        bi_lay.addWidget(self.bi_cam_container, stretch=1)

        # Right: Biaxial Loads vs Time
        bi_right = QWidget()
        brl = QVBoxLayout(bi_right)
        brl.setContentsMargins(0, 0, 0, 0)
        lbl3 = QLabel("Biaxial Loads vs Time")
        lbl3.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {PRIMARY_COLOR};")
        lbl3.setAlignment(Qt.AlignCenter)
        brl.addWidget(lbl3)
        self.plot_bi_loads = pg.PlotWidget()
        setup_plot_style(self.plot_bi_loads, "Biaxial Loads", "Time (s)", "Load (N)")
        brl.addWidget(self.plot_bi_loads)
        bi_lay.addWidget(bi_right, stretch=1)

        # ========== Stack ==========
        self.dash_stack = QStackedWidget()
        self.dash_stack.addWidget(uni_page)   # 0: Uniaxial
        self.dash_stack.addWidget(bi_page)    # 1: Biaxial
        layout.addWidget(self.dash_stack, stretch=1)

        # --- Biaxial stop buttons (bottom bar for biaxial page) ---
        self.bi_btn_bar = QWidget()
        bi_btn_lay = QHBoxLayout(self.bi_btn_bar)
        bi_btn_lay.setContentsMargins(0, 4, 0, 0)
        bi_btn_lay.setSpacing(6)

        self.btn_stop_all_bi = QPushButton("Stop All Motors")
        self.btn_stop_all_bi.setStyleSheet(
            "QPushButton { background-color: #c0392b; color: white; font-weight: bold;"
            " padding: 8px 14px; font-size: 13px; }"
            "QPushButton:hover { background-color: #e74c3c; }")
        self.btn_stop_all_bi.clicked.connect(self.stop_all_requested.emit)

        self.btn_stop_rec_bi = QPushButton("Stop Recording")
        self.btn_stop_rec_bi.setStyleSheet(
            "QPushButton { background-color: #c0392b; color: white; font-weight: bold;"
            " padding: 8px 14px; font-size: 13px; }"
            "QPushButton:hover { background-color: #e74c3c; }")
        self.btn_stop_rec_bi.clicked.connect(self.stop_rec_requested.emit)

        bi_btn_lay.addWidget(self.btn_stop_all_bi)
        bi_btn_lay.addWidget(self.btn_stop_rec_bi)
        layout.addWidget(self.bi_btn_bar)

        # Default to Uniaxial
        self.set_mode("Uniaxial")

    def set_mode(self, mode):
        """Switch dashboard between Uniaxial (2x2) and Biaxial (split)."""
        if mode == "Uniaxial":
            self.dash_stack.setCurrentIndex(0)
            self.uni_cam_area.layout().addWidget(self.image_label, stretch=1)
            self.btn_stop_all.setText("Stop Motor")
            self.bi_btn_bar.hide()
        else:
            self.dash_stack.setCurrentIndex(1)
            self.bi_cam_container.layout().addWidget(self.image_label, stretch=1)
            self.bi_btn_bar.show()

    def update_side_readouts(self, load, disp):
        """Update live Load and Displacement values on the side panel."""
        self.side_load_lbl.setText(f"{load:.0f} N")
        self.side_disp_lbl.setText(f"{disp:.3f} mm")

    def start_rec_timer(self):
        """Start recording duration timer."""
        self._rec_elapsed = 0
        self.side_rec_timer_lbl.setText("00:00")
        self.side_rec_timer_lbl.setStyleSheet(
            "color: #27ae60; font-size: 18px; font-weight: bold; background: transparent;")
        self.side_rec_status_lbl.setText("REC")
        self.side_rec_status_lbl.setStyleSheet(
            "color: #27ae60; font-size: 12px; font-weight: bold; background: transparent;")
        self._rec_timer.start()

    def stop_rec_timer(self):
        """Stop recording duration timer."""
        self._rec_timer.stop()
        self.side_rec_timer_lbl.setStyleSheet(
            "color: #95a5a6; font-size: 18px; font-weight: bold; background: transparent;")
        self.side_rec_status_lbl.setText("IDLE")
        self.side_rec_status_lbl.setStyleSheet(
            "color: #95a5a6; font-size: 12px; font-weight: bold; background: transparent;")

    def _tick_rec_timer(self):
        """Increment recording duration counter every second."""
        self._rec_elapsed += 1
        mins = self._rec_elapsed // 60
        secs = self._rec_elapsed % 60
        self.side_rec_timer_lbl.setText(f"{mins:02d}:{secs:02d}")

    @Slot(QImage)
    def update_image(self, q_img):
        current_time = time.time()
        if current_time - self.last_image_update < 0.033:
            return
        self.last_image_update = current_time

        pixmap = QPixmap.fromImage(q_img)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation
            )
            self.image_label.setPixmap(scaled)
            self.image_label.setStyleSheet("border: none;")

    def update_dashboard_title(self, mode):
        self.set_mode(mode)

    def _on_bl_graph_switch(self, text):
        """Switch bottom-left graph between Load vs Disp and Stress vs Strain."""
        if text == "Stress vs Strain":
            self.plot_load_disp.setLabel('left', 'Stress (N/mm²)', color='#2c2f33', size='16pt')
            self.plot_load_disp.setLabel('bottom', 'Strain (mm/mm)', color='#2c2f33', size='16pt')
        else:
            self.plot_load_disp.setLabel('left', 'Load (N)', color='#2c2f33', size='16pt')
            self.plot_load_disp.setLabel('bottom', 'Displacement (mm)', color='#2c2f33', size='16pt')
        self.bl_graph_changed.emit(text)