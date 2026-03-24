# gui_panels.py
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFormLayout, QMessageBox, QComboBox, QFileDialog, QSizePolicy, QGroupBox
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QDoubleValidator

# --- Corporate Colors (centralized) ---
from constants import PRIMARY_COLOR, ACCENT_COLOR

from logging_config import get_logger
logger = get_logger(__name__)


# --- Helper for graph styling ---
def setup_plot_style(plot, title, xlabel, ylabel):
    """
    Set up professional plot styling with larger, bolder fonts and thicker lines.
    """
    plot.setBackground('w')
    plot.setTitle(title, color='#2c2f33', size='18pt')
    plot.setLabel('left', ylabel, color='#2c2f33', size='16pt')
    plot.setLabel('bottom', xlabel, color='#2c2f33', size='16pt')
    plot.showGrid(x=True, y=True, alpha=0.3)

    # Thicker, more visible axes
    pen = pg.mkPen(color='#2c2f33', width=2)
    plot.getAxis('left').setPen(pen)
    plot.getAxis('bottom').setPen(pen)
    plot.getAxis('left').setTextPen(pen)
    plot.getAxis('bottom').setTextPen(pen)

    # Increase tick font size for better readability
    font = pg.QtGui.QFont()
    font.setPixelSize(14)
    plot.getAxis('left').setStyle(tickFont=font)
    plot.getAxis('bottom').setStyle(tickFont=font)

    # Hide the default auto-range button ("A") and add custom "Reset" button
    plot_item = plot.getPlotItem()
    plot_item.hideButtons()  # Hide the default "A" button
    
    # Create custom reset button
    from PySide6.QtWidgets import QPushButton
    reset_btn = QPushButton("Reset", plot)
    reset_btn.setStyleSheet("""
        QPushButton {
            background-color: rgba(255, 255, 255, 0.9);
            border: 1px solid #bdc3c7;
            border-radius: 3px;
            padding: 3px 8px;
            font-size: 11px;
            font-weight: bold;
            color: #2c3e50;
        }
        QPushButton:hover {
            background-color: #ecf0f1;
            border-color: #005b7f;
        }
    """)
    reset_btn.setFixedSize(50, 22)
    reset_btn.move(5, plot.height() - 30)  # Position bottom-left
    reset_btn.clicked.connect(lambda: plot.getPlotItem().getViewBox().enableAutoRange(x=True, y=True))
    
    # Store reference and set up resize handler
    plot._custom_reset_btn = reset_btn
    
    # Reposition button on resize
    original_resize = plot.resizeEvent
    def new_resize(event):
        if original_resize:
            original_resize(event)
        if hasattr(plot, '_custom_reset_btn'):
            plot._custom_reset_btn.move(5, plot.height() - 30)
    plot.resizeEvent = new_resize


# =========================================================
# CONNECTION PANEL
# =========================================================
class ConnectionPanel(QWidget):
    def __init__(self, serial_handler):
        super().__init__()
        self.serial = serial_handler
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        title = QLabel("Serial Port Connection")
        title.setStyleSheet(f"font-size: 28px; font-weight: bold; color: {PRIMARY_COLOR}; margin-bottom: 10px;")
        layout.addWidget(title, alignment=Qt.AlignCenter)

        form_layout = QFormLayout()
        form_layout.setSpacing(20)
        self.port_combo = QComboBox()
        lbl_port = QLabel("Port:")
        lbl_port.setStyleSheet("font-weight: bold;")
        form_layout.addRow(lbl_port, self.port_combo)
        layout.addLayout(form_layout)

        layout.addSpacing(25)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)
        self.refresh_btn = QPushButton("Refresh")
        self.connect_btn = QPushButton("Connect")
        self.disconnect_btn = QPushButton("Disconnect")

        button_layout.addWidget(self.refresh_btn)
        button_layout.addWidget(self.connect_btn)
        button_layout.addWidget(self.disconnect_btn)
        layout.addLayout(button_layout)

        layout.addSpacing(25)

        self.status_label = QLabel("Disconnected")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("""
            background-color: #e74c3c; 
            color: white; 
            padding: 14px; 
            border-radius: 6px; 
            font-weight: bold;
        """)
        layout.addWidget(self.status_label)
        layout.addStretch()

        self.setLayout(layout)

        self.refresh_btn.clicked.connect(self.refresh_ports)
        self.connect_btn.clicked.connect(self.connect_port)
        self.disconnect_btn.clicked.connect(self.disconnect_port)
        self.serial.connection_status_changed.connect(self.update_status_display)
        self.refresh_ports()
        
        # Auto-refresh timer - refreshes COM ports every 2 seconds when not connected
        from PySide6.QtCore import QTimer
        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.timeout.connect(self._auto_refresh_ports)
        self.auto_refresh_timer.start(2000)  # Every 2 seconds

    def refresh_ports(self):
        self.port_combo.clear()
        ports = self.serial.get_ports()
        if not ports:
            self.port_combo.addItem("No COM Ports Found")
            self.connect_btn.setEnabled(False)
        else:
            self.port_combo.addItems(ports)
            self.connect_btn.setEnabled(not self.serial.is_connected())

    def connect_port(self):
        port = self.port_combo.currentText()
        if port and port != "No COM Ports Found":
            success = self.serial.connect(port, baudrate=115200)
            if not success:
                QMessageBox.critical(self, "Connection Error",
                                     f"Failed to open {port}.\nCheck if the device is busy or permissions are denied.")

    def disconnect_port(self):
        self.serial.disconnect()

    def _auto_refresh_ports(self):
        """Auto-refresh COM ports when not connected."""
        if not self.serial.is_connected():
            self.refresh_ports()

    @Slot(bool, str)
    def update_status_display(self, is_connected, msg):
        self.status_label.setText("Connected" if is_connected else "Disconnected")
        color = "#2ecc71" if is_connected else "#e74c3c"
        self.status_label.setStyleSheet(
            f"background-color: {color}; color: white; padding: 14px; border-radius: 6px; font-weight: bold;")
        self.connect_btn.setEnabled(not is_connected)
        self.disconnect_btn.setEnabled(is_connected)
        self.port_combo.setEnabled(not is_connected)


