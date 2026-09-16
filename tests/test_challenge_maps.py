"""Challenge map choices come from the editable map setup registry."""

from pathlib import Path

import main
from core import map_setups


def test_new_story_or_raid_map_is_available_to_challenge(monkeypatch):
    state = {"map_setups": {"New Map": {"mode": "raid", "image": "New Map label", "path": ""}}}
    monkeypatch.setattr(map_setups.settings, "load", lambda: state)
    monkeypatch.setattr(map_setups.settings, "update", lambda change: state.update(change))
    api = main.Api.__new__(main.Api)
    api.get_map_setups = lambda: map_setups.load()

    assert "New Map" in api._default_challenge_settings()["maps"]


def test_challenge_ui_renders_settings_maps_instead_of_a_literal_list():
    src = (Path(__file__).resolve().parent.parent / "ui" / "app.js").read_text(encoding="utf-8")
    assert "Object.keys(s.maps || {}).sort().map(map =>" in src
    assert "const CHALLENGE_STORY_MAPS =" not in src
