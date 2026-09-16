import threading
from unittest.mock import MagicMock

import cv2
import numpy as np

from core import ocr, vision
from core.runner import MacroRunner


def _runner():
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    runner._log = MagicMock()
    runner._set_status = MagicMock()
    runner._checkpoint = lambda _stop: False
    runner._interruptible_sleep = MagicMock()
    return runner


def test_party_start_is_recognized_by_button_color_and_text(monkeypatch):
    frame = np.zeros((756, 1152, 3), dtype=np.uint8)
    cv2.rectangle(frame, (570, 490), (810, 535), (25, 190, 35), -1)
    monkeypatch.setattr(vision, "capture_game_bgr", lambda _hwnd: frame)
    monkeypatch.setattr(ocr, "get_pytesseract", lambda: None)
    monkeypatch.setattr(ocr, "ocr_mask", lambda *_args, **_kwargs: "Start")

    match = _runner()._portal_start_button_by_text(1)

    assert match is not None
    assert 570 <= match["cx"] <= 810
    assert 490 <= match["cy"] <= 535


def test_green_activate_button_is_not_mistaken_for_start(monkeypatch):
    frame = np.zeros((756, 1152, 3), dtype=np.uint8)
    cv2.rectangle(frame, (570, 490), (810, 535), (25, 190, 35), -1)
    monkeypatch.setattr(vision, "capture_game_bgr", lambda _hwnd: frame)
    monkeypatch.setattr(ocr, "get_pytesseract", lambda: None)
    monkeypatch.setattr(ocr, "ocr_mask", lambda *_args, **_kwargs: "Activate Portal")

    assert _runner()._portal_start_button_by_text(1) is None


def test_party_confirmation_accepts_start_text_when_saved_images_miss(monkeypatch):
    runner = _runner()
    runner._portal_start_button_by_text = MagicMock(return_value={"cx": 690, "cy": 510})
    monkeypatch.setattr(vision, "find_image", lambda *_args, **_kwargs: None)

    assert runner._portal_anchor(1, ("portal_start", "portal_party"), 0,
                                 threading.Event()) == "portal_start_text"


def test_start_step_clicks_detected_button_instead_of_calibrated_point(monkeypatch):
    runner = _runner()
    runner._portal_anchor = MagicMock(return_value=None)
    runner._portal_start_button_by_text = MagicMock(return_value={
        "cx": 690, "cy": 510, "detector": "green_start_text"})
    monkeypatch.setattr(vision, "wait_for_image", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(vision, "click_match", MagicMock())
    runner._click_coord_point = MagicMock()

    assert runner._portal_step(1, threading.Event(), "portal_start", "portal_start",
                               "Starting the portal")
    vision.click_match.assert_called_once()
    runner._click_coord_point.assert_not_called()


def test_tab_change_is_confirmed_at_clicked_location(monkeypatch):
    runner = _runner()
    runner._portal_anchor = MagicMock(return_value=None)
    monkeypatch.setattr(vision, "wait_for_image", lambda *_args, **_kwargs: {
        "score": 0.83, "x": 200, "y": 220, "w": 100, "h": 30,
        "cx": 250, "cy": 235})
    colors = iter((0.0, 0.7))
    monkeypatch.setattr(vision, "portal_tab_blue_fraction", lambda *_args: next(colors))
    monkeypatch.setattr(vision, "click_match", MagicMock())
    monkeypatch.setattr("core.runner.wm.activate_window", lambda _hwnd: True)

    assert runner._portal_step(1, threading.Event(), "portal_tab", "portal_tab",
                               "Opening the Portals tab", ("portal_tab_selected",))
    vision.click_match.assert_called_once()
    assert runner._portal_anchor.call_count == 1


def test_activate_does_not_retry_old_point_after_screen_changes(monkeypatch):
    runner = _runner()
    runner._portal_anchor = MagicMock(return_value=None)
    monkeypatch.setattr(vision, "wait_for_image", lambda *_args, **_kwargs: {
        "score": 0.99, "cx": 700, "cy": 520})
    monkeypatch.setattr(vision, "find_image", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(vision, "click_match", MagicMock())
    monkeypatch.setattr("core.runner.wm.activate_window", lambda _hwnd: True)
    runner._click_coord_point = MagicMock()

    assert not runner._portal_step(1, threading.Event(), "portal_activate",
                                   "portal_activate", "Activating the portal",
                                   ("portal_start", "portal_party"))
    vision.click_match.assert_called_once()
    runner._click_coord_point.assert_not_called()
    assert any("Start button was not recognized" in call.args[0]
               for call in runner._log.call_args_list)
