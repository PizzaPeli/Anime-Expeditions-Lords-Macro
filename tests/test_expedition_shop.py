"""Regressions for the independent coin shop and later-round placements."""
from pathlib import Path
import threading
from unittest.mock import MagicMock

import cv2
import pytest

from core import auto_shop, auto_shop_vision, runner_shop, settings, vision
from core.runner import MacroRunner
from main import Api

CAPTURES = Path(__file__).resolve().parents[1] / "Assets/reference/auto_shop/expedition_20261101"


def capture(stamp):
    frame = cv2.imread(str(CAPTURES / f"screen_manual_20261101_{stamp}.png"))
    assert frame is not None
    return frame


def test_old_settings_migrate_and_shops_stay_independent(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    settings.update({"auto_shop": {"enabled": True, "shops": {"gold_shop": {
        "enabled": True, "items": {"stat_lock": {"enabled": True, "target": 3}}
    }}}})
    api = object.__new__(Api)
    current = api.get_auto_shop_settings()
    assert not current["shops"]["expedition_shop"]["enabled"]
    assert len(current["shops"]["expedition_shop"]["items"]) == 8
    assert all("payload" not in item["key"] for item in current["shops"]["expedition_shop"]["items"])
    assert api.set_auto_shop_shop_enabled("expedition_shop", True)["ok"]
    assert api.set_auto_shop_item_enabled("expedition_shop", "exp_stat_lock", True)["ok"]
    assert api.set_auto_shop_item_target("expedition_shop", "exp_stat_lock", "max")["ok"]
    assert not api.set_auto_shop_item_enabled("expedition_shop", "stat_lock", True)["ok"]
    assert api.set_auto_shop_view("squares")["ok"]
    reloaded = object.__new__(Api).get_auto_shop_settings()
    assert reloaded["view"] == "squares"
    gold = next(item for item in reloaded["shops"]["gold_shop"]["items"] if item["key"] == "stat_lock")
    assert gold["target"] == 3 and gold["enabled"]
    exp = next(item for item in reloaded["shops"]["expedition_shop"]["items"] if item["key"] == "exp_stat_lock")
    assert exp["target"] == "max" and exp["enabled"] and exp["icon"].startswith("data:image/png;base64,")


@pytest.mark.parametrize("key,stamp", [
    ("gem", "144746"), ("gold", "144746"), ("stat_lock", "144746"),
    ("stat_reroll", "144746"), ("trait_crystal", "144750"),
    ("enhanced_katana", "144750"), ("equipment_reroll", "144750"),
    ("equipment_lock", "144750"),
])
def test_coin_item_identity_and_own_buy_button(monkeypatch, key, stamp):
    frame = capture(stamp)
    key = "exp_" + key
    definition = auto_shop.item_definition(key)
    match = vision.find_in_gray_multiscale(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), definition["template"])
    assert match is not None
    assert auto_shop_vision.verify_card_identity(frame, key, match)
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    runner._active_shop_key = "expedition_shop"
    monkeypatch.setattr(runner, "_checkpoint", lambda event: event.is_set())
    monkeypatch.setattr(vision, "capture_game_bgr", lambda *_a, **_k: frame)
    monkeypatch.setattr(runner_shop.time, "sleep", lambda _s: None)
    found = runner._shop_find_visible_item(1, {"key": key, "name": definition["name"]}, threading.Event())
    assert found is not None
    if key != "exp_trait_crystal":
        button = auto_shop_vision.find_card_buy_button(frame, found)
        assert button is not None
        assert runner._shop_region_is_visible(button, shop_key="expedition_shop")
        assert abs(button[0] + button[2] // 2 - match["cx"]) < 20


def test_remote_expedition_navigation_uses_own_card_and_header(monkeypatch):
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    state = ["144737"]
    monkeypatch.setattr(runner, "_checkpoint", lambda stop: stop.is_set())
    monkeypatch.setattr(runner_shop.time, "sleep", lambda _s: None)
    monkeypatch.setattr(vision, "ref_to_screen", lambda _hwnd, x, y: (x, y))

    def find(_hwnd, name, region=None, **_kwargs):
        frame = capture(state[0])
        if region:
            x, y, w, h = region
            frame = frame[y:y+h, x:x+w]
        match = vision.find_in_gray_multiscale(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), name)
        if match and region:
            for field in ("x", "cx"):
                match[field] += region[0]
            for field in ("y", "cy"):
                match[field] += region[1]
        return match

    def click(x, y):
        assert 552 <= x <= 629 and 365 <= y <= 394  # Open, never Buy All
        state[0] = "144746"

    monkeypatch.setattr(vision, "find_image", find)
    monkeypatch.setattr(vision, "wait_for_image", find)
    runner._click_found_image = lambda hwnd, name, _timeout, _stop, **kw: find(hwnd, name, **kw)
    runner._mouse.click.side_effect = click
    assert runner._shop_enter_remote_shop(1, threading.Event(), "expedition_shop")
    assert state[0] == "144746"
    assert runner._shop_enter_remote_shop(1, threading.Event(), "expedition_shop")
    assert runner._mouse.click.call_count == 1


def test_scheduler_includes_expedition_only_and_visits_both_shops(monkeypatch):
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    data = {"enabled": True, "shops": {
        "gold_shop": {"enabled": False, "items": []},
        "expedition_shop": {"enabled": True, "items": [{"key": "exp_gem", "enabled": True, "state": {"status": "pending"}}]},
    }}
    monkeypatch.setattr(runner, "_auto_shop_settings", lambda: data)
    assert runner._auto_shop_wants_in()
    calls = []
    monkeypatch.setattr(runner, "_run_auto_shop_for_shop", lambda _h, _s, key: calls.append(key))
    runner._run_auto_shop_if_due(1, threading.Event())
    assert calls == ["gold_shop", "expedition_shop"]
    assert runner._active_shop_key == "gold_shop"


def test_later_start_popup_replays_once_then_rearms(monkeypatch):
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    runner._battle_replayed = True  # initial Start Game still visible
    runner._battle_block_index = 9
    popup = [True]
    monkeypatch.setattr(runner, "_find_start_game_button", lambda *_a: ("nav_start_game", {"score": 1} if popup[0] else None))
    monkeypatch.setattr(runner, "_debug_save", lambda *_a: None)
    monkeypatch.setattr(runner, "_note_checkpoint_intercepted", lambda: None)
    monkeypatch.setattr(runner, "_dismiss_reward_card_if_found", lambda *_a: False)
    monkeypatch.setattr(vision, "click_match", lambda *_a: None)
    monkeypatch.setattr(vision, "find_image", lambda *_a, **_k: None)
    from core import runner_expedition
    monkeypatch.setattr(runner_expedition.wm, "get_window_rect_screen", lambda *_a: (0, 0, 1152, 756))
    monkeypatch.setattr(runner_expedition.time, "sleep", lambda _s: None)
    monkeypatch.setattr(runner, "_check_expedition_checkpoint_by_color", lambda *_a: None)
    runner._expedition_color_buttons = True
    for _round in range(3):
        runner._check_expedition_wave_result(1, threading.Event())
        assert runner._battle_block_index == 9  # same popup never restarts
        popup[0] = False
        runner._check_expedition_wave_result(1, threading.Event())
        assert runner._battle_block_index == 9  # ordinary play never restarts
        popup[0] = True
        runner._check_expedition_wave_result(1, threading.Event())
        assert runner._battle_block_index == 0
        runner._battle_block_index = 9
