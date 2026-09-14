import threading
from unittest.mock import MagicMock

import pytest
from core.runner import MacroRunner
from core import keys, auto_shop, auto_shop_vision


@pytest.mark.parametrize(
    'screen,search_point,first_slot',
    [('lobby', (460, 180), (387, 247)), ('chooser', (506, 187), (294, 254))],
)
def test_portal_search_selects_first_result_before_confirm(
        monkeypatch, screen, search_point, first_slot):
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    runner._hover_click = MagicMock()
    runner._interruptible_sleep = MagicMock()
    runner._checkpoint = lambda _stop: False
    monkeypatch.setattr('core.runner.vision.ref_to_screen', lambda _hwnd, x, y: (x, y))
    task = {'portal_name': 'Summer', 'portal_priority': ['Old Portal']}
    assert runner._scan_for_portal(1, threading.Event(), task, screen) == first_slot
    assert [call.args for call in runner._hover_click.call_args_list] == [
        (search_point[0], search_point[1], 1),
        (first_slot[0], first_slot[1], 1),
    ]
    runner._keyboard.combo.assert_called_once_with(keys.VK_CONTROL, ord('A'))
    runner._keyboard.type_text.assert_called_once_with('Summer')


@pytest.mark.parametrize('macro,want_on', [('', True), ('Farm', False)])
def test_autoplay_ignores_old_toggle_and_follows_macro(macro, want_on):
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    runner._ensure_autoplay = MagicMock(return_value=True)
    stop = threading.Event()
    assert runner._settle_autoplay_for_match(1, stop, {
        'mode': 'story', 'macro': macro, 'auto_play': 'macro' if want_on else 'autoplay',
    })
    runner._ensure_autoplay.assert_called_once_with(1, stop, want_on)


def test_autoplay_click_uses_located_button_and_hover(monkeypatch):
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    runner._autoplay_state = MagicMock(side_effect=['off', 'on'])
    runner._click_found_image = MagicMock(return_value={'score': 0.86})
    runner._interruptible_sleep = MagicMock()
    stop = threading.Event()

    assert runner._ensure_autoplay(1, stop, True)
    runner._click_found_image.assert_called_once_with(
        1, 'autoplay_off', 8.0, stop, shuffle=True, threshold=0.80)


def test_unknown_card_identity_never_authorizes_buy(monkeypatch):
    import numpy as np
    monkeypatch.setattr(auto_shop_vision, '_identity_references', lambda _key: [])
    assert not auto_shop_vision.verify_card_identity(
        np.zeros((756, 1152, 3), dtype=np.uint8), 'new_item',
        {'x': 429, 'y': 325, 'w': 61, 'h': 55})


def test_unlocated_state_resets_on_next_day():
    state = auto_shop.mark_item_not_located(None, '2026-09-12')
    assert state['status'] == auto_shop.STATUS_PENDING_NOT_LOCATED
    assert auto_shop.normalize_item_state(state, '2026-09-13')['status'] == auto_shop.STATUS_PENDING
