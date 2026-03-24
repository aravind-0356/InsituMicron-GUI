# dpi_scaling.py
"""
DPI-Aware Scaling Module

This module provides functions for creating DPI-aware GUI elements.
It calculates a scale factor based on the screen's device pixel ratio
and provides helper functions for scaling pixel values.

IMPORTANT: All base sizes are defined at 100% Windows scaling.
Qt's High-DPI system multiplies by DPR automatically.

Reference: Your laptop at 150% scaling = 1.5 DPR
Original design sizes (at 150%) divided by 1.5 = base sizes at 100%

Usage:
    from dpi_scaling import scaled, font_base, font_title
"""

from PySide6.QtWidgets import QApplication

# Your laptop baseline: 1920x1080 @ 150% = 1.5 DPR
REFERENCE_DPR = 1.5

# Module-level cached scale factor
_cached_scale_factor = None


def get_scale_factor() -> float:
    """
    Get scale factor relative to 150% Windows scaling baseline.
    Returns 1.0 on your laptop (150%), 1.33 at 200%, 0.67 at 100%.
    """
    global _cached_scale_factor
    
    if _cached_scale_factor is not None:
        return _cached_scale_factor
    
    app = QApplication.instance()
    if app is None:
        return 1.0
    
    screen = app.primaryScreen()
    if screen is None:
        return 1.0
    
    device_pixel_ratio = screen.devicePixelRatio()
    _cached_scale_factor = device_pixel_ratio / REFERENCE_DPR
    
    return _cached_scale_factor


def scaled(value: int) -> int:
    """
    Scale a BASE pixel value (defined at 100% scaling).
    
    Example: If you want 18px on YOUR laptop (150%):
      - True base at 100% = 18/1.5 = 12px
      - Call: scaled(12)
      - Qt multiplies by DPR: 12 * 1.5 = 18px on your laptop
      
    On other monitors:
      - 200% scaling: scaled(12) = 16px, Qt: 16 * 2.0 = 32px
      - 100% scaling: scaled(12) = 8px, Qt: 8 * 1.0 = 8px
    """
    return int(round(value * get_scale_factor()))


def scaled_stylesheet(base_px: int) -> str:
    """
    Return a scaled pixel value as a string for use in stylesheets.
    """
    return f"{scaled(base_px)}px"


# =========================================================
# Pre-defined scaled font sizes for convenience
# All values are BASE sizes at 100% scaling
# Original 150% values: 18, 20, 22, 28 → divided by 1.5
# =========================================================

def font_base() -> int:
    """Standard text - 12px base (appears as 18px at 150%)"""
    return scaled(12)


def font_large() -> int:
    """Large text - 13px base (appears as ~20px at 150%)"""
    return scaled(13)


def font_title() -> int:
    """Title text - 15px base (appears as ~22px at 150%)"""
    return scaled(15)


def font_heading() -> int:
    """Heading/page title - 19px base (appears as ~28px at 150%)"""
    return scaled(19)


# =========================================================
# Pre-defined scaled padding/spacing values
# =========================================================

def padding_small() -> int:
    """Small padding - 4px base (appears as 6px at 150%)"""
    return scaled(4)


def padding_medium() -> int:
    """Medium padding - 7px base (appears as ~10px at 150%)"""
    return scaled(7)


def padding_large() -> int:
    """Large padding - 8px base (appears as 12px at 150%)"""
    return scaled(8)
