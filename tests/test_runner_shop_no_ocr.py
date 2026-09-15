import threading
from unittest.mock import MagicMock

import numpy as np
import pytest

from core import auto_shop
from core import runner_shop
from core.runner import MacroRunner


def _runner(saved_items):
    return MacroRunner(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        save_auto_shop_item_state=lambda shop, item, state: saved_items.append(
            (shop, item, state)
        ),
    )


def _item(target=5):
    return {
        "key": "cursed_boba",
        "name": "Cursed Boba",
        "daily_maximum": 50,
        "target": target,
        "state": auto_shop.fresh_item_state("2026-07-30"),
    }


def test_visible_numeric_purchase_remains_due_without_reading_stock(monkeypatch):
    """A numeric purchase must repeat on later passes until the card is terminal."""
    saved_items = []
    runner = _runner(saved_items)
    cancel = {"x": 579, "y": 420, "w": 181, "h": 28}
    item = _item(target=5)
    runner._shop_read_observation = MagicMock(
        side_effect=AssertionError("The no-OCR path must not read stock")
    )
    monkeypatch.setattr(runner, "_shop_find_terminal_label", lambda *_args: None)
    monkeypatch.setattr(runner, "_shop_open_purchase_modal", lambda *_args: cancel)
    monkeypatch.setattr(runner, "_shop_configure_amount", lambda *_args: True)
    monkeypatch.setattr(runner, "_shop_confirm_purchase", lambda *_args: True)

    runner._shop_process_visible_item(
        1,
        "gold_shop",
        item,
        {"x": 429, "y": 245, "w": 61, "h": 55},
        threading.Event(),
    )

    runner._shop_read_observation.assert_not_called()
    assert saved_items[-1][2]["status"] == auto_shop.STATUS_RETRY_PENDING
    assert saved_items[-1][2]["verification"] is None


def test_visible_max_purchase_is_completed_for_the_current_day(monkeypatch):
    saved_items = []
    runner = _runner(saved_items)
    cancel = {"x": 579, "y": 420, "w": 181, "h": 28}
    item = _item(target="max")
    monkeypatch.setattr(runner, "_shop_find_terminal_label", lambda *_args: None)
    monkeypatch.setattr(runner, "_shop_open_purchase_modal", lambda *_args: cancel)
    monkeypatch.setattr(runner, "_shop_configure_amount", lambda *_args: True)
    monkeypatch.setattr(runner, "_shop_confirm_purchase", lambda *_args: True)

    runner._shop_process_visible_item(
        1,
        "gold_shop",
        item,
        {"x": 429, "y": 245, "w": 61, "h": 55},
        threading.Event(),
    )

    assert saved_items[-1][2]["status"] == auto_shop.STATUS_COMPLETED


def test_visible_purchase_with_uncertain_modal_requires_a_manual_today_reset(monkeypatch):
    """A final Buy that does not close must not restart the shop every task."""
    saved_items = []
    runner = _runner(saved_items)
    cancel = {"x": 579, "y": 420, "w": 181, "h": 28}
    item = _item(target="max")
    monkeypatch.setattr(runner, "_shop_find_terminal_label", lambda *_args: None)
    monkeypatch.setattr(runner, "_shop_open_purchase_modal", lambda *_args: cancel)
    monkeypatch.setattr(runner, "_shop_configure_amount", lambda *_args: True)
    monkeypatch.setattr(runner, "_shop_confirm_purchase", lambda *_args: False)

    runner._shop_process_visible_item(
        1,
        "gold_shop",
        item,
        {"x": 429, "y": 245, "w": 61, "h": 55},
        threading.Event(),
    )

    assert saved_items[-1][2]["status"] == auto_shop.STATUS_FAILED_TODAY


