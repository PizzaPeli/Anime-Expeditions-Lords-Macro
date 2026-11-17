"""District 7 controls measured from the creator's Bossrush captures."""
import random

import cv2

from . import vision


POLL_INTERVAL = 0.25
CARD_POINTS = {'flame': (278, 501), 'light': (577, 501), 'dark': (876, 501)}


def options(task):
    try:
        gates = max(2, min(6, int(task.get('bossrush_gates', 2))))
    except (TypeError, ValueError, OverflowError):
        gates = 2
    card = task.get('bossrush_card', 'random')
    return gates, card if card in CARD_POINTS else 'random'


def card_choice(preference):
    return preference if preference in CARD_POINTS else random.choice(tuple(CARD_POINTS))


def match(gray, name, region=None):
    """Use editable UI variants, with coordinates kept in reference pixels."""
    if gray is None or not getattr(gray, 'size', 0):
        return None
    x, y, w, h = region or (0, 0, gray.shape[1], gray.shape[0])
    try:
        found = vision.find_in_gray_multiscale(gray[y:y+h, x:x+w], name, threshold=0.9)
    except vision.TemplateNotFound:
        return None
    if found is not None:
        found = dict(found)
        found['x'] += x
        found['y'] += y
        found['cx'] += x
        found['cy'] += y
    return found


def observe(frame):
    if frame is None or not getattr(frame, 'size', 0):
        return {}
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    # Results and modal controls have priority over the gate labels behind them.
    names = {
        'victory': ('victory', (140, 100, 600, 220)),
        'defeat': ('defeat', (140, 100, 600, 220)),
        'card': ('bossrush_card', (490, 115, 175, 75)),
        'decision': ('bossrush_decision', (480, 90, 200, 50)),
        'start': ('nav_start_game', (430, 90, 290, 180)),
        'gates': ('bossrush_gate', (0, 180, 1000, 430)),
        'enter': ('bossrush_enter', (0, 180, 1000, 430)),
        'boss_health': ('bossrush_boss_health', (275, 50, 200, 50)),
    }
    return {key: match(gray, name, region) for key, (name, region) in names.items()}
