"""Puts the Roblox camera into the standard macro viewpoint: right-click drag
straight down until the pitch pins at its floor (top-down view), then hold O
for 2s so the scroll-out zoom reaches max.

Shared by Settings > Debug > "Camera Setup" (main.Api.debug_camera_setup,
on demand) and the macro run's Pre Start step (core.runner, automatically
before every match) -- both need the exact same sequence, so it lives here
once instead of twice.
"""
import json
import os
import time

from . import constants
from . import window as wm
from .jsonstore import write_json_atomic


def tilt_camera_top_down(mouse, hwnd) -> None:
    """Pin the Roblox camera pitch without changing its zoom.

    Caller owns the focus dance. Relative moves are required because Roblox
    consumes raw mouse deltas while the right button is held and recenters the
    hidden cursor every frame.
    """
    left, top, right, bottom = wm.get_window_rect_screen(hwnd)
    cx, cy = (left + right) // 2, (top + bottom) // 2
    mouse.move_to(cx, cy)
    time.sleep(0.15)
    mouse.nudge()  # force a real hover event before the click lands
    time.sleep(0.05)

    mouse.down("right")
    try:
        time.sleep(0.08)
        # Far more total downward travel than any camera needs to pin fully
        # down -- past the floor the extra deltas are no-ops, so overshooting
        # is free and saves needing to know the exact sensitivity/pitch-range.
        for _ in range(40):
            mouse.nudge(0, 80)
            time.sleep(0.012)
        time.sleep(0.08)
    finally:
        # If a nudge() ever raises mid-drag, an unguarded mouse.up("right")
        # below it would never run and leave the right button physically
        # held down for the rest of the run -- every later mouse move would
        # then read to Roblox as an active camera-rotate drag instead of a
        # normal, unlocked cursor move (the same "holding right click keeps
        # the mouse from locking" symptom this helper exists to produce).
        mouse.up("right")
    time.sleep(0.15)


def run_camera_setup(mouse, keyboard, hwnd, hold_ms: float = 2000) -> None:
    """Pin the pitch, then hold O for the standard maximum zoom-out."""
    tilt_camera_top_down(mouse, hwnd)

    keyboard.key_down(ord("O"))
    try:
        time.sleep(max(0.0, hold_ms) / 1000)
    finally:
        keyboard.key_up(ord("O"))


def run_camera_drag_hold(mouse, keyboard, hwnd, hold_ms: float = 2500, o_tap_ms: float = 0) -> None:
    """The same right-click drag-straight-down pitch pin as
    run_camera_setup, but followed by holding the LEFT ARROW key for
    hold_ms (a camera rotate) instead of the O zoom-hold -- then, if
    o_tap_ms > 0, a short O press for that long (a small zoom step, not
    the full 2s zoom-out). This is EXPEDITION's Pre Start camera setup
    (730ms rotate + 100ms O -- the standard sequence doesn't frame
    Expedition maps right, see core.runner's _run_prestart); Settings >
    Debug > "Camera Setup 3" runs the rotate part on demand with any hold
    time for tuning. Same relative-move drag mechanics and same
    held-input-released-in-finally safety as run_camera_setup above."""
    from . import keys

    tilt_camera_top_down(mouse, hwnd)

    keyboard.key_down(keys.VK_LEFT)
    try:
        time.sleep(max(0.0, hold_ms) / 1000)
    finally:
        keyboard.key_up(keys.VK_LEFT)

    if o_tap_ms > 0:
        time.sleep(0.1)
        keyboard.key_down(ord("O"))
        try:
            time.sleep(max(0.0, o_tap_ms) / 1000)
        finally:
            keyboard.key_up(ord("O"))


# ---------------------------------------------------------------------------
# Camera profiles (0.25)
#
# Until 0.25 the Pre Start camera was one hardcoded `if`: Expedition got the
# drag + 730ms rotate + short O tap, and EVERY other mode -- Story, Raid,
# Event, Portals, Tower, Tournament -- got the drag + 2s O zoom-out, whatever
# the map actually looked like. A map whose lanes run off the side of that
# framing had no way to say so.
#
# A profile is the same three primitives that hardcoded pair was built from,
# named and made data instead of code:
#
#   tilt       right-click drag straight down until the pitch pins (top-down)
#   rotate     hold an arrow key for N ms (swing the view around)
#   zoom       hold O for N ms (zoom out; 2000 is the old full zoom-out)
#
# Order is fixed -- tilt, then rotate, then zoom -- because that is the order
# the two built-in sequences already used and the only one that makes sense:
# pitch first (it is absolute, so it can't be undone by the others), then the
# rotate, then the zoom.
#
# Per MAP first, then per MODE, then "default". Maps are what differ; modes
# are the useful fallback (that is all Expedition's row ever was).
PROFILE_KEYS = ("tilt", "rotate_key", "rotate_ms", "o_ms")

