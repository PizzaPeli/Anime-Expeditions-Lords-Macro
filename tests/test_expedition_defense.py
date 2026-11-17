"""Defense coordinates must never run against the assault/cart camera."""
from pathlib import Path
import threading
from unittest.mock import MagicMock

import numpy as np
import pytest

from core import expedition_vision as ev
from core import runner_expedition as rx
from core import runner_blocks as rb
from core.image_io import read_image
from core.runner import MacroRunner


FIXTURES = Path(__file__).parent / 'fixtures/expedition'


def frame(name, unit=None):
    image = np.zeros((756, 1152, 3), dtype=np.uint8)
    hud = read_image(FIXTURES / f'{name}_hud.png')
    image[:hud.shape[0]] = hud
    if unit is not None:
        image[240:510, :390] = read_image(FIXTURES / f'unit_{unit}.png')
    return image


@pytest.mark.parametrize('name,expected', [('assault', False), ('setup', False),
                                         ('defense', True), ('defense_flower', True),
                                         ('elite', True)])
def test_stage_from_independent_captures(name, expected):
    assert ev.is_defense(frame(name)) is expected


def test_future_shield_is_not_the_current_node():
    image = frame('assault')
    shield = frame('defense')[60:87, 417:445].copy()
    image[60:87, 617:645] = shield
    assert not ev.is_defense(image)


@pytest.mark.parametrize('state', range(7))
def test_individual_panel_and_blue_priority_from_captures(state):
    image = frame('setup', 'off' if state == 0 else str(state))
    panel = ev.selected_unit(image)
    assert panel is not None
    assert ev.auto_upgrade_state(image, panel) == state
    assert panel['button'] == (346, 454)
    assert panel['close'] == (368, 262)


def test_empty_cargo_is_not_a_selected_unit():
    assert ev.selected_unit(frame('defense')) is None


@pytest.mark.parametrize('unit,state,x', [(0, 0, 301), (1, 0, 301), (2, 0, 301),
                                         (3, 4, 346), (4, 0, 301), (5, 0, 346)])
def test_macro2_all_six_actual_unit_panels(unit, state, x):
    image = frame('setup', f'macro2_{unit}')
    panel = ev.selected_unit(image)
    assert panel is not None
    assert panel['button'] == (x, 454)
    assert ev.auto_upgrade_state(image, panel) == state


@pytest.mark.parametrize('state', range(1, 7))
@pytest.mark.parametrize('offset', [-3, -2, 0, 2, 3])
def test_numbered_priority_in_left_control(state, offset):
    image = frame('setup', 'off')
    source = frame('setup', str(state))
    image[448:463, 337:355] = 0  # extra ability must not be selected
    image[448:463, 292+offset:310+offset] = source[448:463, 337:355]
    panel = ev.selected_unit(image)
    assert panel['button'] == (301, 454)
    assert ev.auto_upgrade_state(image, panel) == state


@pytest.mark.parametrize('state', range(7))
def test_priority_reference_survives_dimmer_lighting(state):
    image = frame('setup', 'off' if state == 0 else str(state))
    image = (image.astype(float)*0.65).astype(np.uint8)
    panel = ev.selected_unit(image)
    assert panel is not None
    assert ev.auto_upgrade_state(image, panel) == state


def test_obscured_priority_is_unreadable_instead_of_off():
    image = frame('setup', '3')
    panel = ev.selected_unit(image)
    image[448:463, 337:355] = 0
    assert ev.auto_upgrade_state(image, panel) is None


@pytest.mark.parametrize('state', range(1, 7))
def test_priority_digit_survives_changed_button_background(state):
    image = frame('setup', str(state))
    # Hover/lighting changes the blue fill while the white digit stays put.
    crop = image[448:463, 337:355]
    colored = crop.max(axis=2).astype(float)-crop.min(axis=2) > 30
    crop[colored] = (240, 140, 20)
    panel = ev.selected_unit(image)
    assert panel is not None
    assert ev.auto_upgrade_state(image, panel) == state


def test_no_capture_is_unreadable():
    assert ev.auto_upgrade_state(None, {'number_box': (337, 448, 18, 15)}) is None


