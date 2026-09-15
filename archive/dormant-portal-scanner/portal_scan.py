"""Reading a portal card instead of trusting its position.

Every portal bug this project has had comes back to one thing: a portal is
chosen by COORDINATE, and a coordinate is not an identity. The Items >
Portals grid and the post-run Portal Selection list both re-flow as portals
are spent, so the square that held the portal you picked yesterday holds a
different one today -- and the route spends it, with a log that reads clean
(convention 3f).

Better coordinates cannot fix that; only reading the card can. So a
coordinate stops being the ANSWER and becomes the SEARCH SPACE: click a
slot, read the detail pane it fills in, and confirm only when the name is
the one the task asked for and no blacklisted modifier is on it. A slot
holding the wrong portal is skipped rather than spent.

The mechanics here (tier-stripped identity, a sliding-window fuzzy match at
0.78, and the 4x-upscale + CLAHE + Otsu OCR variants) are reimplemented from
another build of this macro that solves the same problem the same way -- see
AI_CONTEXT. Everything in this module is pure enough to test without a game
running, which is deliberate: the matching rules are where the subtle bugs
live, and they should not need Roblox to check.
"""
import difflib
import re

import cv2
import numpy as np

from . import ocr_windows


# A task label carries the tier ("Summer Portal Tier 5") while the card's
# own title usually does not (it shows the tier on a separate line), so tier
# is stripped from BOTH sides before comparing. Matching on it would make
# every correct read fail.
_TIER = re.compile(r"\btier\s*\d+\b", re.IGNORECASE)
_WORDS = re.compile(r"[a-z0-9]+")

# How close a read has to be to count as the same name. OCR on stylised game
# text drops and doubles letters constantly, so this cannot be an equality
# test; 0.78 is the other build's figure and matches what its logs accept.
NAME_MATCH_RATIO = 0.78

# The default lattices, in reference space (1152x756).
#
# MEASURED off a real docked capture of Items > Portals
# (debug/portal_scan_frame.png), not guessed and not inherited: the values
# that shipped at 0.26.0 came from the other build's window and were wrong
# for ours by ~70px in x -- column one would have landed on the left nav
# rather than on a card. Card pitch here is ~92.7 across and ~92.3 down,
# with the four visible columns centred at 359/452/544/637 and the four
# fully-visible rows at 240/332/424/517.
#
# Four rows, not five: a fifth row is half-visible at the panel's bottom
# edge and the grid scrolls (the panel shows 20 of 100 items), so a click
# there lands on a partly-drawn card. Anything past the first sixteen needs
# scrolling, which the scanner does not do yet.
DEFAULT_INVENTORY_SLOTS = (
    (359, 240), (452, 240), (544, 240), (637, 240),
    (359, 332), (452, 332), (544, 332), (637, 332),
    (359, 424), (452, 424), (544, 424), (637, 424),
    (359, 517), (452, 517), (544, 517), (637, 517),
)
# The post-run Portal Selection list, measured off its own capture. It is a
# DIFFERENT screen, not the inventory in another frame: five columns instead
# of four, pitch ~89 across and ~89.5 down, and the whole panel sits left and
# up of the inventory's.
DEFAULT_CHOOSER_SLOTS = (
    (263, 243), (352, 243), (441, 243), (530, 243), (619, 243),
    (263, 332), (352, 332), (441, 332), (530, 332), (619, 332),
    (263, 421), (352, 421), (441, 421), (530, 421), (619, 421),
    (263, 511), (352, 511), (441, 511), (530, 511), (619, 511),
)

# Where the card's own name and modifier text land once a slot is selected.
#
# PER SCREEN, because the two detail panes do not line up: the chooser's sits
# about 25px left of the inventory's. Sharing one pair looked reasonable
# until both were OCR-ed against real captures of each screen -- the
# inventory pair scores 4/4 on the inventory and **0/4** on the chooser,
# where it slices "Summer" into "mmer" and drops the Traitless icon. Each
# pair below reads its own screen 4/4.
DEFAULT_NAME_REGION = (715, 190, 200, 44)
DEFAULT_MODIFIER_REGION = (718, 408, 235, 72)
DEFAULT_CHOOSER_NAME_REGION = (690, 196, 210, 42)
DEFAULT_CHOOSER_MODIFIER_REGION = (694, 400, 265, 72)


def identity(text: str) -> str:
    """A comparable form of a portal name, from either a task label or OCR.

    Lowercase, letters and digits only, tier removed. Curly apostrophes are
    folded to straight ones first so "Sovereign's" reads the same whichever
    way the game (or the user) typed it.
    """
    cleaned = _TIER.sub(" ", str(text or "").replace("’", "'"))
    return " ".join(_WORDS.findall(cleaned.lower()))


def _best_window_ratio(needle: str, haystack: str) -> float:
    """How well `needle` matches SOMEWHERE INSIDE `haystack`.

    The OCR of a detail pane carries more than the name -- rarity, stat
    lines, whatever else the crop caught -- so a whole-string ratio would
    punish every correct read for the words around it. Compare against every
    window of the same word count instead and keep the best.
    """
    if not needle or not haystack:
        return 0.0
    needle_words = needle.split()
    hay_words = haystack.split()
    if not needle_words or not hay_words:
        return 0.0
    span = len(needle_words)
    best = 0.0
    for start in range(max(1, len(hay_words) - span + 1)):
        window = " ".join(hay_words[start:start + span])
        best = max(best, difflib.SequenceMatcher(None, needle, window).ratio())
    # Also try the whole string: a one-word name in a one-word read is not
    # covered by the window loop above when the read is shorter than the name.
    return max(best, difflib.SequenceMatcher(None, needle, haystack).ratio())