BUILTIN_PROFILES = {
    "default": {"tilt": True, "rotate_key": "", "rotate_ms": 0, "o_ms": 2000},
    # Expedition's sequence, unchanged, now expressed as a row rather than an
    # `if` in _run_prestart -- the standard framing doesn't suit its maps.
    "expedition": {"tilt": True, "rotate_key": "left", "rotate_ms": 730, "o_ms": 100},
}

SHARED_PROFILES_FILE = os.path.join(constants.ASSETS_DIR, "default_camera_profiles.json")

# Arrow keys only. WASD would walk the character instead of moving the camera,
# and letting a profile hold an arbitrary key turns a camera setting into a
# "press anything before the round" setting, which is what macro blocks are.
ROTATE_KEY_NAMES = ("", "left", "right", "up", "down")


def load_shared_profiles() -> dict:
    """Load project-owned camera profiles shipped in the loose Assets folder."""
    try:
        with open(SHARED_PROFILES_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(saved, dict):
        return {}
    return {str(name): normalize_profile(profile) for name, profile in saved.items()
            if isinstance(profile, dict)}


def set_shared_profile(name: str, profile) -> dict:
    profiles = load_shared_profiles()
    profiles[name] = normalize_profile(profile)
    os.makedirs(os.path.dirname(SHARED_PROFILES_FILE), exist_ok=True)
    write_json_atomic(SHARED_PROFILES_FILE, profiles)
    return profiles


def clear_shared_profile(name: str) -> dict:
    profiles = load_shared_profiles()
    profiles.pop(name, None)
    os.makedirs(os.path.dirname(SHARED_PROFILES_FILE), exist_ok=True)
    write_json_atomic(SHARED_PROFILES_FILE, profiles)
    return profiles


def _rotate_vk(name: str):
    from . import keys
    return {
        "left": keys.VK_LEFT,
        "right": keys.VK_RIGHT,
        "up": keys.VK_UP,
        "down": keys.VK_DOWN,
    }.get((name or "").strip().lower())


def normalize_profile(raw, fallback: str = "default") -> dict:
    """A stored profile -> one this module will actually run.

    Anything malformed falls back to the named built-in rather than raising:
    a hand-edited settings.json must degrade to "behaves like stock", never
    stop a run before it starts. Values are clamped, so a typo'd 999999 ms
    rotate cannot hang Pre Start for a quarter of an hour.
    """
    base = dict(BUILTIN_PROFILES.get(fallback, BUILTIN_PROFILES["default"]))
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    if "tilt" in raw:
        out["tilt"] = bool(raw.get("tilt"))
    key = str(raw.get("rotate_key", out["rotate_key"]) or "").strip().lower()
    out["rotate_key"] = key if key in ROTATE_KEY_NAMES else ""
    for field, cap in (("rotate_ms", 10000), ("o_ms", 10000)):
        try:
            out[field] = max(0, min(int(raw.get(field, out[field]) or 0), cap))
        except (TypeError, ValueError):
            pass
    return out


def describe_profile(profile: dict) -> str:
    """One-line summary for the log, so a run says what framing it used."""
    profile = normalize_profile(profile)
    parts = ["tilt down" if profile["tilt"] else "no tilt"]
    if profile["rotate_key"] and profile["rotate_ms"]:
        parts.append(f"{profile['rotate_key']} arrow {profile['rotate_ms']}ms")
    if profile["o_ms"]:
        parts.append(f"O zoom {profile['o_ms']}ms")
    return ", ".join(parts)


def run_camera_profile(mouse, keyboard, hwnd, profile) -> None:
    """Run one profile. Every held input is released in a finally, the same
    rule the two sequences below already followed -- an exception mid-rotate
    must not leave an arrow key stuck down for the rest of the run."""
    profile = normalize_profile(profile)
    if profile["tilt"]:
        tilt_camera_top_down(mouse, hwnd)

    vk = _rotate_vk(profile["rotate_key"])
    if vk is not None and profile["rotate_ms"] > 0:
        keyboard.key_down(vk)
        try:
            time.sleep(profile["rotate_ms"] / 1000)
        finally:
            keyboard.key_up(vk)

    if profile["o_ms"] > 0:
        if profile["rotate_ms"] > 0:
            time.sleep(0.1)
        keyboard.key_down(ord("O"))
        try:
            time.sleep(profile["o_ms"] / 1000)
        finally:
            keyboard.key_up(ord("O"))