def runner(monkeypatch, image=None):
    r = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    r.logs = []
    r._log = r.logs.append
    r._current_task = {'mode': 'expedition', 'macro': 'Expeditions'}
    r._checkpoint = lambda stop: stop.is_set()
    r._interruptible_sleep = lambda *_: None
    r._dismiss_reward_card_if_found = lambda *_: False
    r._find_start_game_button = lambda *_: ('nav_start_game', {'cx': 576, 'cy': 214, 'score': 1})
    r._set_status = lambda **_: None
    r._save_debug_screenshot_unconditional = MagicMock(return_value='failure.png')
    monkeypatch.setattr(rx.wm, 'activate_window', lambda *_: True)
    monkeypatch.setattr(rx.vision, 'capture_window_region_bgr', lambda *_: image if image is not None else frame('defense'))
    monkeypatch.setattr(rx.vision, 'capture_game_bgr', lambda *_: image if image is not None else frame('defense'))
    monkeypatch.setattr(rx.vision, 'save_region_debug', lambda *_: 'failure.png')
    r._hover_click = lambda x, y, hwnd: r._mouse.click(x, y)
    monkeypatch.setattr(rx.vision, 'ref_to_screen', lambda h, x, y: (int(x), int(y)))
    monkeypatch.setattr(rx.time, 'sleep', lambda *_: None)
    return r


PLACE = {'type': 'place_unit', '_ordinal': 7, 'hotkey': '4',
         'params': {'x': 970, 'y': 348, 'name': 'Wolf'}}


@pytest.mark.parametrize('stage', ['assault', 'setup'])
def test_start_in_other_stages_never_runs_battle_placements(monkeypatch, stage):
    r = runner(monkeypatch, frame(stage))
    r._check_defense_placement = MagicMock()
    assert r._prepare_expedition_defense(1, threading.Event(), [PLACE], True, 'Expeditions')
    r._check_defense_placement.assert_not_called()


def test_unreadable_stage_cannot_authorize_start(monkeypatch):
    r = runner(monkeypatch, np.zeros((756, 1152, 3), dtype=np.uint8))
    r._check_defense_placement = MagicMock()
    monkeypatch.setattr(rx.vision, 'click_match', MagicMock())
    r._check_expedition_wave_result(1, threading.Event())
    rx.vision.click_match.assert_not_called()
    r._check_defense_placement.assert_not_called()
    r._save_debug_screenshot_unconditional.assert_called_once()


def test_defense_icon_without_wave_badge_is_unknown_not_setup():
    image = frame('defense')
    image[20:50, 370:480] = 0
    assert ev.stage(image) is None


def test_elite_requires_wave_badge_and_current_node():
    image = frame('elite')
    assert ev.stage(image) == 'defense'
    image[20:50, 370:480] = 0
    assert ev.stage(image) is None
    image = frame('assault')
    image[60:87, 617:645] = frame('elite')[60:87, 417:445]
    assert not ev.is_defense(image)


def test_elite_prepares_atom_before_alucard_and_start(monkeypatch):
    r = runner(monkeypatch, frame('elite'))
    calls = []
    r._expedition_battle_blocks = [
        dict(PLACE, params={'name': 'Atom'}), dict(PLACE, params={'name': 'Alu'})]
    r._check_defense_placement = lambda h, s, b, *_: calls.append(b['params']['name'])
    monkeypatch.setattr(rx.vision, 'click_match', lambda *_: calls.append('start'))
    r._check_expedition_wave_result(1, threading.Event())
    assert calls == ['Atom', 'Alu', 'start']


def test_expedition_outline_does_not_move_the_saved_placement(monkeypatch):
    r = runner(monkeypatch)
    r._scan_place_search_box = lambda *_: (-17, 3)
    assert r._find_valid_place_spot(1, threading.Event(), 0, 0, 812, 345, 'Atom') == (812, 345)
    assert all(call.args == (812, 345) for call in r._mouse.move_to.call_args_list)


@pytest.mark.parametrize('panels,attempts,confirmed', [([None, {}], 2, True),
                                                     ([None]*3, 3, False),
                                                     ([{}], 1, True)])
