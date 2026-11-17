"""Captured Bossrush transitions must preserve combat progress and gate order."""
from pathlib import Path
from functools import lru_cache
import threading
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from core import bossrush, maps, paths
from core import runner_bossrush as br
from core.image_io import read_image
from core.runner import MacroRunner


ROOT = Path(__file__).resolve().parents[1]
CAPTURES = ROOT / 'Assets/reference/bossrush'
STOP = threading.Event()
OBSERVE = bossrush.observe


def capture(name):
    return read_image(CAPTURES / f'{name}.png')


@lru_cache(maxsize=12)
def observed(name):
    return OBSERVE(capture(name)) if name else {}


@pytest.mark.parametrize('name,key', [('card', 'card'), ('decision', 'decision'),
    ('hub', 'gates'), ('enter', 'enter'), ('start', 'start'), ('victory', 'victory')])
def test_real_capture_controls(name, key):
    assert bossrush.observe(capture(name))[key] is not None


def test_lobby_screens_do_not_look_like_gate_transitions():
    for name in ('menu', 'district', 'party'):
        assert not any(bossrush.observe(capture(name)).values())


@pytest.mark.parametrize('name,template', [('menu', 'bossrush_mode'), ('district', 'bossrush_district'),
    ('district', 'bossrush_select_stage'), ('district', 'bossrush_matchmaking')])
def test_entry_templates_match_the_actual_screen(name, template):
    gray = cv2.cvtColor(capture(name), cv2.COLOR_BGR2GRAY)
    assert bossrush.match(gray, template)


@pytest.mark.parametrize('value,expected', [(None, 2), ('bad', 2), (0, 2), (2, 2), ('4', 4), (6, 6), (99, 6)])
def test_gate_limits(value, expected):
    assert bossrush.options({'bossrush_gates': value})[0] == expected


def test_defaults_and_card_choices():
    assert bossrush.options({}) == (2, 'random')
    for choice in bossrush.CARD_POINTS:
        assert bossrush.card_choice(choice) == choice
    assert {bossrush.card_choice('random') for _ in range(100)} == set(bossrush.CARD_POINTS)


def make_runner(monkeypatch, task=None):
    r = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    r._current_task = {'mode': 'bossrush', 'map': 'District 7', **(task or {})}
    r._checkpoint = MagicMock(return_value=False)
    r._force_focus = MagicMock(return_value=True)
    r._set_status = MagicMock()
    r._bossrush_click = MagicMock(return_value=True)
    r._save_debug_screenshot_unconditional = MagicMock()
    r._battle_block_index = 7
    r._battle_block_state = {'remaining': 4, 'idle_attempts': 1}
    r._loop_runtime = {'loop_a': {'index': 3, 'state': {'remaining': 2}}}
    r._bossrush_reset(r._current_task)
    clock = [100.0]
    monkeypatch.setattr(br.time, 'monotonic', lambda: clock[0])
    r._bossrush_state['changed_at'] = 100
    replay = MagicMock()
    monkeypatch.setattr(br.paths, 'replay_events', replay)
    return r, clock, replay


def tick(monkeypatch, runner, clock, name):
    clock[0] += 2
    frame = capture(name) if name else np.zeros((756, 1152, 3), dtype=np.uint8)
    monkeypatch.setattr(br.vision, 'capture_game_bgr', lambda _: frame)
    ui = observed(name)
    monkeypatch.setattr(br.bossrush, 'observe', lambda _: ui)
    return runner._bossrush_tick(123, STOP)


@pytest.mark.parametrize('target', [2, 3, 4, 5, 6])
def test_full_gate_sequence_and_boss_preserve_custom_macro(monkeypatch, target):
    r, clock, replay = make_runner(monkeypatch, {'bossrush_gates': target, 'bossrush_card': 'dark'})
    for gate in range(1, target+1):
        assert tick(monkeypatch, r, clock, 'hub') == (None, True)
        assert replay.call_args.args[0] == paths.load_path(f'Boss Rush Gate {gate}')['events']
        assert tick(monkeypatch, r, clock, 'enter') == (None, True)
        assert tick(monkeypatch, r, clock, 'start') == (None, True)
        assert tick(monkeypatch, r, clock, None) == (None, False)
        assert r._bossrush_state['phase'] == 'gate'
        assert tick(monkeypatch, r, clock, 'card') == (None, True)
        tick(monkeypatch, r, clock, 'card')  # same card is not another clear
        assert r._bossrush_state['completed'] == gate
        assert r._bossrush_click.call_args.args[2:4] == bossrush.CARD_POINTS['dark']
        tick(monkeypatch, r, clock, None)  # card clears
        if gate >= 2:
            tick(monkeypatch, r, clock, 'decision')
            assert r._bossrush_click.call_args.args[2] == (635 if gate == target else 516)
        if gate < target:
            tick(monkeypatch, r, clock, None)
    tick(monkeypatch, r, clock, 'start')
    assert tick(monkeypatch, r, clock, None) == (None, False)
    assert r._bossrush_state['phase'] == 'boss'
    assert tick(monkeypatch, r, clock, 'victory') == ('win', True)
    assert replay.call_count == target
    assert r._battle_block_index == 7
    assert r._battle_block_state == {'remaining': 4, 'idle_attempts': 1}
    assert r._loop_runtime['loop_a'] == {'index': 3, 'state': {'remaining': 2}}