def test_auto_shop_run_delegates_enabled_items_to_the_no_ocr_sweep(monkeypatch):
    """The public runner path must not retain the old OCR item processor."""
    item = _item()
    item["enabled"] = True
    settings = {
        "enabled": True,
        "shops": {
            "gold_shop": {
                "enabled": True,
                "state": auto_shop.fresh_shop_state("2026-07-30"),
                "items": [item],
            },
        },
    }
    runner = MacroRunner(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        get_auto_shop_settings=lambda: settings,
    )
    runner._recover_to_lobby = MagicMock()
    dispatched = []
    monkeypatch.setattr("core.runner_shop.wm.show_window", lambda _hwnd: None)
    monkeypatch.setattr("core.runner_shop.wm.activate_window", lambda _hwnd: True)
    monkeypatch.setattr(runner, "_ensure_lobby", lambda *_args: True)
    monkeypatch.setattr(runner, "_shop_enter_gold_shop", lambda *_args: True)
    monkeypatch.setattr(
        runner,
        "_shop_run_no_ocr_sweep",
        lambda _hwnd, shop, items, _stop: dispatched.append((shop, items)),
    )
    runner._shop_process_item = MagicMock(
        side_effect=AssertionError("The OCR processor must not run")
    )
    monkeypatch.setattr("core.runner_shop.vision.find_image", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("core.runner_shop.time.sleep", lambda _seconds: None)

    runner._run_auto_shop(1, threading.Event())

    assert dispatched == [("gold_shop", [item])]


def test_open_modal_clicks_the_green_buy_region_without_matching_a_price(monkeypatch):
    """Price artwork must not decide whether a known card Buy can be clicked."""
    runner = _runner([])
    item_match = {"x": 429, "y": 245, "w": 61, "h": 55}
    cancel = {"x": 579, "y": 420, "w": 181, "h": 28}
    monkeypatch.setattr("core.runner_shop.vision.wait_for_image_any", lambda *_a, **_k: (cancel, "shop_cancel"))
    clicked = []
    monkeypatch.setattr(
        "core.runner_shop.vision.capture_game_bgr",
        lambda *_args, **_kwargs: np.full((43, 142, 3), (0, 255, 70), dtype=np.uint8),
    )
    monkeypatch.setattr(
        "core.runner_shop.vision.find_color_run",
        lambda *_args, **_kwargs: pytest.fail("Text must not break a total-color check"),
    )
    monkeypatch.setattr(
        "core.runner_shop.vision.wait_for_image",
        lambda _hwnd, name, **_kwargs: cancel if name == "shop_cancel" else pytest.fail(
            "A dynamic Buy price must not be searched"
        ),
    )
    monkeypatch.setattr(
        "core.runner_shop.vision.click_match",
        lambda _mouse, _hwnd, match: clicked.append(match),
    )

    assert runner._shop_open_purchase_modal(1, item_match, threading.Event()) == cancel
    assert clicked == [
        {"x": 391, "y": 382, "w": 140, "h": 42, "cx": 461, "cy": 403},
    ]


def test_max_amount_checks_max_and_min_templates_before_clicking(monkeypatch):
    """Verify that Max toggle checks template states before clicking to avoid buying 1 instead of Max."""
    runner = _runner([])
    cancel = {"x": 579, "y": 420, "w": 181, "h": 28}
    monkeypatch.setattr(
        "core.runner_shop.vision.find_image",
        lambda _hwnd, name, **_kwargs: (
            {"x": 710, "y": 374, "w": 43, "h": 22}
            if name == "shop_amount_max" else None
        ),
    )
    monkeypatch.setattr(
        "core.runner_shop.vision.ref_to_screen",
        lambda _hwnd, x, y: (x, y),
    )

    assert runner._shop_configure_amount(1, cancel, "max", 50, threading.Event()) is True
    runner._mouse.click.assert_called_once_with(734, 388)


def test_modal_close_requires_consecutive_clear_checks(monkeypatch):
    runner = _runner([])
    cancel = {"x": 579, "y": 420, "w": 181, "h": 28}
    # One transient miss is followed by the modal being visible again.  Only
    # the final three clear observations may confirm closure.
    cancel_results = iter([None, cancel, None, None, None])

    def find_image(_hwnd, name, **_kwargs):
        if name == "shop_cancel":
            return next(cancel_results)
        return None

    monkeypatch.setattr("core.runner_shop.vision.find_image", find_image)
    monkeypatch.setattr("core.runner_shop.time.sleep", lambda _seconds: None)
    monkeypatch.setattr(runner, "_checkpoint", lambda _stop: False)

    assert runner._shop_wait_for_modal_closed(1, threading.Event()) is True


def test_modal_close_is_not_confirmed_when_no_template_can_be_checked(monkeypatch):
    runner = _runner([])
    times = iter([0.0, 0.0, 0.5, 1.0, 5.1])
    monkeypatch.setattr("core.runner_shop.time.time", lambda: next(times))
    monkeypatch.setattr("core.runner_shop.time.sleep", lambda _seconds: None)
    monkeypatch.setattr(runner, "_checkpoint", lambda _stop: False)
    monkeypatch.setattr(
        "core.runner_shop.vision.find_image",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            runner_shop.vision.TemplateNotFound("missing")
        ),
    )

    assert runner._shop_wait_for_modal_closed(1, threading.Event()) is False


