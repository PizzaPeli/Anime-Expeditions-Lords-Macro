from unittest.mock import MagicMock

from core import vision
from core.runner import MacroRunner


def _runner():
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    runner._map_setups = {
        "New Map": {"mode": "story", "image": "New Map label",
                    "image_ready": True, "path": "New Map path"}}
    runner._log = MagicMock()
    return runner


def test_in_match_label_selects_the_added_map_setup(monkeypatch):
    runner = _runner()
    monkeypatch.setattr(vision, "find_image_any",
                        lambda _hwnd, _names: ({"score": 0.96}, "New Map label"))

    task, paths = runner._resolve_in_match_map_setup(
        1, {"mode": "story", "map": "Old Map", "macro": "Farm"}, {})

    assert task["map"] == "New Map"
    assert task["_map_setup"]["path"] == "New Map path"
    assert task["macro"] == "Farm"


def test_unrecognized_map_uses_autoplay_without_specific_setup(monkeypatch):
    from core import map_capture
    capture = MagicMock()
    monkeypatch.setattr(map_capture, "save_map_miss", capture)
    runner = _runner()
    monkeypatch.setattr(vision, "find_image_any", lambda _hwnd, _names: (None, None))

    task, paths = runner._resolve_in_match_map_setup(
        1, {"mode": "story", "map": "Old Map", "macro": "Farm"},
        {"Old Map": "Old route"})

    assert task["macro"] == ""
    assert task["auto_play"] == "autoplay"
    assert task["_map_unknown"] is True
    assert paths == {}
    capture.assert_called_once()
    assert capture.call_args.kwargs["candidates"] == {"New Map label": "New Map"}


def test_challenge_miss_already_reported_does_not_capture_twice(monkeypatch):
    from core import map_capture
    capture = MagicMock()
    monkeypatch.setattr(map_capture, "save_map_miss", capture)
    monkeypatch.setattr(vision, "find_image_any", lambda *_: (None, None))
    task, paths = _runner()._resolve_in_match_map_setup(
        1, {"mode": "story", "_map_miss_reported": True}, {})
    capture.assert_not_called()
    assert task["auto_play"] == "autoplay"
