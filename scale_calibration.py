# scale_calibration.py
"""
Scale bar calibration and drawing module for InsituMicron GUI.

This module provides:
  1. ZOOM_CALIBRATIONS — a lookup table mapping each physical zoom lens barrel
     position to its calibration value (pixels_per_mm). Modify the
     pixels_per_mm values in this dict after performing empirical calibration
     with a stage micrometer.
  2. draw_scale_bar() — a pure function that draws a scale bar annotation
     onto a 2D grayscale numpy array. Called from ImageSaveWorker (save
     daemon thread), NOT from the camera acquisition hot path.

Camera: FLIR Grasshopper3 GS3-U3-23S6M-C (Monochrome)
  - Native resolution: 1920 x 1200 pixels
  - Pixel pitch: 5.86 µm (square pixels)
  - Output: 2D uint8 numpy array (1200, 1920)

Zoom Lens: Navitar barrel positions 0.7x–4.5x

HOW TO UPDATE CALIBRATION VALUES:
  1. Mount a stage micrometer under the camera.
  2. Set the zoom lens to a specific barrel position (e.g., "1.0x").
  3. Capture an image and measure how many pixels span a known physical
     distance (e.g., 1 mm) using ImageJ or similar.
  4. Replace the pixels_per_mm value in ZOOM_CALIBRATIONS below.
  5. Repeat for each zoom setting.
  6. Set pixels_per_mm to None for any uncalibrated zoom setting —
     the scale bar will be suppressed with a warning logged.
"""

import numpy as np
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    cv2 = None
    HAS_CV2 = False

from logging_config import get_logger
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# CALIBRATION TABLE
# Modify pixels_per_mm values here after empirical calibration.
# Keys must exactly match the physical label on the Navitar zoom lens barrel.
# Dict order = dropdown display order (Python 3.7+ ordered dict guarantee).
# ---------------------------------------------------------------------------
ZOOM_CALIBRATIONS = {
    "0.7": {"pixels_per_mm": 1012.0, "display_label": "0.7"},
    "1.0": {"pixels_per_mm": 1439.0, "display_label": "1.0"},
    "1.5": {"pixels_per_mm": 2083.0, "display_label": "1.5"},
    "2.0": {"pixels_per_mm": 2695.0, "display_label": "2.0"},
    "2.5": {"pixels_per_mm": 3344.0, "display_label": "2.5"},
    "3.0": {"pixels_per_mm": 4098.0, "display_label": "3.0"},
    "3.5": {"pixels_per_mm": 4854.0, "display_label": "3.5"},
    "4.0": {"pixels_per_mm": 5682.0, "display_label": "4.0"},
    "4.5": {"pixels_per_mm": 6329.0, "display_label": "4.5"},
}
# NOTE: All values above are THEORETICAL (pixel_pitch / magnification).
# Replace with empirically measured values after calibration. Set to None
# to mark a zoom setting as uncalibrated — the scale bar will be suppressed
# with a warning logged rather than drawing an inaccurate annotation.


# ---------------------------------------------------------------------------
# SCALE BAR CONSTANTS
# ---------------------------------------------------------------------------

# Candidate physical lengths for the scale bar label (in mm).
# The algorithm picks the candidate that produces a bar closest to 15% of
# image width. Keep this list sorted ascending.
_CANDIDATE_LENGTHS_MM = [0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0]

_TARGET_BAR_FRACTION = 0.15   # bar width as fraction of image width
_BOX_PADDING = 12             # pixels inside background box on all sides
_TICK_HEIGHT = 10             # pixels: vertical tick marks at bar ends
_BAR_THICKNESS = 2            # pixels: horizontal bar line thickness
_TICK_THICKNESS = 2           # pixels: vertical tick line thickness
_LABEL_SPACING = 6            # pixels: gap between text baseline and bar top
_CORNER_RADIUS = 8            # pixels: rounded corner radius on background box
_EDGE_MARGIN = 20             # pixels: gap from image right and bottom edges
_BOX_FILL = 50                # grayscale value: dark gray background box
_BAR_COLOR = 255              # grayscale value: white bar, ticks, text
_FONT_THICKNESS = 1


