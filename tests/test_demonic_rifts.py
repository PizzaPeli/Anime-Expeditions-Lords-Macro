from datetime import datetime, timezone
from threading import Event
from unittest.mock import MagicMock

import pytest

from core import rifts, settings, vision
from core.runner import MacroRunner


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'SETTINGS_FILE', str(tmp_path / 'settings.json'))


@pytest.mark.parametrize('minute,second,expected', [
    (0, 0, 'enter'), (14, 59, 'enter'), (15, 0, 'normal'),
    (56, 59, 'normal'), (57, 0, 'wait'), (59, 59, 'wait')])
def test_hourly_entry_and_three_minute_guard(minute, second, expected):
    now = datetime(2026, 11, 16, 12, minute, second, tzinfo=timezone.utc)
    assert rifts.action(now, {'enabled': True}, {}) == expected
    assert rifts.action(now, {'enabled': False}, {}) == 'normal'


def test_ledger_survives_setting_edits_and_next_hour_is_available():
    now = datetime(2026, 11, 16, 12, 4, tzinfo=timezone.utc)
    rifts.reserve(rifts.window(now)[0], 3, 2, finished=True)
    settings.update({'demonic_rifts': {'enabled': True, 'macro': 'Farm'}})
    assert rifts.action(now) == 'normal'
    assert rifts.action(now.replace(hour=13)) == 'enter'


def runner():
    r = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    r._checkpoint = lambda stop: stop.is_set()
    r._set_status = MagicMock()
    return r


def test_guard_wait_is_interruptible_and_disabled_setting_resumes(monkeypatch):
    r = runner()
    states = iter(['wait', 'normal'])
    monkeypatch.setattr(rifts, 'action', lambda: next(states))
    r._interruptible_sleep = MagicMock()
    r._run_hourly_rift = MagicMock()
    assert r._rift_lobby_boundary(1, Event())
    r._interruptible_sleep.assert_called_once()
    r._run_hourly_rift.assert_not_called()


def test_rift_does_not_recurse_into_scheduler(monkeypatch):
    r = runner()
    r._running_rift = True
    monkeypatch.setattr(rifts, 'action', lambda: pytest.fail('Nested schedule check'))
    assert not r._rift_blocks_new_match()
    assert r._rift_lobby_boundary(1, Event())


@pytest.mark.parametrize('results', [['win', 'win'], ['loss', 'win', 'loss', 'win']])
def test_rift_repeats_until_two_victories_and_then_recovers(monkeypatch, results):
    r = runner()
    settings.update({'demonic_rifts': {'enabled': True}})
    monkeypatch.setattr(rifts, 'window', lambda: ('hour', 30))
    r._enter_hourly_rift = MagicMock(return_value=True)
    r._wait_teleport_in = MagicMock(return_value=True)
    r._play_one_match = MagicMock(side_effect=results)
    r._recover_to_lobby = MagicMock(return_value=True)
    monkeypatch.setattr(vision, 'find_image', lambda *_: None)
    calls = []
    def handle(*args, repeat):
        calls.append(repeat)
        r._result_repeated_in_place = repeat
        return True
    r._handle_match_result = handle
    r._run_hourly_rift(1, Event(), 'hour', {}, {})
    assert calls == [True] * (len(results)-1) + [False]
    assert r._play_one_match.call_count == len(results)
    assert settings.load()['demonic_rift_state'] == {'hour': 'hour', 'runs': len(results),
                                                    'clears': 2, 'finished': True}
    r._recover_to_lobby.assert_called_once()


def test_unavailable_repeat_reenters_while_window_open(monkeypatch):
    r = runner()
    settings.update({'demonic_rifts': {'enabled': True}})
    monkeypatch.setattr(rifts, 'window', lambda: ('hour', 30))
    r._enter_hourly_rift = MagicMock(return_value=True)
    r._wait_teleport_in = MagicMock(return_value=True)
    r._play_one_match = MagicMock(return_value='win')
    r._recover_to_lobby = MagicMock()
    r._reset_rift_spawn = MagicMock(return_value=True)
    r._result_repeated_in_place = False
    r._handle_match_result = MagicMock(return_value=True)
    monkeypatch.setattr(vision, 'find_image', lambda *_: None)
    r._run_hourly_rift(1, Event(), 'hour', {}, {})
    assert r._play_one_match.call_count == 2
    assert r._enter_hourly_rift.call_count == 2
    r._reset_rift_spawn.assert_called_once()


def test_pending_rift_remains_due_until_two_clears_or_window_closes():
    now = datetime(2026, 11, 16, 12, 4, tzinfo=timezone.utc)
    rifts.reserve(rifts.window(now)[0], 4, 1)
    settings.update({'demonic_rifts': {'enabled': True}})
    assert rifts.action(now) == 'enter'
    assert rifts.action(now.replace(minute=15)) == 'normal'


