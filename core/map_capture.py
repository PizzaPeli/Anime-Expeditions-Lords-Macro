"""Persistent evidence for an unrecognized in-match map, independent of debug toggles."""
import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import cv2

from . import vision


def placement_capture_reason(task):
    """Return why this stage needs a camera-ready reference, if any."""
    from . import maps
    if task.get("_map_unknown") or (task.get("is_challenge") and not task.get("map")):
        return "Unrecognized map after camera setup"
    category = {"story": "Story", "raid": "Raid", "portal": "Portal",
                "expedition": "Expedition", "event": "Event",
                "soul_furnace": "Event", "tower": "Tower",
                "tournament": "Tournament"}.get(task.get("mode"))
    name = "Expedition" if category == "Expedition" else task.get("map")
    if not category or not name:
        return None
    if maps.map_capture_note(category, name):
        return "Placement preview needs a camera-ready replacement"
    available = maps.list_maps(category)
    # Raid acts can have distinct placement views.
    if name in available or f"{name} Act{task.get('act')}" in available:
        return None
    return "Map has no placement preview"


def save_placement_reference(hwnd, *, task, profile, source, reason, log):
    """Archive a full-size post-camera frame for review, never auto-publish it."""
    try:
        frame = vision.capture_game_bgr(hwnd)
        if frame is None or frame.shape[:2] != (756, 1152):
            raise RuntimeError("Expected a 1152 x 756 Roblox capture")
        now = datetime.now().astimezone()
        folder = Path(vision.DEBUG_DIR) / "map_placements"
        folder.mkdir(parents=True, exist_ok=True)
        screenshot = folder / f"map_placement_{now:%Y%m%d_%H%M%S_%f}_{uuid4().hex[:8]}.png"
        if not cv2.imwrite(str(screenshot), frame):
            raise OSError("Could not write the Roblox screenshot")
        report = {
            "timestamp": now.isoformat(), "screenshot": screenshot.name,
            "phase": "after_camera_setup", "reason": reason,
            "map_identified": bool(task.get("_identified_map")),
            "map_unknown": bool(task.get("_map_unknown")),
            "task": {key: task[key] for key in (
                "name", "mode", "map", "act", "difficulty", "is_challenge",
                "is_daily_challenge", "challenge_slot") if key in task},
            "camera_profile": profile, "camera_source": source,
            "capture_size": {"width": frame.shape[1], "height": frame.shape[0]},
        }
        screenshot.with_suffix(".json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        log(f"[Macro] Saved camera-ready map placement reference to {screenshot}")
        return str(screenshot)
    except Exception as exc:
        log(f"[Macro] Couldn't save camera-ready map reference ({exc}).")
        return None


def save_map_miss(hwnd, *, task, candidates, log):
    """Capture only Roblox; failures must never interrupt the existing fallback."""
    try:
        frame = vision.capture_game_bgr(hwnd)
        if frame is None:
            raise RuntimeError("Roblox capture returned no pixels")
        now = datetime.now().astimezone()
        folder = Path(vision.DEBUG_DIR) / "unrecognized_maps"
        folder.mkdir(parents=True, exist_ok=True)
        stem = f"map_miss_{now:%Y%m%d_%H%M%S_%f}_{uuid4().hex[:8]}"
        screenshot = folder / f"{stem}.png"
        if not cv2.imwrite(str(screenshot), frame):
            raise OSError("Could not write the Roblox screenshot")
        log(f"[Macro] Unrecognized map: saved Roblox screenshot to {screenshot}")
        report = {
            "timestamp": now.isoformat(), "screenshot": screenshot.name,
            "mode": task.get("mode", ""),
            "task": {key: task[key] for key in (
                "name", "mode", "map", "act", "difficulty", "macro", "play_mode",
                "is_challenge", "is_daily_challenge", "challenge_slot") if key in task},
            "reason": "No saved in-match map label matched",
            "capture_size": {"width": frame.shape[1], "height": frame.shape[0]},
            "candidates": [],
        }
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        for image, name in candidates.items():
            entry = {"map": name, "image": image}
            try:
                probe = vision.find_in_gray_multiscale_diagnostic(gray, image)
                best = probe.get("best")
                entry["best_score"] = float(best["score"]) if best else None
            except Exception as exc:
                entry["error"] = str(exc)
            report["candidates"].append(entry)
        screenshot.with_suffix(".json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(screenshot)
    except Exception as exc:
        log(f"[Macro] Couldn't finish saving unrecognized-map evidence ({exc}).")
        return None