def test_repeated_start_does_not_create_another_gate(monkeypatch):
    r, clock, _ = make_runner(monkeypatch)
    for _ in range(3):
        tick(monkeypatch, r, clock, 'start')
    assert r._bossrush_state['completed'] == 0
    assert tick(monkeypatch, r, clock, 'start') == ('failed', True)


def test_failed_walk_is_not_replayed_from_unknown_position(monkeypatch):
    r, clock, replay = make_runner(monkeypatch)
    tick(monkeypatch, r, clock, 'hub')
    clock[0] += 46
    assert tick(monkeypatch, r, clock, 'hub') == ('failed', True)
    assert replay.call_count == 1
    assert r._bossrush_state['completed'] == 0


def test_wait_block_pauses_between_gates_and_resumes_remaining_time(monkeypatch):
    r, clock, _ = make_runner(monkeypatch)
    r._battle_block_state = {}
    block = {'params': {'ms': 10000}}
    assert not r._bossrush_wait_tick(block)
    clock[0] += 4
    assert not r._bossrush_wait_tick(block)
    r._bossrush_pause_blocks()
    clock[0] += 50
    assert not r._bossrush_wait_tick(block)
    assert r._battle_block_state['bossrush_wait_left'] == 6
    clock[0] += 6
    assert r._bossrush_wait_tick(block)


def test_card_cannot_consume_the_pending_upgrade_block(monkeypatch):
    r, clock, _ = make_runner(monkeypatch)
    r._battle_block_index = 0
    r._run_upgrade_unit_tick = MagicMock()
    monkeypatch.setattr(br.vision, 'capture_game_bgr', lambda _: capture('card'))
    r._run_battle_blocks_tick(123, STOP, [{'type': 'upgrade_unit'}], True)
    r._run_upgrade_unit_tick.assert_not_called()
    assert r._battle_block_state['remaining'] == 4
    assert r._battle_block_index == 0


def test_matchmaking_or_auto_vote_can_start_a_gate(monkeypatch):
    r, clock, _ = make_runner(monkeypatch)
    r._bossrush_state['phase'] = 'entering'
    monkeypatch.setattr(br.vision, 'capture_game_bgr', lambda _: capture('hub'))
    monkeypatch.setattr(br.bossrush, 'observe', lambda _: {'boss_health': {'score': 1}})
    assert r._bossrush_tick(123, STOP) == (None, True)
    assert r._bossrush_tick(123, STOP) == (None, False)
    assert r._bossrush_state['phase'] == 'gate'


def test_defeat_is_terminal_and_does_not_count_a_gate(monkeypatch):
    r, clock, _ = make_runner(monkeypatch)
    monkeypatch.setattr(br.vision, 'capture_game_bgr', lambda _: capture('hub'))
    monkeypatch.setattr(br.bossrush, 'observe', lambda _: {'defeat': {'score': 1}})
    assert r._bossrush_tick(123, STOP) == ('loss', True)
    assert r._bossrush_state['completed'] == 0


def test_match_loop_suspends_battle_and_loops_during_navigation(monkeypatch):
    r, _, _ = make_runner(monkeypatch)
    r._bossrush_tick = MagicMock(side_effect=[(None, True), (None, True), ('win', True)])
    r._run_battle_blocks_tick = MagicMock()
    r._tick_loop_phases = MagicMock()
    r._interruptible_sleep = MagicMock()
    assert r._wait_for_match_result(123, STOP, [{'type': 'upgrade_unit'}],
                                  mode='bossrush', task=r._current_task) == 'win'
    r._run_battle_blocks_tick.assert_not_called()
    r._tick_loop_phases.assert_not_called()
    assert r._battle_block_state['remaining'] == 4


def test_district_preview_and_six_bundled_paths_exist():
    assert 'Bossrush' in maps.list_categories()
    assert maps.list_maps('Bossrush') == ['District 7']
    assert maps.map_image_data_uri('Bossrush', 'District 7').startswith('data:image/png;base64,')
    for gate in range(1, 7):
        events = paths.load_path(f'Boss Rush Gate {gate}')['events']
        assert events and events[-1]['state'] == 'up'


def test_solo_and_matchmaking_use_shared_stage_entry(monkeypatch):
    r, _, _ = make_runner(monkeypatch)
    r._click_and_verify_gone = MagicMock(return_value=True)
    r._click_start_and_wait_teleport = MagicMock(return_value=True)
    r._click_enter_matchmaking = MagicMock(return_value=True)
    r._wait_teleport_in = MagicMock(return_value=True)
    assert r._enter_selected_stage(123, STOP, r._current_task, 'bossrush', {})
    assert r._click_and_verify_gone.call_args.args[2] == 'bossrush_select_stage'
    r._current_task['play_mode'] = 'matchmaking'
    assert r._enter_selected_stage(123, STOP, r._current_task, 'bossrush', {})
    r._click_enter_matchmaking.assert_called_once()
    r._wait_teleport_in.assert_called_once()