def test_prestart_placement_confirms_before_continuing(monkeypatch, panels, attempts, confirmed):
    r = runner(monkeypatch, frame('setup'))
    r._expedition_initial_setup = True
    r._placed_unit_positions[7] = (999, 350)  # stale success cannot survive a failed check
    r._find_valid_place_spot = lambda *_: (812, 345)
    r._select_expedition_unit = MagicMock(side_effect=panels)
    r._close_expedition_unit_panel = MagicMock()
    monkeypatch.setattr(rb.vision, 'find_image', lambda *_a, **_k: None)
    block = dict(PLACE, hotkey='3', params={'name': 'Atom', 'x': 812, 'y': 345})
    r._run_place_unit_block(1, threading.Event(), 0, 0, block, 8, 'Expeditions', 7, verify=False)
    assert r._select_expedition_unit.call_count == attempts
    assert r._mouse.click.call_count == attempts
    assert (7 in r._placed_unit_positions) == confirmed
    if confirmed:
        assert r._placed_unit_positions[7] == (812, 345)
    else:
        r._save_debug_screenshot_unconditional.assert_called_once()


def test_start_waits_when_stage_changes_during_transition(monkeypatch):
    r = runner(monkeypatch)
    images = iter([frame('setup'), frame('defense')])
    monkeypatch.setattr(rx.vision, 'capture_window_region_bgr', lambda *_: next(images))
    r._check_defense_placement = MagicMock()
    assert not r._prepare_expedition_defense(1, threading.Event(), [PLACE], True, 'Expeditions')
    r._check_defense_placement.assert_not_called()


def test_missing_focus_defers_defense_instead_of_skipping_units(monkeypatch):
    r = runner(monkeypatch)
    monkeypatch.setattr(rx.wm, 'activate_window', lambda *_: False)
    r._check_defense_placement = MagicMock()
    assert not r._prepare_expedition_defense(1, threading.Event(), [PLACE], True, 'Expeditions')
    r._check_defense_placement.assert_not_called()
    assert not getattr(r, '_exp_defense_state', {}).get('done')


def test_interrupted_unit_check_is_resumed_before_start(monkeypatch):
    r = runner(monkeypatch)
    r._check_defense_placement = MagicMock(side_effect=[False, None])
    assert not r._prepare_expedition_defense(1, threading.Event(), [PLACE], True, 'Expeditions')
    assert not r._exp_defense_state.get('done')
    assert r._prepare_expedition_defense(1, threading.Event(), [PLACE], True, 'Expeditions')
    assert r._check_defense_placement.call_count == 2


def test_start_anyway_confirmation_cannot_bypass_defense(monkeypatch):
    r = runner(monkeypatch)
    monkeypatch.setattr(rx.vision, 'find_image', lambda *_: {'score': 1})
    monkeypatch.setattr(rx.vision, 'click_match', MagicMock())
    r._prepare_expedition_defense = MagicMock(return_value=False)
    assert not r._click_start_game_2_if_found(1, threading.Event())
    rx.vision.click_match.assert_not_called()


def test_each_defense_prepares_once_before_start_even_if_vote_fails(monkeypatch):
    r = runner(monkeypatch)
    calls = []
    r._check_defense_placement = lambda *args: calls.append('check')
    r._expedition_battle_blocks = [PLACE]
    monkeypatch.setattr(rx.vision, 'click_match', lambda *_: calls.append('start'))
    r._check_expedition_wave_result(1, threading.Event())
    r._check_expedition_wave_result(1, threading.Event())
    assert calls == ['check', 'start', 'start']
    r._exp_defense_state['prompt_cleared'] = True
    r._check_expedition_wave_result(1, threading.Event())
    assert calls == ['check', 'start', 'start', 'check', 'start']


def test_battle_placements_and_priorities_are_prepared(monkeypatch):
    r = runner(monkeypatch)
    r._check_defense_placement = MagicMock()
    r._run_expedition_auto_upgrade = MagicMock()
    blocks = [dict(PLACE, params={}), {'type': 'wait_wave', 'params': {'wave': 4}}, PLACE,
              {'type': 'auto_upgrade_unit', 'params': {'index': 7}}]
    assert r._prepare_expedition_defense(1, threading.Event(), blocks, True, 'Expeditions')
    r._run_expedition_auto_upgrade.assert_called_once()
    assert r._check_defense_placement.call_count == 2  # unset Aizen is harmlessly skipped by checker
    r._run_prestart_blocks = MagicMock()
    r._run_prestart_blocks.assert_not_called()