def _get_font():
    """Return cv2 font constant, or None if cv2 is unavailable."""
    if not HAS_CV2:
        return None
    return cv2.FONT_HERSHEY_DUPLEX


def _draw_rounded_rect(img, x1, y1, x2, y2, radius, color):
    """
    Draw a filled rounded rectangle on a 2D grayscale numpy array in-place.
    Uses 4 quarter-ellipses at corners + 2 fill rectangles for the body.
    All color values are scalar grayscale integers (0–255).
    """
    # Four corner ellipses (filled)
    cv2.ellipse(img, (x1 + radius, y1 + radius), (radius, radius), 180, 0, 90, color, -1)
    cv2.ellipse(img, (x2 - radius, y1 + radius), (radius, radius), 270, 0, 90, color, -1)
    cv2.ellipse(img, (x1 + radius, y2 - radius), (radius, radius),  90, 0, 90, color, -1)
    cv2.ellipse(img, (x2 - radius, y2 - radius), (radius, radius),   0, 0, 90, color, -1)
    # Two fill rectangles for body
    cv2.rectangle(img, (x1 + radius, y1), (x2 - radius, y2), color, -1)
    cv2.rectangle(img, (x1, y1 + radius), (x2, y2 - radius), color, -1)


def draw_scale_bar(image: np.ndarray, pixels_per_mm: float) -> np.ndarray:
    """
    Draw a scale bar annotation on a 2D grayscale numpy image.

    The scale bar is drawn at the bottom-right corner inside a dark gray
    rounded-rectangle background box. A white horizontal bar with vertical
    tick marks at both ends and a text label above represent a physically
    accurate length in the specimen plane.

    Args:
        image:         2D numpy array, shape (H, W), dtype uint8 (grayscale).
                       Must NOT be a 3-channel RGB array.
        pixels_per_mm: Calibration value. Number of pixels per 1mm of physical
                       distance at the current zoom setting. Must be > 0.

    Returns:
        A new numpy array (same shape and dtype) with the scale bar drawn.
        The input array is never modified in-place.
        If any input is invalid or cv2 is unavailable, returns a copy of the
        original image unchanged and logs a warning.

    IMPORTANT — OpenCV font limitation:
        cv2.FONT_HERSHEY_* fonts only support 7-bit ASCII characters.
        The Unicode micro sign (µ) CANNOT be rendered. Use "um" not "µm".
    """
    # --- Guard: return unchanged copy on any invalid input ---
    if image is None or image.ndim != 2:
        logger.warning("draw_scale_bar: image must be 2D grayscale array, got ndim=%s",
                       getattr(image, 'ndim', None))
        return image.copy() if image is not None else np.zeros((100, 100), dtype=np.uint8)

    if not HAS_CV2 or cv2 is None:
        logger.warning("draw_scale_bar: cv2 not available, scale bar suppressed")
        return image.copy()

    if pixels_per_mm is None or pixels_per_mm <= 0:
        logger.warning("draw_scale_bar: invalid pixels_per_mm=%s, scale bar suppressed", pixels_per_mm)
        return image.copy()

    img_h, img_w = image.shape
    font = _get_font()

    # ------------------------------------------------------------------
    # STEP 1 — Choose a clean physical length for the scale bar label
    # ------------------------------------------------------------------
    target_phys_mm = (img_w * _TARGET_BAR_FRACTION) / pixels_per_mm
    clean_phys_mm = min(_CANDIDATE_LENGTHS_MM, key=lambda c: abs(c - target_phys_mm))
    bar_px = int(round(clean_phys_mm * pixels_per_mm))

    # Guard: bar must be a usable size
    if bar_px < 10 or bar_px > img_w - 2 * _EDGE_MARGIN:
        logger.warning(
            "draw_scale_bar: computed bar_px=%d is out of usable range for img_w=%d, suppressed",
            bar_px, img_w)
        return image.copy()

    # ------------------------------------------------------------------
    # STEP 2 — Build label text (ASCII only — no Unicode micro sign)
    # ------------------------------------------------------------------
    if clean_phys_mm >= 1.0:
        val = int(clean_phys_mm) if clean_phys_mm == int(clean_phys_mm) else clean_phys_mm
        label_text = f"{val} mm"
    else:
        um_val = int(round(clean_phys_mm * 1000))
        label_text = f"{um_val} um"

    # ------------------------------------------------------------------
    # STEP 3 — Measure text to compute layout dimensions
    # ------------------------------------------------------------------
    font_scale = (img_w / 1920.0) * 0.65   # scale relative to 1920px reference width
    (text_w, text_h), baseline = cv2.getTextSize(label_text, font, font_scale, _FONT_THICKNESS)

    # Box must be wide enough to contain both the bar and the label text
    content_w = max(bar_px, text_w)
    box_w = content_w + 2 * _BOX_PADDING
    box_h = _BOX_PADDING + text_h + _LABEL_SPACING + _BAR_THICKNESS + _TICK_HEIGHT + _BOX_PADDING

    # Guard: ensure box is large enough for rounded corners
    if box_w < 2 * _CORNER_RADIUS or box_h < 2 * _CORNER_RADIUS:
        logger.warning("draw_scale_bar: box too small for corner radius, suppressed")
        return image.copy()

    # ------------------------------------------------------------------
    # STEP 4 — Compute box position (bottom-right, _EDGE_MARGIN from edges)
    # ------------------------------------------------------------------
    box_x2 = img_w - _EDGE_MARGIN
    box_y2 = img_h - _EDGE_MARGIN
    box_x1 = box_x2 - box_w
    box_y1 = box_y2 - box_h

    # Clamp to image bounds (should not be needed at normal resolutions)
    box_x1 = max(0, box_x1)
    box_y1 = max(0, box_y1)
    box_x2 = min(img_w - 1, box_x2)
    box_y2 = min(img_h - 1, box_y2)

    # ------------------------------------------------------------------
    # STEP 5 — Draw
    # ------------------------------------------------------------------
    img = image.copy()   # never modify input in-place

    # 5a. Background rounded rectangle
    _draw_rounded_rect(img, box_x1, box_y1, box_x2, box_y2, _CORNER_RADIUS, _BOX_FILL)

    # 5b. Bar geometry — centered horizontally inside box
    bar_cx = (box_x1 + box_x2) // 2
    bar_x1 = bar_cx - bar_px // 2
    bar_x2 = bar_x1 + bar_px

    # Bar y-position: sits above bottom padding, with tick below it
    bar_y = box_y2 - _BOX_PADDING - _TICK_HEIGHT - (_BAR_THICKNESS // 2)

    # 5c. Horizontal bar line
    cv2.line(img, (bar_x1, bar_y), (bar_x2, bar_y), _BAR_COLOR, _BAR_THICKNESS)

    # 5d. Left tick mark (vertical, extends downward from bar)
    cv2.line(img, (bar_x1, bar_y), (bar_x1, bar_y + _TICK_HEIGHT), _BAR_COLOR, _TICK_THICKNESS)

    # 5e. Right tick mark
    cv2.line(img, (bar_x2, bar_y), (bar_x2, bar_y + _TICK_HEIGHT), _BAR_COLOR, _TICK_THICKNESS)

    # 5f. Label text — centered above bar
    text_x = bar_cx - text_w // 2
    # text_y is baseline position; place text so its bottom sits _LABEL_SPACING above bar_y
    text_y = bar_y - _LABEL_SPACING - baseline

    cv2.putText(img, label_text, (text_x, text_y),
                font, font_scale, _BAR_COLOR, _FONT_THICKNESS, cv2.LINE_AA)

    return img
