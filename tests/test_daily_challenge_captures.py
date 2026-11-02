"""Replay the captured Daily Challenge entry without coordinate fallback."""
from pathlib import Path
import threading
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from core import runner as runner_module
from core import vision
from core.runner import MacroRunner


ROOT = Path(__file__).resolve().parents[1]


def panel(name):
    frame = np.zeros((756, 1152), dtype=np.uint8)
    frame[155:600, 190:965] = cv2.imread(str(ROOT / f"Assets/reference/daily_challenge/{name}.png"), 0)
    return frame


def find(frame, name, threshold=0.75):
    return vision.find_in_gray_multiscale_diagnostic(frame, name, threshold=threshold)["match"]


@pytest.mark.parametrize("name", ["regular_panel", "daily_panel"])
def test_available_tab_matches_both_selected_and_unselected_states(name):
    match = find(panel(name), "daily_challenge_available")
    assert match is not None
    assert match["score"] > 0.95
    assert 200 < match["cx"] < 377
    assert 305 < match["cy"] < 350


def test_daily_stage_match_does_not_depend_on_the_map_or_reset_countdown():
    frame = panel("daily_panel")
    frame[249:286, 550:934] = 0  # remove map name and difficulty
    frame[369:390, 207:371] = 0  # remove the daily reset timer
    match = find(frame, "daily_challenge_stage")
    assert match is not None
    assert match["score"] > 0.95
    assert 548 < match["cx"] < 653
    assert 232 < match["cy"] < 247
    assert find(frame, "daily_challenge_available") is not None


def test_gray_weekly_card_cannot_stand_in_for_available_daily():
    original = panel("regular_panel")
    frame = np.zeros_like(original)
    frame[403:495, 198:378] = original[403:495, 198:378]
    assert find(frame, "daily_challenge_available") is None


def test_captured_daily_entry_clicks_tab_then_stage_without_any_backup_point(monkeypatch):
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    runner._open_challenge_screen = MagicMock(return_value=True)
    runner._checkpoint = MagicMock(return_value=False)
    runner._set_status = MagicMock()
    runner._debug_save = MagicMock(return_value=None)
    runner._cxy = lambda *_: pytest.fail("A captured entry step fell back to coordinates")
    state = {"panel": "regular_panel"}
    clicks = []

    def find_image(_hwnd, name, **kwargs):
        return find(panel(state["panel"]), name, kwargs.get("threshold", vision.DEFAULT_THRESHOLD))

    def click(_mouse, _hwnd, match, **kwargs):
        if state["panel"] == "regular_panel":
            assert 200 < match["cx"] < 377 and 305 < match["cy"] < 350
            state["panel"] = "daily_panel"
            clicks.append("daily_tab")
        else:
            assert 548 < match["cx"] < 653 and 232 < match["cy"] < 247
            state["panel"] = "daily_stage_selected"
            clicks.append("daily_stage")

    def enter(*args, **kwargs):
        assert state["panel"] == "daily_stage_selected"
        assert find(panel(state["panel"]), "chal_select") is not None
        assert kwargs["daily"] is True
        return True

    runner._enter_selected_challenge = enter
    monkeypatch.setattr(vision, "find_image", find_image)
    monkeypatch.setattr(vision, "wait_for_image", lambda hwnd, name, **kwargs: find_image(hwnd, name, **kwargs))
    monkeypatch.setattr(vision, "click_match", click)
    monkeypatch.setattr(runner_module.wm, "activate_window", lambda _: True)
    monkeypatch.setattr(runner_module.time, "sleep", lambda _: None)
    assert runner._enter_daily_challenge_stage(123, threading.Event(), "solo", {}, {}) == "entered"
    assert clicks == ["daily_tab", "daily_stage"]