def test_existing_unit_is_selected_and_kept_without_placement(monkeypatch):
    r = runner(monkeypatch)
    r._select_expedition_unit = MagicMock(return_value={'close': (368, 262)})
    r._close_expedition_unit_panel = MagicMock()
    r._run_place_unit_block = MagicMock()
    r._placed_unit_positions = {7: (970, 348)}
    r._check_defense_placement(1, threading.Event(), PLACE, 1, 'Expeditions')
    r._run_place_unit_block.assert_not_called()
    assert r._placed_unit_positions[7] == (970, 348)


def test_aligned_position_is_reselected_never_assumed_present(monkeypatch):
    r = runner(monkeypatch)
    r._placed_unit_positions = {7: (952, 337)}
    r._select_expedition_unit = MagicMock(return_value={})
    r._close_expedition_unit_panel = MagicMock()
    r._run_place_unit_block = MagicMock()
    r._check_defense_placement(1, threading.Event(), PLACE, 1, 'Expeditions')
    assert r._select_expedition_unit.call_count == 1
    assert r._select_expedition_unit.call_args.args[2] == (952, 337)
    r._run_place_unit_block.assert_not_called()
    assert r._placed_unit_positions[7] == (952, 337)


def test_missing_unit_tries_once_then_waits_for_next_defense(monkeypatch):
    r = runner(monkeypatch)
    r._select_expedition_unit = MagicMock(return_value=None)
    r._close_expedition_unit_panel = MagicMock()
    r._run_place_unit_block = MagicMock()
    r._placed_unit_positions = {7: (970, 348)}
    r._check_defense_placement(1, threading.Event(), PLACE, 1, 'Expeditions')
    assert r._run_place_unit_block.call_count == 1
    assert 7 not in r._placed_unit_positions
    assert any('next defense' in message for message in r.logs)

    r._check_defense_placement(1, threading.Event(), PLACE, 1, 'Expeditions')
    assert r._run_place_unit_block.call_count == 2  # one fresh attempt next defense


def test_confirmed_placement_stops_retrying(monkeypatch):
    r = runner(monkeypatch)
    r._select_expedition_unit = MagicMock(side_effect=[None, {}])
    r._close_expedition_unit_panel = MagicMock()
    r._run_place_unit_block = MagicMock()
    r._check_defense_placement(1, threading.Event(), PLACE, 1, 'Expeditions')
    assert r._run_place_unit_block.call_count == 1
    assert r._placed_unit_positions[7] == (970, 348)


def test_assault_tick_cannot_run_placement_or_unit_upgrade(monkeypatch):
    r = runner(monkeypatch, frame('assault'))
    r._battle_block_index = 0
    r._battle_block_state = {}
    r._run_place_unit_block = MagicMock()
    r._run_expedition_auto_upgrade = MagicMock()
    r._run_battle_blocks_tick(1, threading.Event(), [PLACE, {'type': 'auto_upgrade_unit'}], True)
    r._run_place_unit_block.assert_not_called()
    r._run_expedition_auto_upgrade.assert_not_called()


@pytest.mark.parametrize('hotkey', [False, True])
@pytest.mark.parametrize('current,target,steps', [(0, 2, 2), (2, 2, 0), (6, 1, 2), (1, 0, 6), (0, 6, 6)])
def test_auto_upgrade_cycles_from_observed_state_and_verifies(monkeypatch, hotkey, current, target, steps):
    r = runner(monkeypatch)
    r._placed_unit_positions[7] = (970, 348)
    panel = ev.selected_unit(frame('defense', 'off' if current == 0 else str(current)))
    r._select_expedition_unit = MagicMock(return_value=panel)
    r._close_expedition_unit_panel = MagicMock()
    r._get_hotkeys = lambda: {'game_auto_upgrade': 'u'}
    live = {'state': current}
    def capture(*_):
        return frame('defense', str(live['state']) if live['state'] else 'off')
    def advance(*_):
        live['state'] = (live['state'] + 1) % 7
    monkeypatch.setattr(rb.vision, 'capture_game_bgr', capture)
    r._mouse.click.side_effect = advance
    r._keyboard.tap.side_effect = advance
    block = {'params': {'index': 7, 'priority': target or 'None', 'input': 'hotkey' if hotkey else 'click'}}
    assert r._run_auto_upgrade_unit_tick(1, threading.Event(), block, 1)
    assert (r._keyboard.tap.call_count if hotkey else r._mouse.click.call_count) == steps
    assert r._select_expedition_unit.call_count == 1


