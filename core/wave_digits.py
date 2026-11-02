"""Fast, conservative recognition of the small current-only wave badge.

References are cropped glyphs from verified game captures. Unknown glyphs,
ambiguous matches, and finite counters fall back to the existing OCR reader.
"""
from functools import lru_cache
from pathlib import Path
import itertools

import cv2
import numpy as np

from .constants import ASSETS_DIR


@lru_cache(maxsize=1)
def _references():
    root = Path(ASSETS_DIR)
    label_path = root / "ui/soul_wave_label/soul_wave_label.png"
    if not label_path.is_file():
        return None, []
    label = cv2.imdecode(np.fromfile(str(label_path), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    glyphs = {}
    for path in (root / "reference/wave_digits").glob("*.png"):
        digit = path.stem.split("_")[0]
        glyph = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_GRAYSCALE) > 0
        if not any(glyph.shape == old.shape and np.array_equal(glyph, old)
                   for old in glyphs.get(digit, [])):
            glyphs.setdefault(digit, []).append(glyph)
    candidates = []
    for value in range(100):
        text = str(value)
        if any(d not in glyphs for d in text):
            continue
        for parts in itertools.product(*(glyphs[d] for d in text)):
            for gap in ((0,) if len(parts) == 1 else (0, 1, 2)):
                for shifts in itertools.product((0, 1), repeat=len(parts)):
                    height = max(p.shape[0]+shift for p, shift in zip(parts, shifts))
                    width = sum(p.shape[1] for p in parts) + gap*(len(parts)-1)
                    joined = np.zeros((height, width), dtype=bool)
                    x = 0
                    for part, shift in zip(parts, shifts):
                        h, w = part.shape
                        joined[shift:shift+h, x:x+w] = part
                        x += w+gap
                    candidates.append((value, joined))
    return label, candidates


def read_current_badge(region_bgr):
    label, candidates = _references()
    if label is None or region_bgr.shape[0] < 15 or region_bgr.shape[1] < 50:
        return None
    gray = cv2.cvtColor(region_bgr[:28], cv2.COLOR_BGR2GRAY)
    if gray.shape[0] < label.shape[0] or gray.shape[1] < label.shape[1]:
        return None
    _, score, _, (x, y) = cv2.minMaxLoc(cv2.matchTemplate(gray, label, cv2.TM_CCOEFF_NORMED))
    if score < 0.88 or not 54 <= x <= 66:
        return None
    mask = cv2.inRange(gray[max(0, y-1):y+label.shape[0]+1, x-34:x-5], 190, 255) > 0
    points = cv2.findNonZero(mask.astype(np.uint8))
    if points is None:
        return None
    left, top, w, h = cv2.boundingRect(points)
    observed = mask[top:top+h, left:left+w]
    # A slash or an extra HUD token must not be silently trimmed away.
    if h < 6 or w > 17 or observed.sum() < 10:
        return None
    scores = {}
    for value, candidate in candidates:
        ch, cw = candidate.shape
        if abs(cw-w) > 1 or abs(ch-h) > 1:
            continue
        resized = cv2.resize(candidate.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST) > 0
        dice = 2*float(np.logical_and(observed, resized).sum())/(observed.sum()+resized.sum())
        scores[value] = max(scores.get(value, 0), dice)
    ranked = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
    if not ranked or ranked[0][1] < 0.93:
        return None
    if len(ranked) > 1 and ranked[0][1]-ranked[1][1] < 0.04:
        return None
    return ranked[0][0]
