"""User-editable Story/Raid map setups shared with Challenge."""

import re

from . import paths
from . import settings

INITIAL_MAPS = {
    "School Grounds": "story",
    "Rose Kingdom": "story",
    "Fairy King Forest": "story",
    "King's Tomb": "story",
    "Flower Forest": "story",
    "East Town": "story",
    "Spirit City": "raid",
    "Snowy Castle": "raid",
}


def load() -> dict:
    data = settings.load()
    saved = data.get("map_setups")
    if not isinstance(saved, dict):
        old_paths = {**paths.load_shipped_default_walk_paths(),
                     **(data.get("default_walk_paths", {}) or {})}
        saved = {name: {"mode": mode, "image": name,
                        "path": old_paths.get(name, ""), "legacy": True}
                 for name, mode in INITIAL_MAPS.items()}
    return {name: dict(entry) for name, entry in saved.items()
            if isinstance(name, str) and isinstance(entry, dict)}


def save(name: str, mode: str, image: str, path: str = "") -> dict:
    name = (name or "").strip()
    image = (image or "").strip()
    path = (path or "").strip()
    if (not name or mode not in ("story", "raid", "both") or not image
            or not re.fullmatch(r"[A-Za-z0-9 _\-']+", name)
            or not re.fullmatch(r"[A-Za-z0-9 _\-']+", image)):
        return {"ok": False, "reason": "name_mode_and_image_required"}
    if path and not (paths.load_path(path).get("events") or []):
        return {"ok": False, "reason": "path_has_no_recorded_movement"}
    current = load()
    if any(other != name and entry.get("image") == image for other, entry in current.items()):
        return {"ok": False, "reason": "image_already_identifies_another_map"}
    current[name] = {"mode": mode, "image": image, "path": path}
    settings.update({"map_setups": current})
    return {"ok": True, "map_setups": current}


def remove(name: str) -> dict:
    current = load()
    current.pop(name, None)
    settings.update({"map_setups": current})
    return {"ok": True, "map_setups": current}
