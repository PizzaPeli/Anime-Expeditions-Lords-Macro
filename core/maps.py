"""Serves the map catalog (Assets/map_previews/<Category>/<Map name>.png) to the
Place Unit picker in Creation -- lets a player click a spot on a reference
map image (or a live Roblox snapshot, see main.get_roblox_snapshot) to read
off an X/Y position instead of guessing coordinates blind.
"""
import base64
import json
import os
import re
import tempfile

from . import constants

MAPS_DIR = os.path.join(constants.ASSETS_DIR, "map_previews")

EXPEDITION_SCREENS_DIR = os.path.join(constants.APP_DIR, "placement_screens", "Expedition")

_IMAGE_EXTS = (".png", ".jpg", ".jpeg")


def list_categories() -> list:
    categories = {d for d in os.listdir(MAPS_DIR) if os.path.isdir(os.path.join(MAPS_DIR, d))} if os.path.isdir(MAPS_DIR) else set()
    return sorted(categories | {"Expedition"})


def list_maps(category: str) -> list:
    if category == "Expedition":
        # All Expedition maps use one camera setup and one placement screen.
        folders = (EXPEDITION_SCREENS_DIR, os.path.join(MAPS_DIR, category))
        return ["Expedition"] if any(os.path.isfile(os.path.join(folder, "Expedition" + ext))
                                     for folder in folders for ext in _IMAGE_EXTS) else []
    folder = os.path.join(MAPS_DIR, category)
    if not os.path.isdir(folder):
        return []
    return sorted(
        os.path.splitext(f)[0] for f in os.listdir(folder)
        if f.lower().endswith(_IMAGE_EXTS)
    )


def map_image_data_uri(category: str, name: str) -> str:
    if category == "Expedition" and not _valid_screen_name(name):
        return ""
    folders = [os.path.join(MAPS_DIR, category)]
    if category == "Expedition":
        # Accept an older remembered map name, but always resolve the default.
        name = "Expedition"
        folders = [EXPEDITION_SCREENS_DIR] + folders
    for folder in folders:
        for ext in _IMAGE_EXTS:
            path = os.path.join(folder, f"{name}{ext}")
            if os.path.isfile(path):
                mime = "image/png" if ext == ".png" else "image/jpeg"
                with open(path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                return f"data:{mime};base64,{b64}"
    return ""


def _valid_screen_name(name: str) -> bool:
    return isinstance(name, str) and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _'-]{0,79}", name))


def save_expedition_screen(name: str, data_uri: str) -> None:
    """Replace the single shared Expedition screen with a normalized capture."""
    if not _valid_screen_name(name):
        raise ValueError("Use a map name with letters, numbers, spaces, apostrophes or hyphens.")
    if not isinstance(data_uri, str) or not data_uri.startswith("data:image/png;base64,") or len(data_uri) > 8_000_000:
        raise ValueError("Expected a PNG Roblox capture.")
    import cv2
    import numpy as np
    try:
        raw = base64.b64decode(data_uri.split(",", 1)[1], validate=True)
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None or image.shape[:2] != (756, 1152):
            raise ValueError("Capture must be 1152 x 756 pixels.")
    except (ValueError, TypeError, cv2.error) as exc:
        raise ValueError("Invalid Roblox capture: " + str(exc)) from exc
    os.makedirs(EXPEDITION_SCREENS_DIR, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=EXPEDITION_SCREENS_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, os.path.join(EXPEDITION_SCREENS_DIR, "Expedition.png"))
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def map_capture_note(category: str, name: str) -> str:
    if category != "Story":
        return ""
    try:
        with open(os.path.join(MAPS_DIR, "capture_notes.json"), encoding="utf-8") as stream:
            return json.load(stream).get(name, {}).get("note", "")
    except (OSError, ValueError):
        return ""
