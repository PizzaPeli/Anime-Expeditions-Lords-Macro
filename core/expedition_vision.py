"""Conservative Expedition stage and selected-unit reads in reference pixels.

The current node is the icon above the player marker, not any future sword
or shield elsewhere on the route. Never infer defense from a timer or kills.
"""
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from .constants import ASSETS_DIR
from .image_io import read_image


@lru_cache(maxsize=16)
def _reference(name):
    return read_image(Path(ASSETS_DIR) / 'reference/expedition/20261115' / f'{name}.png',
                      cv2.IMREAD_GRAYSCALE)


@lru_cache(maxsize=6)
def _digit_reference(value):
    return read_image(Path(ASSETS_DIR) / 'reference/expedition/20261115'
                      / f'auto_upgrade_{value}.png', cv2.IMREAD_COLOR)


def _match(frame, name, region, threshold=0.88):
    if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
        return None
    template = _reference(name)
    x, y, w, h = region
    crop = frame[y:y+h, x:x+w]
    if template is None or crop.shape[0] < template.shape[0] or crop.shape[1] < template.shape[1]:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    _, score, _, (mx, my) = cv2.minMaxLoc(cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED))
    if score < threshold:
        return None
    return x+mx, y+my, float(score)


def is_defense(frame):
    # Both cues must agree. The initial setup has the same close camera but
    # no wave counter; assault can retain a stale wave badge in transitions.
    return bool((_match(frame, 'active_defense', (417, 60, 28, 27), 0.88)
                 or _match(frame, 'active_elite', (417, 60, 28, 27), 0.90))
                and _match(frame, 'wave_label', (370, 20, 110, 30), 0.88))


def stage(frame):
    """Positive current-node identification; an unreadable frame is unknown."""
    if is_defense(frame):
        return 'defense'
    # Do not interpret a missing wave label as initial setup. A defense HUD
    # can still be animating in while Start Game is already clickable.
    for name in ('setup', 'assault'):
        if _match(frame, 'active_'+name, (417, 60, 28, 27), 0.90):
            return name
    return None


def selected_unit(frame):
    """Return this individual panel's close/button points, never Unit Manager."""
    close = _match(frame, 'panel_close', (10, 160, 430, 420), 0.90)
    if close is None:
        return None
    x, y, _ = close
    # The Priority label confirms the individual panel's bottom row without
    # depending on the player's rebindable Auto Upgrade hotkey glyph.
    label = _match(frame, 'unit_priority_label', (x-312, y+181, 60, 26), 0.88)
    if label is None:
        return None
    # Units with an extra ability button put Auto Upgrade one slot left.
    # Match only the two measured priority fields, never that ability button.
    for dx in (-16, -61):
        panel = {'close': (x+15, y+15), 'button': (x+dx+9, y+207),
                 'number_box': (x+dx, y+201, 18, 15)}
        if auto_upgrade_state(frame, panel) is not None:
            return panel
    return {'close': (x+15, y+15), 'button': (x-7, y+207),
            'number_box': (x-16, y+201, 18, 15)}


def auto_upgrade_state(frame, panel):
    """0 = off, 1..6 = priority, None = unreadable (never assume off)."""
    if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
        return None
    x, y, w, h = panel['number_box']
    # The narrower control beside an ability button centers its glyph a few
    # pixels differently. Allow that local shift within the measured field.
    crop = frame[y:y+h, max(0, x-3):x+w+3]
    if crop.shape[:2] != (h, w+6):
        return None
    # Number glyphs are neutral white over a blue control. Comparing the
    # entire grayscale field couples recognition to the button's hover tint.
    # Mask the colored background and compare the actual digit instead.
    def glyph(image):
        low = image.min(axis=2).astype(np.float32)
        high = image.max(axis=2).astype(np.float32)
        return np.where(high-low <= high*0.15, low, 0).astype(np.uint8)

    digit = glyph(crop)
    digit_scores = []
    for value in range(1, 7):
        ref = _digit_reference(value)
        if ref is not None:
            score = float(cv2.minMaxLoc(cv2.matchTemplate(
                digit, glyph(ref), cv2.TM_CCOEFF_NORMED))[1])
            digit_scores.append((score, value))
    digit_scores.sort(reverse=True)
    # Require blue around the glyph: an ability icon/number in the adjacent
    # purple control must never be treated as this unit's upgrade priority.
    blue = (crop[:, :, 0].astype(float) > crop[:, :, 2]*1.5) & (crop[:, :, 1] > crop[:, :, 2]*1.5)
    if (blue.mean() > 0.3 and digit_scores and digit_scores[0][0] >= 0.92
            and digit_scores[0][0]-digit_scores[1][0] >= 0.06):
        return digit_scores[0][1]
    if blue.mean() > 0.3:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    scores = []
    for value in (0,):
        name = str(value) if value else 'off'
        names = ['auto_upgrade_'+name]
        if value == 0:
            names.append('auto_upgrade_off_ability')
        matches = []
        for name in names:
            ref = _reference(name)
            if ref is not None:
                matches.append(float(cv2.minMaxLoc(cv2.matchTemplate(
                    gray, ref, cv2.TM_CCOEFF_NORMED))[1]))
        if matches:
            scores.append((max(matches), value))
    scores.sort(reverse=True)
    if scores and scores[0][0] >= 0.90 and (len(scores) == 1 or scores[0][0]-scores[1][0] >= 0.06):
        return scores[0][1]
    # Every state has a captured reference. An ambiguous/obscured field is
    # unreadable, never a reason to guess or blindly cycle the control.
    return None
