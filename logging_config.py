# logging_config.py
"""
Centralized logging configuration for Insitu GUI.
Provides rotating file logging with console output.
"""

import logging
from logging.handlers import RotatingFileHandler
import os
import sys


def get_app_dir():
    """
    Get application directory (where exe is located).
    Works for both development and PyInstaller frozen executables.
    """
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return os.path.dirname(sys.executable)
    # Running as script
    return os.path.dirname(os.path.abspath(__file__))


def get_resource_dir():
    """
    Get resource directory (where bundled data files are located).
    For PyInstaller, data files are in _internal folder.
    For development, same as app directory.
    """
    if getattr(sys, 'frozen', False):
        # Running as compiled executable - data in _internal
        return os.path.join(os.path.dirname(sys.executable), '_internal')
    # Running as script
    return os.path.dirname(os.path.abspath(__file__))


def setup_logging(log_level=logging.INFO):
    """
    Configure rotating file logger + console output.
    
    Log files are stored in %APPDATA%/InsituMicron GUI/logs/ for installed apps,
    or ./logs/ for development.
    Rotation: 5MB per file, keep 5 backup files (25MB max total).
    
    Returns:
        Logger instance for the main application.
    """
    # Use APPDATA for installed apps (avoids Program Files permission issues)
    if getattr(sys, 'frozen', False):
        # Running as compiled executable - use APPDATA
        appdata = os.environ.get('APPDATA', os.path.expanduser('~'))
        log_dir = os.path.join(appdata, 'InsituMicron GUI', 'logs')
    else:
        # Running as script - use app directory
        log_dir = os.path.join(get_app_dir(), 'logs')
    
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, "insitu_gui.log")
    
    # Rotating file handler (5MB × 5 files = 25MB max)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)  # Log everything to file
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    
    # Console handler (for development/debugging)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)  # Only INFO+ to console
    console_handler.setFormatter(logging.Formatter(
        '%(levelname)s: %(message)s'
    ))
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove any existing handlers (prevents duplicates on reload)
    root_logger.handlers.clear()
    
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Create and return application logger
    logger = logging.getLogger("InsituGUI")
    logger.info("Logging initialized. Log file: %s", log_file)
    
    return logger


def get_logger(name):
    """
    Get a logger for a specific module.
    
    Usage:
        from logging_config import get_logger
        logger = get_logger(__name__)
        logger.info("Message")
    """
    return logging.getLogger(name)
