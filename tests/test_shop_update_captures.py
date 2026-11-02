"""Exercise shop recognition against the user's Update 3 captures."""
from pathlib import Path
import threading
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from core import auto_shop, auto_shop_vision as av, image_io, vision
from core.runner import MacroRunner

CAPTURES = Path(auto_shop.ASSETS_DIR) / "reference/auto_shop/update_20261004"


def frame(number):
    return image_io.read_image(CAPTURES / f"shop_{number:02}.png")


def locate(image, key):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    match = vision.find_in_gray_multiscale(
        gray[218:580, 390:706], auto_shop.item_definition(key)["template"])
    assert match is not None, key
    for field in ("x", "cx"):
        match[field] += 390
    for field in ("y", "cy"):
        match[field] += 218
    return match


@pytest.mark.parametrize("number,key,button_y", [
    (1, "cursed_boba", 378), (1, "red_flower", 378),
    (3, "frown_fruit", 380), (3, "delicious_pie", 380),
    (2, "mana_flask", 381), (2, "meat", 381),
    (11, "survival_rations", 383), (11, "rice", 383),
    (12, "sprite_grey", 485),
    (10, "equipment_reroll", 486), (10, "equipment_lock", 486),
    (16, "stat_reroll", 523), (16, "stat_lock", 523),
])
def test_current_card_identity_and_own_buy(number, key, button_y):
    image = frame(number)
    match = locate(image, key)
    assert av.verify_card_identity(image, key, match)
    button = av.find_card_buy_button(image, match)
    assert button is not None
    assert button[1] == button_y
    assert abs(button[0] + button[2] / 2 - match["cx"]) < 25


def test_sold_out_trait_is_identified_without_green_buy(monkeypatch):
    image = frame(12)
    match = locate(image, "trait_crystal")
    assert av.verify_card_identity(image, "trait_crystal", match)
    assert av.find_card_buy_button(image, match) is None
    region = av.card_terminal_region_from_item_match(match)
    crop = av.crop_region(image, region)
    assert vision.find_in_gray_multiscale(
        cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), "shop_out_of_stock")
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    monkeypatch.setattr(runner, "_checkpoint", lambda _stop: False)
    monkeypatch.setattr(vision, "capture_game_bgr", lambda *_args: image)
    assert runner._shop_find_visible_item(
        1, {"key": "trait_crystal"}, threading.Event()) == match


def test_card_can_move_columns_and_rows_without_new_references():
    source = frame(1)
    moved = np.zeros_like(source)
    moved[330:520, 547:684] = source[225:415, 399:536]
    match = locate(moved, "cursed_boba")
    assert match["cx"] > 600
    assert av.verify_card_identity(moved, "cursed_boba", match)
    assert av.find_card_buy_button(moved, match) == (552, 483, 128, 34)
    assert not av.verify_card_identity(moved, "red_flower", match)


@pytest.mark.parametrize("number,toggle", [(15, "shop_amount_max"), (13, "shop_amount_min")])
def test_quantity_controls_and_confirmation_button(number, toggle):
    image = frame(number)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    cancel = vision.find_in_gray_multiscale(gray, "shop_cancel")
    assert cancel is not None
    assert av.amount_input_region_from_cancel(cancel) == (394, 374, 48, 29)
    toggle_crop = av.crop_region(image, av.amount_toggle_region_from_cancel(cancel))
    assert vision.find_in_gray_multiscale(cv2.cvtColor(toggle_crop, cv2.COLOR_BGR2GRAY), toggle)
    buy = av.find_modal_buy_button(image, cancel)
    assert buy is not None and buy[0] < cancel["x"]
    assert vision.find_in_gray_multiscale(gray, "shop_purchase_modal")


def test_scan_rechecks_after_a_transient_missed_capture(monkeypatch):
    image = frame(12)
    frames = iter([np.zeros_like(image), image])
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    capture = MagicMock(side_effect=lambda *_args: next(frames))
    monkeypatch.setattr(vision, "capture_game_bgr", capture)
    monkeypatch.setattr(runner, "_checkpoint", lambda _stop: False)
    monkeypatch.setattr("core.runner_shop.time.sleep", lambda _seconds: None)
    assert runner._shop_find_visible_item(
        1, {"key": "trait_crystal", "name": "Trait Crystal"}, threading.Event())
    assert capture.call_count == 2


def test_scrollbar_signature_ignores_animated_item_art(monkeypatch):
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    first = frame(1)
    changed = first.copy()
    changed[225:570, 399:684] = 255 - changed[225:570, 399:684]
    current = [first]
    monkeypatch.setattr(vision, "capture_game_bgr", lambda _hwnd, region: av.crop_region(current[0], region))
    signature = runner._shop_discovery_signature(1)
    current[0] = changed
    assert runner._shop_discovery_signature(1) == signature
    current[0] = frame(12)
    assert runner._shop_discovery_signature(1) != signature