def test_dynamic_sweep_resets_once_and_stops_at_the_physical_list_end(monkeypatch):
    runner = _runner([])
    items = [_item(), {**_item(), "key": "red_flower", "name": "Red Flower", "daily_maximum": 75}]
    found = []
    processed = []
    signatures = iter([b"top", b"middle", b"bottom", b"bottom"])
    monkeypatch.setattr(runner, "_checkpoint", lambda _stop: False)
    monkeypatch.setattr(runner, "_shop_discovery_signature", lambda _hwnd: next(signatures))
    monkeypatch.setattr(
        runner,
        "_shop_find_visible_item",
        lambda _hwnd, item, _stop: found.append(item["key"]) or (
            {"x": 429, "y": 325, "w": 61, "h": 55}
            if item["key"] == "red_flower" and found.count("red_flower") == 2 else None
        ),
    )
    monkeypatch.setattr(
        runner, "_shop_process_visible_item",
        lambda _hwnd, _shop, item, _match, _stop: processed.append(item["key"]),
    )
    # This test isolates dynamic list-end detection; terminal fallback has a
    # dedicated test below.
    monkeypatch.setattr(runner, "_shop_move_to_scroll_position", lambda *_args: False)
    monkeypatch.setattr("core.runner_shop.vision.ref_to_screen", lambda _hwnd, x, y: (x, y))
    monkeypatch.setattr("core.runner_shop.time.sleep", lambda _seconds: None)

    runner._shop_run_no_ocr_sweep(1, "gold_shop", items, threading.Event())

    assert processed == ["red_flower"]
    assert [call.args for call in runner._mouse.scroll.call_args_list] == [
        (runner_shop.SHOP_SCROLL_RESET_AMOUNT,),
        (runner_shop.SHOP_DISCOVERY_SCROLL_AMOUNT,),
        (runner_shop.SHOP_DISCOVERY_SCROLL_AMOUNT,),
    ]


def test_dynamic_sweep_keeps_unlocated_item_pending_without_a_fallback_click(monkeypatch):
    saved_items = []
    runner = _runner(saved_items)
    monkeypatch.setattr(runner, "_checkpoint", lambda _stop: False)
    monkeypatch.setattr(runner, "_shop_discovery_signature", lambda _hwnd: b"same")
    monkeypatch.setattr(runner, "_shop_find_visible_item", lambda *_args: None)
    monkeypatch.setattr(runner, "_shop_move_to_scroll_position", lambda *_args: True)
    monkeypatch.setattr(runner, "_shop_find_slot_out_of_stock", lambda *_args: False)
    runner._shop_try_fallback_modal = MagicMock(
        side_effect=AssertionError("dynamic discovery must not manufacture a card match")
    )
    monkeypatch.setattr("core.runner_shop.vision.ref_to_screen", lambda _hwnd, x, y: (x, y))
    monkeypatch.setattr("core.runner_shop.time.sleep", lambda _seconds: None)

    runner._shop_run_no_ocr_sweep(1, "gold_shop", [_item()], threading.Event())

    runner._shop_try_fallback_modal.assert_not_called()
    assert saved_items[-1][2]["status"] == auto_shop.STATUS_PENDING_NOT_LOCATED


def test_dynamic_sweep_recognizes_sold_out_card_when_its_icon_is_hidden(monkeypatch):
    saved_items = []
    runner = _runner(saved_items)
    item = _item()
    monkeypatch.setattr(runner, "_checkpoint", lambda _stop: False)
    monkeypatch.setattr(runner, "_shop_discovery_signature", lambda _hwnd: b"same")
    monkeypatch.setattr(runner, "_shop_find_visible_item", lambda *_args: None)
    moved_to = []
    monkeypatch.setattr(
        runner,
        "_shop_move_to_scroll_position",
        lambda _hwnd, amount, _stop: moved_to.append(amount) or True,
    )
    monkeypatch.setattr(runner, "_shop_find_slot_out_of_stock", lambda *_args: True)
    runner._shop_try_fallback_modal = MagicMock(
        side_effect=AssertionError("sold-out fallback must never attempt a Buy")
    )
    monkeypatch.setattr("core.runner_shop.vision.ref_to_screen", lambda _hwnd, x, y: (x, y))
    monkeypatch.setattr("core.runner_shop.time.sleep", lambda _seconds: None)

    runner._shop_run_no_ocr_sweep(1, "gold_shop", [item], threading.Event())

    assert moved_to == [runner_shop.SHOP_ITEM_SCROLL_AMOUNTS[item["key"]]]
    assert saved_items[-1][2]["status"] == auto_shop.STATUS_OUT_OF_STOCK
    runner._shop_try_fallback_modal.assert_not_called()
