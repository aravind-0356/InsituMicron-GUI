# settings.py
"""
Persistent settings management for Insitu GUI.
Stores user preferences in a JSON file in the application directory.
"""

import json
import os
from logging_config import get_app_dir, get_logger

logger = get_logger(__name__)

SETTINGS_FILE = os.path.join(get_app_dir(), "settings.json")

# Default settings - used when no settings file exists or for new keys
DEFAULT_SETTINGS = {
    "sampling_rate": 4,
    "break_threshold_n": 1000.0,
    "last_output_folder": "",
    "last_sample_id": "Default",
    "save_images": True,
    "serial_baud_rate": 115200,
    "window_maximized": True
}


def load_settings():
    """
    Load settings from JSON file.
    
    Returns merged settings (saved + defaults for any missing keys).
    This allows new settings to be added in updates without breaking existing installs.
    """
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                # Merge with defaults (saved values override defaults)
                merged = {**DEFAULT_SETTINGS, **saved}
                logger.debug("Settings loaded from %s", SETTINGS_FILE)
                return merged
    except Exception as e:
        logger.warning("Failed to load settings: %s. Using defaults.", e)
    
    return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    """
    Save settings to JSON file.
    
    Only saves keys that differ from defaults to keep the file clean.
    """
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2)
        logger.debug("Settings saved to %s", SETTINGS_FILE)
        return True
    except Exception as e:
        logger.error("Failed to save settings: %s", e)
        return False


def get_setting(key, default=None):
    """Get a single setting value."""
    settings = load_settings()
    return settings.get(key, default)


def set_setting(key, value):
    """Set a single setting value and save."""
    settings = load_settings()
    settings[key] = value
    return save_settings(settings)