def test_failed_walk_resets_spawn_and_retries_until_window_closes(monkeypatch):
    r = runner()
    settings.update({'demonic_rifts': {'enabled': True}})
    clock = iter([('hour', 30), ('hour', 40), ('hour', 900)])
    monkeypatch.setattr(rifts, 'window', lambda: next(clock))
    r._interruptible_sleep = MagicMock()
    r._enter_hourly_rift = MagicMock(return_value=False)
    r._reset_rift_spawn = MagicMock(return_value=True)
    r._recover_to_lobby = MagicMock()
    r._play_one_match = MagicMock()
    monkeypatch.setattr(vision, 'find_image', lambda *_: None)
    r._run_hourly_rift(1, Event(), 'hour', {}, {})
    assert r._enter_hourly_rift.call_count == 2
    r._reset_rift_spawn.assert_called_once()
    r._play_one_match.assert_not_called()
    assert settings.load()['demonic_rift_state']['finished']


def test_rift_resumes_saved_clear_count(monkeypatch):
    r = runner()
    settings.update({'demonic_rifts': {'enabled': True}})
    rifts.reserve('hour', 3, 1)
    monkeypatch.setattr(rifts, 'window', lambda: ('hour', 30))
    monkeypatch.setattr(vision, 'find_image', lambda *_: None)
    r._enter_hourly_rift = MagicMock(return_value=True)
    r._wait_teleport_in = MagicMock(return_value=True)
    r._play_one_match = MagicMock(return_value='win')
    r._handle_match_result = MagicMock(return_value=True)
    r._recover_to_lobby = MagicMock()
    r._run_hourly_rift(1, Event(), 'hour', {}, {})
    r._play_one_match.assert_called_once()
    assert r._handle_match_result.call_args.kwargs['repeat'] is False
    assert settings.load()['demonic_rift_state']['clears'] == 2


def test_failed_spawn_reset_does_not_walk_from_wrong_position(monkeypatch):
    r = runner()
    settings.update({'demonic_rifts': {'enabled': True}})
    clock = iter([('hour', 30), ('hour', 40), ('hour', 50), ('hour', 900)])
    monkeypatch.setattr(rifts, 'window', lambda: next(clock))
    monkeypatch.setattr(vision, 'find_image', lambda *_: None)
    r._interruptible_sleep = MagicMock()
    r._enter_hourly_rift = MagicMock(return_value=False)
    r._reset_rift_spawn = MagicMock(return_value=False)
    r._recover_to_lobby = MagicMock()
    r._run_hourly_rift(1, Event(), 'hour', {}, {})
    r._enter_hourly_rift.assert_called_once()
    assert r._reset_rift_spawn.call_count == 2


def test_spawn_reset_verifies_settings_then_closes_before_settling(monkeypatch):
    r = runner()
    r._prepare_rift_lobby = MagicMock(return_value=True)
    r._ensure_lobby = MagicMock(return_value=True)
    r._click_found_image = MagicMock(return_value={'x': 1})
    r._interruptible_sleep = MagicMock()
    r._click_task_point = MagicMock()
    r._close_settings_if_open = MagicMock()
    panels = iter([{'x': 1}, {'x': 362, 'w': 284, 'cy': 392}, None])
    monkeypatch.setattr(vision, 'find_image', lambda *_: next(panels))
    assert r._reset_rift_spawn(1, Event())
    assert r._click_task_point.call_args.args[1:3] == (621, 392)
    r._close_settings_if_open.assert_called_once()


def test_spawn_reset_does_not_click_when_settings_unverified(monkeypatch):
    r = runner()
    r._prepare_rift_lobby = MagicMock(return_value=True)
    r._ensure_lobby = MagicMock(return_value=True)
    r._click_found_image = MagicMock(return_value={'x': 1})
    r._interruptible_sleep = MagicMock()
    r._click_task_point = MagicMock()
    monkeypatch.setattr(vision, 'find_image', lambda *_: None)
    assert not r._reset_rift_spawn(1, Event())
    r._click_task_point.assert_not_called()


def test_boundary_restores_paused_task_and_progress(monkeypatch):
    r = runner()
    r._current_task = {'map': 'School Grounds'}
    r._active_task_progress = {'next_repeat': 4}
    r._result_requires_lobby_setup = True
    states = iter(['enter', 'normal'])
    monkeypatch.setattr(rifts, 'action', lambda: next(states))
    def play(*_):
        r._current_task = {'map': 'Rift'}
        r._active_task_progress = None
        r._result_requires_lobby_setup = False
    r._run_hourly_rift = play
    assert r._rift_lobby_boundary(1, Event())
    assert r._current_task == {'map': 'School Grounds'}
    assert r._active_task_progress == {'next_repeat': 4}
    assert r._result_requires_lobby_setup is True
    assert r._running_rift is False
    assert r._set_status.call_args.kwargs['map'] == 'School Grounds'


