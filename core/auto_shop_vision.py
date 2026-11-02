"""Offline-safe visual helpers for the Gold Shop item list.

All coordinates produced here stay in the same reference space as the item
match returned by :mod:`core.vision`. Re-finding the item after every scroll
therefore relocates the stock label without relying on page coordinates.
"""

from collections import Counter
from typing import Iterable, Mapping, Optional

import numpy as np
import cv2
from functools import lru_cache
from pathlib import Path

from . import auto_shop

IDENTITY_FROM_CENTER = (-68, -25, 140, 110)


@lru_cache(maxsize=128)
def _identity_references(item_key):
    from . import vision, image_io
    definition = auto_shop.item_definition(item_key)
    explicit = definition.get("identity")
    if explicit:
        frame = image_io.read_image(explicit)
        return [frame] if frame is not None else []
    references = []
    root = Path(auto_shop.ASSETS_DIR) / "reference" / "auto_shop"
    for path in sorted((root / "identities" / item_key).glob("*.png")):
        frame = image_io.read_image(str(path))
        if frame is not None:
            references.append(frame)
    if references:
        return references
    for path in sorted(root.glob("gold_shop_*.png")):
        frame = image_io.read_image(str(path))
        if frame is None:
            continue
        gray = cv2.cvtColor(frame[:, :, :3], cv2.COLOR_BGR2GRAY)
        match = vision.find_in_gray_multiscale(gray, definition["template"])
        if match is None:
            continue
        try:
            references.append(crop_region(frame, _region_from_item_match(match, IDENTITY_FROM_CENTER)))
        except ValueError:
            continue
    return references


def verify_card_identity(frame, item_key, match):
    """Verify the icon/name portion of the card, excluding price and stock."""
    try:
        x, y, width, height = _region_from_item_match(match, IDENTITY_FROM_CENTER)
        # Icon variants have different crop centers. Align the same card's
        # identity locally rather than requiring identical crop coordinates.
        left, top = max(0, x - 20), max(0, y - 20)
        right = min(frame.shape[1], x + width + 20)
        bottom = min(frame.shape[0], y + height + 20)
        actual = crop_region(frame, (left, top, right - left, bottom - top))
    except ValueError:
        return False
    actual = cv2.cvtColor(actual[:, :, :3], cv2.COLOR_BGR2GRAY)
    for reference in _identity_references(item_key):
        if (reference.shape[0] > actual.shape[0]
                or reference.shape[1] > actual.shape[1]):
            continue
        mask = reference[:, :, 3] if reference.shape[2] == 4 else None
        expected = cv2.cvtColor(reference[:, :, :3], cv2.COLOR_BGR2GRAY)
        method = cv2.TM_CCORR_NORMED if mask is not None else cv2.TM_CCOEFF_NORMED
        score = cv2.matchTemplate(actual, expected, method, mask=mask).max()
        if np.isfinite(score) and score >= 0.90:
            return True
    return False


STOCK_REGION_FROM_CENTER = (-42, -48, 64, 24)
STOCK_REGION_BASE_HEIGHT = STOCK_REGION_FROM_CENTER[3]
STOCK_REGION_TIGHT_HEIGHT = 18
STOCK_STATUS_FROM_CENTER = (-34, -55, 90, 46)
INITIAL_BUY_FROM_CENTER = (-68, 110, 140, 42)
CARD_TERMINAL_FROM_CENTER = (-68, -55, 140, 207)

CANCEL_ANCHOR_BASE_WIDTH = 181
AMOUNT_INPUT_FROM_CANCEL = (-185, -46, 48, 29)
AMOUNT_TOGGLE_FROM_CANCEL = (131, -46, 48, 29)

MODAL_OPENED = "opened"
MODAL_NOT_OPENED = "not_opened"
MODAL_CLOSED_AFTER_BUY = "closed_after_buy"
MODAL_REMAINS_AFTER_BUY = "remains_after_buy"
MODAL_UNKNOWN = "unknown"

_OCR_CONFIG = "--psm 7 -c tessedit_char_whitelist=0123456789"
_OCR_SHARPEN_AMOUNTS = (0.0, 1.5)
BUY_BUTTON_GREEN_MIN_FRACTION = 0.06


def stock_region_from_item_match(match: Mapping) -> tuple:
    """Derive the ``Left!`` crop from the freshly located item icon."""
    return _region_from_item_match(match, STOCK_REGION_FROM_CENTER)