# =========================================================
# SAMPLE PANEL (WITH FOLDER SELECTION AND SAVE OPTIONS)
# =========================================================
class SamplePanel(QWidget):
    sample_parameters_changed = Signal()
    output_folder_changed = Signal(str)
    save_sensor_changed = Signal(bool)
    save_images_changed = Signal(bool)

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        title = QLabel("Test Configuration")
        title.setStyleSheet(f"font-size: 28px; font-weight: bold; color: {PRIMARY_COLOR}; margin-bottom: 10px;")
        layout.addWidget(title, alignment=Qt.AlignCenter)

        # === DOWNLOAD SETTINGS GROUP ===
        download_grp = QGroupBox("Download Settings")
        download_grp.setStyleSheet(f"""
            QGroupBox {{
                font-size: 22px;
                font-weight: bold;
                color: {PRIMARY_COLOR};
                border: 1px solid #bdc3c7;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 10px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
            }}
        """)
        download_layout = QVBoxLayout(download_grp)
        download_layout.setContentsMargins(15, 20, 15, 15)
        download_layout.setSpacing(15)

        # Save Location
        folder_label = QLabel("Save Location:")
        folder_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        download_layout.addWidget(folder_label)

        folder_row = QHBoxLayout()
        self.folder_path_display = QLineEdit()
        self.folder_path_display.setReadOnly(True)
        self.folder_path_display.setPlaceholderText("No folder selected - Click Browse to select...")
        self.folder_path_display.setStyleSheet("background-color: #ecf0f1; font-style: italic;")

        self.btn_browse_folder = QPushButton("Browse...")
        self.btn_browse_folder.setMinimumWidth(120)
        self.btn_browse_folder.clicked.connect(self.browse_output_folder)

        folder_row.addWidget(self.folder_path_display)
        folder_row.addWidget(self.btn_browse_folder)
        download_layout.addLayout(folder_row)

        # Data to Record
        save_opts_label = QLabel("Data to Record:")
        save_opts_label.setStyleSheet("font-weight: bold; color: #2c3e50; margin-top: 5px;")
        download_layout.addWidget(save_opts_label)

        save_opts_row = QHBoxLayout()
        save_opts_row.setSpacing(30)

        from gui_test_views import StyledCheckBox
        self.chk_save_sensor = StyledCheckBox("Sensor Data (.xlsx)")
        self.chk_save_sensor.setChecked(True)
        self.chk_save_sensor.toggled.connect(self.save_sensor_changed.emit)

        self.chk_save_images = StyledCheckBox("Camera Test Images (.tiff)")
        self.chk_save_images.setChecked(True)
        self.chk_save_images.toggled.connect(self.save_images_changed.emit)

        save_opts_row.addWidget(self.chk_save_sensor)
        save_opts_row.addWidget(self.chk_save_images)
        save_opts_row.addStretch()
        download_layout.addLayout(save_opts_row)

        layout.addWidget(download_grp)

        # === SAMPLE DIMENSIONS GROUP ===
        sample_grp = QGroupBox("Sample Dimensions")
        sample_grp.setStyleSheet(f"""
            QGroupBox {{
                font-size: 22px;
                font-weight: bold;
                color: {PRIMARY_COLOR};
                border: 1px solid #bdc3c7;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 10px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
            }}
        """)
        sample_layout = QVBoxLayout(sample_grp)
        sample_layout.setContentsMargins(15, 20, 15, 15)

        form_layout = QFormLayout()
        form_layout.setSpacing(18)

        self.sample_id_input = QLineEdit(self.main_window._sample_id)
        self.sample_id_input.editingFinished.connect(
            lambda: self.main_window.set_sample_id(self.sample_id_input.text()))

        id_label = QLabel("Sample ID:")
        form_layout.addRow(id_label, self.sample_id_input)

        self.sample_type_combo = QComboBox()
        self.sample_type_combo.addItems(["Rectangular", "Circular", "Biaxial"])
        self.sample_type_combo.setCurrentText(self.main_window._sample_type)
        self.sample_type_combo.currentTextChanged.connect(self.update_inputs)

        type_label = QLabel("Sample Type:")
        form_layout.addRow(type_label, self.sample_type_combo)

        from PySide6.QtWidgets import QStackedWidget
        self.stack = QStackedWidget()

        # Rectangular
        rect_w = QWidget()
        rect_f = QFormLayout(rect_w)
        rect_f.setSpacing(18)
        rect_f.setContentsMargins(0, 10, 0, 0)

        self.width_inp = QLineEdit(str(self.main_window._sample_width))
        self.thick_inp = QLineEdit(str(self.main_window._sample_thickness))
        self.rect_gauge_inp = QLineEdit(str(self.main_window._sample_gauge_length))

        for inp in [self.width_inp, self.thick_inp, self.rect_gauge_inp]:
            inp.setValidator(QDoubleValidator(0, 1000, 2))
            inp.editingFinished.connect(self.push_params)

        rect_f.addRow(QLabel("Width (mm):"), self.width_inp)
        rect_f.addRow(QLabel("Thickness (mm):"), self.thick_inp)
        rect_f.addRow(QLabel("Gauge Length (mm):"), self.rect_gauge_inp)
        self.stack.addWidget(rect_w)

        # Circular
        circ_w = QWidget()
        circ_f = QFormLayout(circ_w)
        circ_f.setSpacing(18)
        circ_f.setContentsMargins(0, 10, 0, 0)

        self.rad_inp = QLineEdit(str(self.main_window._sample_radius))
        self.circ_gauge_inp = QLineEdit(str(self.main_window._sample_gauge_length))

        for inp in [self.rad_inp, self.circ_gauge_inp]:
            inp.setValidator(QDoubleValidator(0, 1000, 2))
            inp.editingFinished.connect(self.push_params)

        circ_f.addRow(QLabel("Radius (mm):"), self.rad_inp)
        circ_f.addRow(QLabel("Gauge Length (mm):"), self.circ_gauge_inp)
        self.stack.addWidget(circ_w)

        # Biaxial
        biaxial_w = QWidget()
        biaxial_f = QFormLayout(biaxial_w)
        biaxial_f.setSpacing(18)
        biaxial_f.setContentsMargins(0, 10, 0, 0)
        
        self.extra_dims_inp = QLineEdit(self.main_window._sample_extra_dims)
        self.extra_dims_inp.setPlaceholderText("Enter comments or dimensions...")
        self.extra_dims_inp.editingFinished.connect(self.push_params)
        
        biaxial_f.addRow(QLabel("Additional Sample Dimensions:"), self.extra_dims_inp)
        self.stack.addWidget(biaxial_w)

        sample_layout.addLayout(form_layout)
        sample_layout.addWidget(self.stack)

        layout.addWidget(sample_grp)
        layout.addStretch()
        self.setLayout(layout)
        self.update_inputs(self.sample_type_combo.currentText())

    def browse_output_folder(self):
        """Open folder browser dialog"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Output Folder for Test Data",
            "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )

        if folder:
            self.folder_path_display.setText(folder)
            self.folder_path_display.setStyleSheet("background-color: #d5f4e6; font-style: normal;")
            self.output_folder_changed.emit(folder)
            logger.info("Output folder selected: %s", folder)

    def update_inputs(self, text):
        self.main_window.set_sample_type(text)
        if text == "Rectangular":
            self.stack.setCurrentIndex(0)
        elif text == "Circular":
            self.stack.setCurrentIndex(1)
        else:
            self.stack.setCurrentIndex(2)
        self.push_params()

    def push_params(self):
        try:
            self.main_window.set_sample_width(float(self.width_inp.text()))
            self.main_window.set_sample_thickness(float(self.thick_inp.text()))
            self.main_window.set_sample_radius(float(self.rad_inp.text()))

            if self.stack.currentIndex() == 0:
                self.main_window.set_sample_gauge_length(float(self.rect_gauge_inp.text()))
            elif self.stack.currentIndex() == 1:
                self.main_window.set_sample_gauge_length(float(self.circ_gauge_inp.text()))
            else:
                self.main_window.set_sample_extra_dims(self.extra_dims_inp.text())

            self.sample_parameters_changed.emit()
        except ValueError:
            pass
