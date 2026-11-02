import json

import cv2
import numpy as np
import pytest

from core import map_capture, vision


def test_camera_ready_capture_preserves_coordinates_and_profile(tmp_path, monkeypatch):
    frame = np.full((756, 1152, 3), 77, dtype=np.uint8)
    monkeypatch.setattr(vision, "DEBUG_DIR", str(tmp_path))
    monkeypatch.setattr(vision, "capture_game_bgr", lambda _: frame)
    profile = {"tilt": True, "rotate_key": "left", "rotate_ms": 200, "o_ms": 2000}
    result = map_capture.save_placement_reference(
        1, task={"mode": "story", "map": "New Map", "_map_unknown": True},
        profile=profile, source="built-in default", reason="Unrecognized map", log=lambda _: None)
    assert np.array_equal(cv2.imread(result), frame)
    report = json.loads(next((tmp_path / "map_placements").glob("*.json")).read_text())
    assert report["phase"] == "after_camera_setup"
    assert report["camera_profile"] == profile
    assert report["map_unknown"] is True


def test_placement_capture_uses_missing_preview_and_unknown_flags(monkeypatch):
    from core import maps
    monkeypatch.setattr(maps, "list_maps", lambda category: ["Known", "Castle Act2"])
    assert map_capture.placement_capture_reason({"mode": "story", "map": "Known"}) is None
    assert map_capture.placement_capture_reason({"mode": "raid", "map": "Castle", "act": 2}) is None
    assert map_capture.placement_capture_reason({"mode": "story", "map": "New"})
    assert map_capture.placement_capture_reason({"mode": "story", "_map_unknown": True})
    assert map_capture.placement_capture_reason({"mode": "story", "is_challenge": True, "map": ""})


def test_map_miss_saves_game_pixels_and_diagnostics_without_overwriting(tmp_path, monkeypatch):
    frame = np.full((756, 1152, 3), 123, dtype=np.uint8)
    monkeypatch.setattr(vision, "DEBUG_DIR", str(tmp_path))
    monkeypatch.setattr(vision, "capture_game_bgr", lambda hwnd: frame)
    monkeypatch.setattr(vision, "find_in_gray_multiscale_diagnostic",
                        lambda *args: {"best": {"score": 0.61}})
    paths = [map_capture.save_map_miss(
        1, task={"mode": "raid", "map": "Selected map", "macro": "Farm"},
        candidates={"label": "Known map"}, log=lambda _: None) for _ in range(2)]
    assert paths[0] != paths[1]
    assert np.array_equal(cv2.imread(paths[0]), frame)
    reports = list((tmp_path / "unrecognized_maps").glob("*.json"))
    assert len(reports) == 2
    report = json.loads(reports[0].read_text())
    assert report["task"]["macro"] == "Farm"
    assert report["mode"] == "raid"
    assert report["candidates"][0]["best_score"] == 0.61


@pytest.mark.parametrize("failure", ["capture", "write", "score"])
def test_evidence_failures_are_nonfatal(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(vision, "DEBUG_DIR", str(tmp_path))
    monkeypatch.setattr(vision, "capture_game_bgr", lambda _: (
        None if failure == "capture" else np.zeros((4, 4, 3), dtype=np.uint8)))
    if failure == "write":
        monkeypatch.setattr(cv2, "imwrite", lambda *_: False)
    def unavailable(*_):
        raise vision.TemplateNotFound("missing reference")
    monkeypatch.setattr(vision, "find_in_gray_multiscale_diagnostic", unavailable)
    logs = []
    result = map_capture.save_map_miss(
        1, task={"mode": "story"}, candidates={"missing": "Map"}, log=logs.append)
    if failure == "score":
        assert result
        report = json.loads(next(tmp_path.rglob("*.json")).read_text())
        assert "missing reference" in report["candidates"][0]["error"]
    else:
        assert result is None
        assert "Couldn't finish saving" in logs[-1]