def _region_from_item_match(match: Mapping, relative_region: tuple) -> tuple:
    try:
        x = int(match["x"])
        y = int(match["y"])
        width = int(match["w"])
        height = int(match["h"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "Item match must contain integer x, y, w, and h values"
        ) from exc
    if width <= 0 or height <= 0:
        raise ValueError("Item match dimensions must be positive")

    center_x = int(match.get("cx", x + width // 2))
    center_y = int(match.get("cy", y + height // 2))
    offset_x, offset_y, region_width, region_height = relative_region
    return (
        center_x + int(offset_x),
        center_y + int(offset_y),
        max(1, int(region_width)),
        max(1, int(region_height)),
    )


def stock_status_region_from_item_match(match: Mapping) -> tuple:
    """Return the larger item-relative region that can contain Out of Stock."""
    return _region_from_item_match(match, STOCK_STATUS_FROM_CENTER)


def initial_buy_region_from_item_match(match: Mapping) -> tuple:
    """Return the card's first Buy button bounds without matching its price."""
    return _region_from_item_match(match, INITIAL_BUY_FROM_CENTER)


def card_terminal_region_from_item_match(match: Mapping) -> tuple:
    """Return the card area containing terminal stock and inventory labels."""
    return _region_from_item_match(match, CARD_TERMINAL_FROM_CENTER)


def crop_region(frame_bgr: np.ndarray, region: tuple) -> np.ndarray:
    """Crop a validated reference-space region from a captured frame."""
    if frame_bgr is None or frame_bgr.size == 0:
        raise ValueError("Frame cannot be empty")
    x, y, width, height = (int(value) for value in region)
    frame_height, frame_width = frame_bgr.shape[:2]
    if width <= 0 or height <= 0:
        raise ValueError("Crop dimensions must be positive")
    if x < 0 or y < 0 or x + width > frame_width or y + height > frame_height:
        raise ValueError("Stock region falls outside the captured frame")
    return frame_bgr[y:y + height, x:x + width].copy()


def buy_button_is_enabled(crop_bgr: np.ndarray) -> bool:
    """Classify a known Buy rectangle by its total saturated-green coverage."""
    if crop_bgr is None or crop_bgr.size == 0:
        return False
    if crop_bgr.ndim != 3 or crop_bgr.shape[2] < 3:
        raise ValueError("Buy button crop must be a BGR image")
    pixels = crop_bgr[:, :, :3].astype(np.int16)
    blue, green, red = (pixels[:, :, index] for index in range(3))
    green_mask = (
        (green > 135)
        & (green - red > 45)
        & (green - blue > 70)
    )
    return float(green_mask.mean()) >= BUY_BUTTON_GREEN_MIN_FRACTION


def find_card_buy_button(frame_bgr: np.ndarray, item_match: Mapping) -> Optional[tuple]:
    """Find Buy below the icon within this card's own control band."""
    if frame_bgr is None or frame_bgr.ndim != 3 or frame_bgr.shape[2] < 3:
        return None
    icon_x = int(item_match.get("cx", int(item_match["x"]) + int(item_match["w"]) // 2))
    icon_y = int(item_match.get("cy", int(item_match["y"]) + int(item_match["h"]) // 2))
    icon_w = int(item_match["w"])
    frame_h, frame_w = frame_bgr.shape[:2]
    left = max(0, icon_x - icon_w * 2)
    right = min(frame_w, icon_x + icon_w * 2)
    top = max(0, icon_y + 55)
    bottom = min(frame_h, icon_y + 160)
    if right <= left or bottom <= top:
        return None
    crop = frame_bgr[top:bottom, left:right, :3].astype(np.int16)
    blue, green, red = (crop[:, :, channel] for channel in range(3))
    mask = ((green > 135) & (green - red > 45) & (green - blue > 70)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 9), np.uint8))
    candidates = []
    for contour in cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, width, height = cv2.boundingRect(contour)
        x += left
        y += top
        center_x = x + width / 2
        if (width < icon_w * 0.9 or height < icon_w * 0.3
                or abs(center_x - icon_x) > icon_w * 0.65):
            continue
        candidates.append((y, (x, y, width, height)))
    return min(candidates, default=(0, None))[1]


def _region_from_cancel(cancel_match: Mapping, relative_region: tuple) -> tuple:
    try:
        x = int(cancel_match["x"])
        y = int(cancel_match["y"])
        width = int(cancel_match["w"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Cancel match must contain integer x, y, and w values") from exc
    if width <= 0:
        raise ValueError("Cancel match width must be positive")

    scale = width / CANCEL_ANCHOR_BASE_WIDTH
    offset_x, offset_y, region_width, region_height = relative_region
    return (
        x + round(offset_x * scale),
        y + round(offset_y * scale),
        max(1, round(region_width * scale)),
        max(1, round(region_height * scale)),
    )


def amount_input_region_from_cancel(cancel_match: Mapping) -> tuple:
    """Return the numeric input bounds anchored to the visible Cancel button."""
    return _region_from_cancel(cancel_match, AMOUNT_INPUT_FROM_CANCEL)


def amount_toggle_region_from_cancel(cancel_match: Mapping) -> tuple:
    """Return the Max/Min toggle bounds anchored to the Cancel button."""
    return _region_from_cancel(cancel_match, AMOUNT_TOGGLE_FROM_CANCEL)


def find_modal_buy_button(frame_bgr: np.ndarray, cancel_match: Mapping) -> Optional[tuple]:
    """Locate the green confirmation button beside Cancel by its visible color.

    The price and amount printed on Buy change, so matching its text or using
    a stored offset from Cancel is unreliable after a modal layout change.
    """
    if frame_bgr is None or frame_bgr.ndim != 3 or frame_bgr.shape[2] < 3:
        return None
    cx, cy, cw, ch = (int(cancel_match[key]) for key in ("x", "y", "w", "h"))
    if cw <= 0 or ch <= 0:
        return None
    frame_h, frame_w = frame_bgr.shape[:2]
    left, right = 0, min(frame_w, cx + round(cw * 0.12))
    top = max(0, cy - round(ch * 1.5))
    bottom = min(frame_h, cy + round(ch * 2.5))
    if right <= left or bottom <= top:
        return None
    crop = frame_bgr[top:bottom, left:right, :3].astype(np.int16)
    blue, green, red = (crop[:, :, channel] for channel in range(3))
    mask = ((green > 135) & (green - red > 45) & (green - blue > 70)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 9), np.uint8))
    candidates = []
    for contour in cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, width, height = cv2.boundingRect(contour)
        x += left
        y += top
        if (width < cw * 0.55 or height < ch * 0.55
                or x + width > cx + cw * 0.12
                or abs((y + height / 2) - (cy + ch / 2)) > ch * 0.8):
            continue
        candidates.append((width * height, (x, y, width, height)))
    return max(candidates, default=(0, None))[1]


def cancel_click_point(cancel_match: Mapping) -> tuple:
    """Return the required far-right, inside-button Cancel click point."""
    try:
        return auto_shop.cancel_right_edge_point(
            int(cancel_match["x"]),
            int(cancel_match["y"]),
            int(cancel_match["w"]),
            int(cancel_match["h"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Cancel match must contain integer x, y, w, and h values") from exc


def classify_modal_transition(was_open: bool, is_open: Optional[bool]) -> str:
    """Classify the modal around the initial or final Buy click."""
    if is_open is None:
        return MODAL_UNKNOWN
    if not was_open:
        return MODAL_OPENED if is_open else MODAL_NOT_OPENED
    return MODAL_REMAINS_AFTER_BUY if is_open else MODAL_CLOSED_AFTER_BUY


def _ocr_values(crop_bgr: np.ndarray, daily_maximum: int) -> list:
    from . import ocr  # Legacy helper only; never imported by the shop sweep.
    try:
        engine = ocr.get_pytesseract()
    except ocr.TesseractNotAvailable:
        engine = None
    values = []
    for sharpen_amount in _OCR_SHARPEN_AMOUNTS:
        for mask in ocr.candidate_masks(crop_bgr, sharpen_amount=sharpen_amount):
            text = ocr.ocr_mask(engine, mask, _OCR_CONFIG)
            value = auto_shop.parse_left_count(text, daily_maximum)
            if value is not None:
                values.append(value)
    return values


def read_left_count(crop_bgr: np.ndarray, daily_maximum: int) -> Optional[int]:
    """Read one bounded stock count through a strict preprocessing vote."""
    def strict_vote(values):
        if not values:
            return None
        ranked = Counter(values).most_common()
        best_value, best_votes = ranked[0]
        second_votes = ranked[1][1] if len(ranked) > 1 else 0
        if best_votes < 2 or best_votes == second_votes:
            return None
        return best_value

    height = crop_bgr.shape[0]
    tight_height = round(
        height * STOCK_REGION_TIGHT_HEIGHT / STOCK_REGION_BASE_HEIGHT
    )
    if 0 < tight_height < height:
        tight_value = strict_vote(
            _ocr_values(crop_bgr[:tight_height], daily_maximum)
        )
        if tight_value is not None:
            return tight_value

    values = _ocr_values(crop_bgr, daily_maximum)
    if not values:
        return None
    return strict_vote(values)


def read_left_consensus(crops_bgr: Iterable[np.ndarray], daily_maximum: int) -> Optional[int]:
    """Read three short frames and require two identical stock values."""
    readings = [read_left_count(crop, daily_maximum) for crop in crops_bgr]
    return auto_shop.consensus_left_count(readings, daily_maximum)


def stock_visual_changed(first_signature: str, second_signature: str, threshold: float = 0.005) -> bool:
    """Return whether bright stock-label pixels changed beyond capture noise."""
    if threshold < 0 or threshold > 1:
        raise ValueError("Visual-change threshold must be between 0 and 1")
    return auto_shop.stock_signature_distance(first_signature, second_signature) > threshold