@pytest.mark.parametrize('panel_exists', [False, True])
def test_auto_upgrade_failure_is_bounded_without_blind_changes(monkeypatch, panel_exists):
    r = runner(monkeypatch)
    r._placed_unit_positions[7] = (970, 348)
    r._select_expedition_unit = MagicMock(return_value={} if panel_exists else None)
    r._close_expedition_unit_panel = MagicMock()
    monkeypatch.setattr(ev, 'auto_upgrade_state', lambda *_: None)
    r._run_auto_upgrade_unit_tick(1, threading.Event(), {'params': {'index': 7, 'priority': 2}}, 1)
    assert r._select_expedition_unit.call_count == 3
    r._mouse.click.assert_not_called()
    assert any('failed after 3' in message for message in r.logs)


def test_dropped_click_retries_from_actual_priority(monkeypatch):
    r = runner(monkeypatch)
    r._placed_unit_positions[7] = (970, 348)
    image = frame('defense', '1')
    panel = ev.selected_unit(image)
    r._select_expedition_unit = MagicMock(return_value=panel)
    r._close_expedition_unit_panel = MagicMock()
    live = {'state': 1, 'clicks': 0}
    def capture(*_):
        return frame('defense', str(live['state']))
    def click(*_):
        live['clicks'] += 1
        if live['clicks'] > 1:
            live['state'] += 1
    monkeypatch.setattr(rb.vision, 'capture_game_bgr', capture)
    r._mouse.click.side_effect = click
    r._run_auto_upgrade_unit_tick(1, threading.Event(),
                                 {'params': {'index': 7, 'priority': 3}}, 1)
    assert live == {'state': 3, 'clicks': 3}
    assert r._select_expedition_unit.call_count == 2
    assert any('priority 3 confirmed' in message for message in r.logs)


def test_transient_correct_number_is_not_confirmation(monkeypatch):
    r = runner(monkeypatch)
    images = iter([frame('defense', '3'), frame('defense', '1'), frame('defense', '1')])
    monkeypatch.setattr(rb.vision, 'capture_game_bgr', lambda *_: next(images))
    _, state = r._read_expedition_priority(1, threading.Event())
    assert state == 1


def test_selection_clears_old_panel_before_clicking_new_unit(monkeypatch):
    r = runner(monkeypatch)
    images = iter([frame('defense', '1'), frame('defense'), frame('defense', '2')])
    monkeypatch.setattr(rb.vision, 'capture_game_bgr', lambda *_: next(images))
    panel = r._select_expedition_unit(1, threading.Event(), (970, 348))
    assert panel is not None
    assert [call.args for call in r._mouse.click.call_args_list] == [(368, 262), (970, 348)]


def test_stop_prevents_defense_actions(monkeypatch):
    r = runner(monkeypatch)
    r._check_defense_placement = MagicMock()
    stop = threading.Event()
    stop.set()
    assert not r._prepare_expedition_defense(1, stop, [PLACE], True, 'Expeditions')
    r._check_defense_placement.assert_not_called()


def test_expedition_search_never_spirals_into_unit_manager(monkeypatch):
    r = runner(monkeypatch)
    assert r._spiral_search_place_spot(1, threading.Event(), 0, 0, 970, 348, 'Wolf') is None
    r._mouse.move_to.assert_not_called()


def test_defense_priorities_finish_before_start_and_do_not_rerun_in_combat(monkeypatch):
    r = runner(monkeypatch)
    calls = []
    r._expedition_battle_blocks = [PLACE, {'type': 'auto_upgrade_unit', 'params': {'index': 7, 'priority': 3}}]
    r._check_defense_placement = lambda *_: calls.append('place')
    r._run_expedition_auto_upgrade = lambda *_: calls.append('priority') or True
    monkeypatch.setattr(rx.vision, 'click_match', lambda *_: calls.append('start'))
    r._check_expedition_wave_result(1, threading.Event())
    assert calls == ['place', 'priority', 'start']
    r._run_battle_blocks_tick(1, threading.Event(), r._expedition_battle_blocks, True)
    assert calls == ['place', 'priority', 'start']
    r._exp_defense_state = {}
    r._check_expedition_wave_result(1, threading.Event())
    assert calls == ['place', 'priority', 'start'] * 2
