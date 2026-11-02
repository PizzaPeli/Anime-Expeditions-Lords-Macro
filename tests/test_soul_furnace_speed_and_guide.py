import ast
import base64
from pathlib import Path
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np

from core import runner_soul_furnace as soul
from core.runner import MacroRunner


ROOT = Path(__file__).resolve().parents[1]


def test_result_search_reuses_one_capture_for_all_result_labels(monkeypatch):
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    frame = np.zeros((756, 1152, 3), dtype=np.uint8)
    capture = MagicMock(return_value=frame)
    monkeypatch.setattr(soul.vision, "capture_game_bgr", capture)
    runner._soul_find = MagicMock(return_value=None)
    assert runner._soul_result(123) is None
    capture.assert_called_once()
    assert len(runner._soul_find.call_args_list) == 3
    assert all(call.kwargs["frame"] is frame for call in runner._soul_find.call_args_list)


def test_snapshot_match_keeps_absolute_game_coordinates(monkeypatch):
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    frame = np.zeros((756, 1152, 3), dtype=np.uint8)
    match = dict(x=50, y=60, cx=70, cy=80, w=40, h=40, score=1.0)
    monkeypatch.setattr(soul.vision, "find_in_gray_multiscale", lambda *_args, **_kw: match)
    capture = MagicMock()
    monkeypatch.setattr(soul.vision, "capture_game_bgr", capture)
    result = runner._soul_find(123, "item", region=(235, 215, 665, 365), frame=frame)
    assert (result["x"], result["y"], result["cx"], result["cy"]) == (285, 275, 305, 295)
    assert match["x"] == 50  # cached match dictionaries must remain unchanged
    capture.assert_not_called()


def test_captured_boss_purchase_uses_three_frames_and_still_confirms_forging(monkeypatch):
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    runner._checkpoint = MagicMock(return_value=False)
    runner._release_quick_place_shift = MagicMock()
    runner._soul_result = MagicMock(return_value=None)
    runner._soul_click = MagicMock()
    runner._interruptible_sleep = MagicMock()
    frames = []
    for name in ("before", "after"):
        frame = np.zeros((756, 1152, 3), dtype=np.uint8)
        frame[170:584, 235:925] = cv2.imread(str(ROOT / f"Assets/reference/soul_furnace/boss_shop_{name}.png"))
        frames.append(frame)
    before, after = frames
    top = before.copy()
    top[215:580, 235:900] = 0  # item is below the current shop viewport
    capture = MagicMock(side_effect=[top, before, before, after])
    monkeypatch.setattr(soul.vision, "capture_game_bgr", capture)
    monkeypatch.setattr(soul.vision, "ref_to_screen", lambda hwnd, x, y: (x, y))
    original = runner._soul_find
    def find(hwnd, name, region=None, frame=None):
        if frame is None:
            assert name == "soul_forge"
            return {"score": 1.0}
        return original(hwnd, name, region=region, frame=frame)
    runner._soul_find = find
    assert runner._soul_purchase_attempt(123, threading.Event(), "final_boss")
    assert capture.call_count == 4  # scroll, locate, stable position, purchase
    runner._soul_result.assert_called_once_with(123)
    assert any(call.args == (-240,) for call in runner._mouse.scroll.call_args_list)
    assert runner._mouse.nudge.call_count >= 2
    buy = runner._soul_click.call_args.args
    assert 280 <= buy[1] <= 418 and 460 <= buy[2] <= 500
    assert soul.SHOP_SCROLL_SETTLE == 0.1
    assert soul.SHOP_CONFIRM_INTERVAL == 0.1
    assert soul.SOUL_POLL_INTERVAL == 0.2
    assert soul.PURCHASE_RETRY_SECONDS == 3.0


def test_recommendation_api_returns_the_creator_screenshots():
    path = ROOT / "main.py"
    module = ast.parse(path.read_text(encoding="utf-8"))
    api = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == "Api")
    method = next(n for n in api.body if isinstance(n, ast.FunctionDef) and n.name == "get_soul_furnace_recommendation")
    import os
    env = dict(os=os, constants=SimpleNamespace(ASSETS_DIR=str(ROOT / "Assets")))
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), "exec"), env)
    result = env[method.name](None)
    for key in ("team", "autoplay"):
        prefix, encoded = result[key].split(",", 1)
        assert prefix == "data:image/png;base64"
        original = (ROOT / f"Assets/reference/soul_furnace/recommended_{key}.png").read_bytes()
        assert base64.b64decode(encoded) == original
