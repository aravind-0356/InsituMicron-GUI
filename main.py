# main.py
"""
InsituMicron GUI - Main Entry Point
Copyright (c) 2025 Insitu Instruments. All rights reserved.
"""

import sys
import os

# --- Version Information ---
__version__ = "2.1.1"
__app_name__ = "InsituMicron GUI"

# =========================================================
# DPI-AWARE SCALING
# =========================================================
# Strategy: Enable Qt's auto-scaling, but apply a counter-scale factor
# to compensate for Windows recommended scaling.
#
# Your laptop at 150% scaling: Qt would scale by 1.5x (too big!)
# Counter-scale by 0.67: 0.67 × 1.5 = 1.0 (neutral)
#
# Other monitor at 200%: 0.67 × 2.0 = 1.33 (properly scaled up)
# Other monitor at 100%: 0.67 × 1.0 = 0.67 (properly scaled down)
# =========================================================

# Enable Qt's automatic screen scale factor
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

# Counter-scale to neutralize 150% baseline (1.0 / 1.5 = 0.6667)
# This ensures your original 18px design looks the same at 150%
os.environ["QT_SCALE_FACTOR"] = "0.6667"

# Initialize logging BEFORE other imports
from logging_config import setup_logging, get_logger
logger = setup_logging()

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from gui import MainWindow

# --- Corporate Colors (centralized) ---
from constants import PRIMARY_COLOR, ACCENT_COLOR

# --- Global Stylesheet (original 18px-based sizes) ---
GLOBAL_STYLESHEET = f"""
QMainWindow {{
    background-color: #f8f9fa; 
}}
QWidget {{
    background-color: #ffffff; 
    color: #2c3e50; 
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 18px;
}}
QLineEdit {{
    background-color: #f4f6f7; 
    border: 1px solid #bdc3c7; 
    padding: 10px;
    border-radius: 6px;
    color: #2c3e50;
    selection-background-color: {PRIMARY_COLOR};
    font-size: 18px;
}}
QLineEdit:focus {{
    border: 1px solid {PRIMARY_COLOR};
}}
QPushButton {{
    background-color: {PRIMARY_COLOR}; 
    border: none;
    padding: 12px 24px;
    border-radius: 6px;
    color: white;
    font-weight: bold;
    font-size: 18px;
}}
QPushButton:pressed {{
    background-color: #004a66; 
    padding-top: 14px;        
    padding-left: 26px;       
    padding-bottom: 10px;
    padding-right: 22px;
}}
QPushButton:hover {{
    background-color: {ACCENT_COLOR};
}}
QPushButton:disabled {{
    background-color: #dfe6e9; 
    color: #b2bec3;
}}

/* --- Modern QComboBox with Standard Arrow --- */
QComboBox {{
    background-color: #ffffff;
    border: 1px solid #bdc3c7;
    border-radius: 6px;
    padding: 10px 35px 10px 12px;
    min-width: 8em;
    color: #2c3e50;
    selection-background-color: {PRIMARY_COLOR};
    font-size: 18px;
}}
QComboBox:hover {{
    border: 1px solid {PRIMARY_COLOR};
}}
QComboBox:on {{
    padding-top: 12px;
    padding-left: 14px;
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 30px;
    border-left-width: 1px;
    border-left-color: #bdc3c7;
    border-left-style: solid;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    background-color: #ecf0f1;
}}
QComboBox::drop-down:hover {{
    background-color: #d5dbdb;
}}
/* CSS TRIANGLE ARROW - Reliable rendering */
QComboBox::down-arrow {{
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 5px solid #2c3e50;
    margin-right: 5px;
}}
QComboBox::down-arrow:on {{
    border-top: 5px solid {PRIMARY_COLOR};
}}
QComboBox QAbstractItemView {{
    border: 1px solid {PRIMARY_COLOR};
    selection-background-color: {PRIMARY_COLOR};
    selection-color: white;
    outline: 0px;
    font-size: 18px;
    padding: 6px;
}}

QGroupBox {{
    border: 1px solid #ecf0f1;
    border-radius: 8px;
    margin-top: 1.4em;
    font-weight: bold;
    color: {PRIMARY_COLOR}; 
    background-color: white;
    font-size: 20px;
    padding-top: 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left; 
    padding: 0 8px;
    background-color: white;
}}

QLabel {{
    font-size: 18px;
}}

QCheckBox {{
    font-size: 18px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid #bdc3c7;
    border-radius: 4px;
    background: #ffffff;
}}

QCheckBox::indicator:hover {{
    border: 2px solid {PRIMARY_COLOR};
}}

QCheckBox::indicator:checked {{
    border: 2px solid {PRIMARY_COLOR};
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.4, fx:0.5, fy:0.5, stop:0 {PRIMARY_COLOR}, stop:0.3 {PRIMARY_COLOR}, stop:0.31 white, stop:1 white);
}}

QSlider::groove:horizontal {{
    border: 1px solid #bdc3c7;
    height: 8px;
    background: #e0e0e0;
    margin: 2px 0;
    border-radius: 4px;
}}

QSlider::handle:horizontal {{
    background: {PRIMARY_COLOR};
    border: 1px solid {PRIMARY_COLOR};
    width: 18px;
    height: 18px;
    margin: -5px 0;
    border-radius: 9px;
}}

QSlider::handle:horizontal:hover {{
    background: {ACCENT_COLOR};
    border: 1px solid {ACCENT_COLOR};
}}
"""

if __name__ == "__main__":
    logger.info("Starting %s v%s", __app_name__, __version__)
    
    app = QApplication(sys.argv)
    app.setStyleSheet(GLOBAL_STYLESHEET)

    # Set Default Font
    font = app.font()
    font.setFamily("Segoe UI")
    font.setPointSize(12)
    app.setFont(font)

    window = MainWindow()
    window.setWindowTitle(f"{__app_name__} v{__version__}")
    window.showMaximized()
    
    logger.info("Application started successfully")
    exit_code = app.exec()
    
    logger.info("Application exiting with code %d", exit_code)
    sys.exit(exit_code)