def name_matches(target: str, text: str, ratio: float = NAME_MATCH_RATIO) -> bool:
    """Is `text` a read of the portal the task asked for?

    `target` may list alternatives separated by "|" -- useful when a portal
    reads differently at different tiers, or when the user is not sure which
    of two spellings the game uses.
    """
    read = identity(text)
    if not read:
        return False
    for option in str(target or "").split("|"):
        wanted = identity(option)
        if wanted and _best_window_ratio(wanted, read) >= ratio:
            return True
    return False


def blacklisted_modifier(blacklist, text: str, ratio: float = NAME_MATCH_RATIO):
    """The first blacklisted modifier this read appears to carry, or None.

    Same fuzzy window as the name, for the same reason: the modifier sits in
    a pane with other words around it.
    """
    read = identity(text)
    if not read:
        return None
    for modifier in (blacklist or ()):
        wanted = identity(modifier)
        if wanted and _best_window_ratio(wanted, read) >= ratio:
            return modifier
    return None


def ocr_variants(bgr) -> list:
    """Every plausible reading of one detail crop.

    At a real 1152x756 game window this text is only about 12-14 pixels
    high, and Windows OCR commonly returns an empty string at that size
    while reading it reliably after a 4x cubic enlargement. The contrast
    variants exist because portal cards come on both dark-red and dark-green
    backgrounds and neither is reliably readable with one preparation.

    Returns the distinct non-empty strings, best-effort: no OCR engine
    available means an empty list, which every caller treats as "unreadable"
    rather than as "no match".
    """
    if bgr is None or getattr(bgr, "size", 0) == 0:
        return []
    out = []
    try:
        big = cv2.resize(bgr, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
        _, otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        # Inverted too: light-on-dark is the common case here, but a pane
        # that renders dark-on-light reads as noise without it.
        candidates = (big, clahe, otsu, cv2.bitwise_not(otsu))
    except Exception:
        return []
    for image in candidates:
        try:
            text = (ocr_windows.ocr_image(image) or "").strip()
        except Exception:
            continue
        if text and text not in out:
            out.append(text)
    if out:
        return out

    # Nothing from the fast path. Fall back to the project's full OCR chain
    # (RapidOCR -> Windows OCR -> Tesseract, over its own prepared masks),
    # which is slower but is the one that works on a machine where Windows
    # OCR is missing entirely -- and "no OCR engine at all" was otherwise
    # indistinguishable from "the region is pointing at the wrong place".
    try:
        from . import ocr
        try:
            pytesseract = ocr.get_pytesseract()
        except Exception:
            pytesseract = None
        # psm 6 ("a block of text"), explicitly, for BOTH the config and the
        # sweep. The detail pane is two or three short lines, and ocr_best's
        # own default sweep is (7, 8) -- single line and single word -- which
        # it substitutes INTO the config string, quietly overriding a --psm 6
        # passed there. Measured on a real pane: psm 6 reads "Summer Portal"
        # on every variant, psm 7 gets "Sacnner Partal".
        text = (ocr.ocr_best(pytesseract, big, "--psm 6", psm_modes=(6, 7)) or "").strip()
        if text:
            out.append(text)
    except Exception:
        pass
    return out


def engine_status() -> dict:
    """Which OCR engines this machine actually has.

    The scanner is only as good as its OCR, and a machine with none reads
    every slot as blank -- which looks exactly like a mis-aimed region. So
    the status is reported explicitly rather than inferred from a failure.
    """
    status = {"windows": False, "windows_reason": "", "rapidocr": False, "tesseract": False}
    try:
        status["windows"] = bool(ocr_windows.is_available())
        if not status["windows"]:
            status["windows_reason"] = ocr_windows.unavailable_reason() or ""
    except Exception as exc:
        status["windows_reason"] = str(exc)
    try:
        from . import ocr
        try:
            status["rapidocr"] = bool(ocr.is_rapidocr_available())
        except Exception:
            pass
        try:
            status["tesseract"] = ocr.get_pytesseract() is not None
        except Exception:
            status["tesseract"] = False
    except Exception:
        pass
    return status


def describe_engines(status: dict) -> str:
    have = [name for name, key in (("Windows OCR", "windows"),
                                   ("RapidOCR", "rapidocr"),
                                   ("Tesseract", "tesseract")) if status.get(key)]
    if have:
        return ", ".join(have)
    reason = status.get("windows_reason") or ""
    return f"none available{f' ({reason})' if reason else ''}"


def describe_slots(slots) -> str:
    return ", ".join(f"({x}, {y})" for x, y in slots)


def normalize_slots(raw, fallback):
    """A stored slot list -> one the scanner can click.

    Anything malformed falls back to the shipped lattice rather than
    raising: a hand-edited settings.json must degrade to "behaves like
    stock", never stop a run before it starts.
    """
    if not isinstance(raw, (list, tuple)) or not raw:
        return tuple(fallback)
    out = []
    for item in raw[:60]:
        try:
            if isinstance(item, dict):
                x, y = int(item.get("x")), int(item.get("y"))
            else:
                x, y = int(item[0]), int(item[1])
        except (TypeError, ValueError, KeyError, IndexError):
            continue
        out.append((max(0, x), max(0, y)))
    return tuple(out) or tuple(fallback)


def normalize_region(raw, fallback):
    """Same contract as normalize_slots, for an (x, y, w, h) crop."""
    try:
        x, y, w, h = (int(v) for v in raw)
    except (TypeError, ValueError):
        return tuple(fallback)
    if w <= 0 or h <= 0:
        return tuple(fallback)
    return (max(0, x), max(0, y), w, h)
