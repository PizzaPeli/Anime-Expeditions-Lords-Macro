"""Replay remote navigation and item recognition against real captures."""
from pathlib import Path
import threading
from unittest.mock import MagicMock

import cv2
import pytest

from core import auto_shop, auto_shop_vision, runner_shop, vision
from core.runner import MacroRunner

CAPTURES = Path(__file__).resolve().parents[1] / "Assets/reference/auto_shop/remote_20261031"


def capture(stamp):
    frame = cv2.imread(str(CAPTURES / f"screen_manual_20261031_{stamp}.png"))
    assert frame is not None
    return frame


@pytest.mark.parametrize("initial", ["142647", "142652", "142701", "142709", "142814"])
def test_remote_navigation_from_each_screen(monkeypatch, initial):
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    state = [initial]
    clicks = []
    monkeypatch.setattr(runner, "_checkpoint", lambda stop: stop.is_set())
    monkeypatch.setattr(runner_shop.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(vision, "ref_to_screen", lambda _hwnd, x, y: (x, y))

    def find(_hwnd, name, region=None, **_kwargs):
        frame = capture(state[0])
        if region:
            x, y, w, h = region
            frame = frame[y:y + h, x:x + w]
        match = vision.find_in_gray_multiscale(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), name)
        if match and region:
            for field in ("x", "cx"):
                match[field] += region[0]
            for field in ("y", "cy"):
                match[field] += region[1]
        return match

    def click(x, y):
        clicks.append((x, y))
        if state[0] == "142647":
            assert 225 <= x <= 248 and 23 <= y <= 46
            state[0] = "142652"
        elif state[0] == "142652":
            assert 237 <= x <= 353 and 186 <= y <= 214
            state[0] = "142701"
        elif state[0] == "142701":
            assert 228 <= x <= 331 and 342 <= y <= 372
            state[0] = "142709"
        elif state[0] == "142709":
            if 228 <= x <= 331 and 342 <= y <= 372:
                return
            # Require Gold Shop's Open Shop, not Buy All or another shop.
            assert 735 <= x <= 811 and 366 <= y <= 393
            state[0] = "142814"
        else:
            pytest.fail("Already-open Gold Shop should not be clicked")

    def click_found(hwnd, name, _timeout, stop, **kwargs):
        if stop.is_set():
            return None
        match = find(hwnd, name, **kwargs)
        if match:
            click(match["cx"], match["cy"])
        return match

    monkeypatch.setattr(vision, "find_image", find)
    monkeypatch.setattr(vision, "wait_for_image", find)
    monkeypatch.setattr(runner, "_click_found_image", click_found)
    runner._mouse.click.side_effect = click
    assert runner._shop_enter_gold_shop(1, threading.Event())
    assert state[0] == "142814"
    runner._keyboard.tap.assert_not_called()
    if initial == "142814":
        assert not clicks


@pytest.mark.parametrize("key", ["cursed_boba", "red_flower"])
def test_existing_item_and_buy_controls_on_remote_screen(key):
    frame = capture("142814")
    definition = auto_shop.item_definition(key)
    match = vision.find_in_gray_multiscale(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), definition["template"])
    assert match is not None
    assert auto_shop_vision.verify_card_identity(frame, key, match)
    region = auto_shop_vision.find_card_buy_button(frame, match)
    assert region is not None
    assert runner_shop.ShopOps._shop_region_is_visible(region)
    x, y, width, height = region
    expected_x = (403, 532) if key == "cursed_boba" else (550, 680)
    assert expected_x[0] <= x + width // 2 <= expected_x[1]
    assert 409 <= y + height // 2 <= 443


@pytest.mark.parametrize("failure", ["cancel", "menu_missing", "card_missing", "header_missing", "clipped"])
def test_failed_remote_navigation_never_purchases(monkeypatch, failure):
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    stop = threading.Event()
    if failure == "cancel":
        stop.set()
    monkeypatch.setattr(runner, "_checkpoint", lambda event: event.is_set())
    monkeypatch.setattr(runner_shop.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(vision, "find_image", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(vision, "ref_to_screen", lambda _hwnd, x, y: (x, y))
    runner._click_found_image = MagicMock(return_value=None if failure == "menu_missing" else {"score": 1})

    def wait(_hwnd, name, **_kwargs):
        if name == "shop_remote_gold_card":
            if failure == "card_missing":
                return None
            return {"x": 737, "y": 550 if failure == "clipped" else 214}
        return None

    monkeypatch.setattr(vision, "wait_for_image", wait)
    assert not runner._shop_enter_gold_shop(1, stop)
    if failure != "header_missing":
        runner._mouse.click.assert_not_called()
    runner._keyboard.tap.assert_not_called()