def test_public_party_is_made_private_before_start(monkeypatch):
    r = runner()
    r._prepare_rift_lobby = MagicMock(return_value=True)
    r._ensure_lobby = MagicMock(return_value=True)
    r._force_focus = MagicMock(return_value=True)
    r._rift_party_text = MagicMock(side_effect=['public party', 'private party'])
    r._click_task_point = MagicMock()
    r._interruptible_sleep = MagicMock()
    r._click_found_image = MagicMock(return_value={'x': 1})
    monkeypatch.setattr(rifts, 'window', lambda: ('hour', 30))
    monkeypatch.setattr('core.paths.replay_events', MagicMock())
    monkeypatch.setattr(vision, 'wait_for_image', lambda *a, **kw: {'x': 1})
    assert r._enter_hourly_rift(1, Event(), 'hour')
    r._click_task_point.assert_called_once()
    assert r._click_found_image.call_args.args[1] == 'rift_party_start'


def test_unverified_private_party_never_starts(monkeypatch):
    r = runner()
    r._prepare_rift_lobby = MagicMock(return_value=True)
    r._ensure_lobby = MagicMock(return_value=True)
    r._force_focus = MagicMock(return_value=True)
    r._rift_party_text = MagicMock(return_value='unreadable')
    r._interruptible_sleep = MagicMock()
    r._click_found_image = MagicMock()
    monkeypatch.setattr(rifts, 'window', lambda: ('hour', 30))
    monkeypatch.setattr('core.paths.replay_events', MagicMock())
    monkeypatch.setattr(vision, 'wait_for_image', lambda *a, **kw: {'x': 1})
    assert not r._enter_hourly_rift(1, Event(), 'hour')
    r._click_found_image.assert_not_called()


@pytest.mark.parametrize('daily', [False, True])
def test_challenge_entry_waits_for_rift_boundary(daily):
    r = runner()
    r._rift_lobby_boundary = MagicMock(return_value=False)
    r._open_challenge_screen = MagicMock()
    if daily:
        assert r._enter_daily_challenge_stage(1, Event(), 'solo', {}, {}) == 'stopped'
    else:
        assert not r._enter_challenge_stage(1, Event(), '1', 'solo', {}, {})
    r._open_challenge_screen.assert_not_called()


def test_rift_result_overrides_replay_before_other_tasks(monkeypatch):
    from core import runner as module
    r = runner()
    monkeypatch.setattr(module, 'RESULT_CAPTURE_DELAY', 0)
    r._note_win_for_crafting = MagicMock()
    r._release_quick_place_shift = MagicMock()
    r._dismiss_reward_card_if_found = MagicMock(return_value=False)
    r._clear_result_obtainment_modal = MagicMock(return_value=True)
    r._finish_match_result_background = MagicMock()
    r._rift_blocks_new_match = MagicMock(return_value=True)
    r._repeat_same_stage_result = MagicMock()
    r._click_and_verify_gone = MagicMock(return_value=True)
    r._click_return_to_lobby_if_found = MagicMock(return_value=True)
    r._rift_lobby_boundary = MagicMock(return_value=True)
    assert r._handle_match_result(1, Event(), {'mode':'story'}, 'win', '1m', {}, repeat=True)
    r._repeat_same_stage_result.assert_not_called()
    r._rift_lobby_boundary.assert_called_once()
    assert r._result_requires_lobby_setup


def test_rift_unwinds_menus_before_checking_lobby(monkeypatch):
    r = runner()
    calls = []
    r._force_focus = lambda *_: True
    monkeypatch.setattr(vision, 'find_image', lambda h, name: {'score': 1})
    r._click_found_image = lambda *_: calls.append('disband')
    r._spam_back_until_gone = lambda *_: calls.append('back')
    r._ensure_lobby = lambda *_: calls.append('lobby') or True
    assert r._prepare_rift_lobby(1, Event())
    assert calls == ['disband', 'back', 'lobby']


def test_missing_teleport_row_cannot_toggle_auto_start(monkeypatch):
    r = runner()
    r._prepare_rift_lobby = lambda *_: True
    r._click_found_image = lambda *_: {'score': 1}
    r._interruptible_sleep = lambda *_: None
    r._close_settings_if_open = MagicMock()
    r._click_task_point = MagicMock()
    monkeypatch.setattr(vision, 'find_image', lambda h, name: {'score': 1} if name == 'nav_settings_on' else None)
    assert not r._reset_rift_spawn(1, Event())
    r._click_task_point.assert_not_called()
    r._close_settings_if_open.assert_called_once()


def test_captured_lobby_settings_matches_teleport_above_auto_vote():
    from pathlib import Path
    import numpy as np
    import cv2
    from core.image_io import read_image
    panel = read_image(Path(__file__).parent / 'fixtures/rifts/lobby_settings.png')
    image = np.zeros((756, 1152, 3), np.uint8)
    image[156:598, 190:962] = panel
    match = vision.find_in_gray_multiscale(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), 'lobby_teleport_spawn')
    assert match is not None
    assert (match['x'] + match['w'] - 25, match['cy']) == (621, 392)
    # Auto Vote Start is the next row at y=443; it must never match.
    image[369:415, 362:646] = 0
    assert vision.find_in_gray_multiscale(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), 'lobby_teleport_spawn') is None
