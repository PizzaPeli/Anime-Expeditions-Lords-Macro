from pathlib import Path
import threading
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from core import runner as runner_module
from core.runner import MacroRunner
from test_soul_furnace import task_runner


ROOT = Path(__file__).resolve().parents[1]


def test_soul_furnace_repeat_text_is_a_supported_variant():
    frame = np.zeros((756, 1152), dtype=np.uint8)
    frame[540:567, 210:301] = cv2.imread(str(ROOT / "Assets/ui/soul_repeat_stage/soul_repeat_stage.png"), 0)
    match = find_repeat(frame)
    assert match is not None
    assert 210 < match["cx"] < 301


@pytest.mark.parametrize("mode", ["soul_furnace", "raid", "tower", "portals"])
def test_single_task_queue_carries_visit_count_across_passes(monkeypatch, mode):
    runner = task_runner(monkeypatch)
    runner._play_one_match = MagicMock(side_effect=["win", "loss"] * 6)
    task = dict(mode=mode, map="Same stage", repeat=1, extract_after=1, runs_before_lobby=10)
    if mode == "portals":
        # The mocked entry follows the chooser, as the live portal entry does.
        runner._portal_entered_from = "chooser"
    runner._queue_tasks_getter = lambda: [dict(task)]
    repeats = []
    def handle(*args, repeat, **kwargs):
        repeats.append(repeat)
        runner._result_repeated_in_place = repeat
        runner._result_requires_lobby_setup = not repeat
        return True
    runner._handle_match_result = handle
    for _ in range(12):
        assert runner._run_task(123, threading.Event(), task, 1, 1, {}, 3, 8, {}, {})
    assert repeats == [True] * 9 + [False, True, True]
    if mode == "portals":
        assert runner._run_task_setup.call_count == 12
    else:
        assert runner._run_task_setup.call_count == 2
        assert runner._wait_teleport_in.call_count == 10
        assert [c.kwargs["first_repeat"] for c in runner._play_one_match.call_args_list] == [True] + [False] * 9 + [True, False]


def test_queue_change_prevents_replay_carry(monkeypatch):
    runner = task_runner(monkeypatch)
    runner._play_one_match = MagicMock(return_value="win")
    task = dict(mode="story", map="East Town", repeat=1)
    runner._queue_tasks_getter = lambda: [dict(task, map="School Grounds")]
    assert runner._run_task(123, threading.Event(), task, 1, 1, {}, 3, 8, {}, {})
    assert runner._handle_match_result.call_args.kwargs["repeat"] is False
    assert runner._queue_continuation is None


def find_repeat(frame):
    # Exercise the production search across every supported scale/variant.
    result = runner_module.vision.find_in_gray_multiscale_diagnostic(
        frame, "result_repeat_stage", threshold=0.90)
    return result["match"]



@pytest.mark.parametrize("fixture,left,right", [("next_and_repeat_stage", 362, 505), ("repeat_stage_only", 210, 429)])
def test_captured_repeat_is_found_in_its_actual_slot(fixture, left, right):
    frame = np.zeros((756, 1152), dtype=np.uint8)
    frame[540:592, 205:722] = cv2.imread(str(ROOT / f"Assets/reference/results/{fixture}.png"), 0)
    match = find_repeat(frame)
    assert match is not None
    assert left < match["cx"] < right
    assert 544 < match["cy"] < 586


def test_next_stage_cannot_be_used_as_a_fallback_when_repeat_is_missing():
    frame = np.zeros((756, 1152), dtype=np.uint8)
    frame[540:592, 205:722] = cv2.imread(str(ROOT / "Assets/reference/results/next_and_repeat_stage.png"), 0)
    frame[544:588, 362:508] = 0  # retain the actual Next Stage, erase only Repeat Stage
    assert find_repeat(frame) is None


def test_repeat_helper_clicks_label_then_checks_result_disappeared(monkeypatch):
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    runner._checkpoint = MagicMock(return_value=False)
    runner._set_status = MagicMock()
    runner._interruptible_sleep = MagicMock()
    runner._wait_for_image_gone = MagicMock(return_value=True)
    match = dict(cx=435, cy=565, score=0.99)
    wait = MagicMock(return_value=match)
    click = MagicMock()
    monkeypatch.setattr(runner_module.vision, "wait_for_image", wait)
    monkeypatch.setattr(runner_module.vision, "click_match", click)
    monkeypatch.setattr(runner_module.wm, "activate_window", lambda _: True)
    assert runner._repeat_same_stage_result(123, threading.Event(), "Victory")
    assert wait.call_args.args[1] == "result_repeat_stage"
    assert wait.call_args.kwargs["threshold"] == 0.90
    click.assert_called_once_with(runner._mouse, 123, match)
    assert runner._wait_for_image_gone.call_args.args[1] == ("result_repeat_stage", "victory")


def test_repeat_helper_never_clicks_when_the_label_cannot_be_found(monkeypatch):
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    runner._checkpoint = MagicMock(return_value=False)
    runner._set_status = MagicMock()
    monkeypatch.setattr(runner_module.vision, "wait_for_image", lambda *_args, **_kw: None)
    click = MagicMock()
    monkeypatch.setattr(runner_module.vision, "click_match", click)
    assert not runner._repeat_same_stage_result(123, threading.Event(), "Victory")
    click.assert_not_called()


@pytest.mark.parametrize("play_mode", ["solo", "matchmaking"])
def test_task_repeats_in_place_then_returns_to_lobby_for_all_play_modes(monkeypatch, play_mode):
    runner = task_runner(monkeypatch)
    runner._play_one_match = MagicMock(side_effect=["win", "loss", "win", "loss"])
    repeats = []
    def handle(*args, repeat, **kwargs):
        repeats.append(repeat)
        runner._result_repeated_in_place = repeat
        runner._result_requires_lobby_setup = not repeat
        return True
    runner._handle_match_result = handle
    task = dict(mode="raid", map="Spirit City", play_mode=play_mode, repeat=4, runs_before_lobby=2)
    assert runner._run_task(123, threading.Event(), task, 1, 1, {}, 3, 8, {}, {})
    assert repeats == [True, False, True, False]
    assert runner._run_task_setup.call_count == 2
    assert runner._wait_teleport_in.call_count == 2


def test_no_repeat_available_reenters_the_same_task_from_lobby(monkeypatch):
    runner = task_runner(monkeypatch)
    runner._play_one_match = MagicMock(return_value="win")
    def handle(*args, **kwargs):
        runner._result_requires_lobby_setup = True
        return True
    runner._handle_match_result = handle
    task = dict(mode="story", map="East Town", repeat=2, runs_before_lobby=0)
    assert runner._run_task(123, threading.Event(), task, 1, 1, {}, 3, 8, {}, {})
    assert runner._run_task_setup.call_count == 2
    runner._wait_teleport_in.assert_not_called()


def test_portal_chooser_runs_count_until_the_configured_lobby_boundary(monkeypatch):
    runner = task_runner(monkeypatch)
    runner._play_one_match = MagicMock(side_effect=["win", "loss", "win", "loss"])
    runner._portal_entered_from = "lobby"
    runner._portal_expect_chooser = False
    entries = []
    def setup(*args, **kwargs):
        runner._portal_entered_from = "chooser" if runner._portal_expect_chooser else "lobby"
        entries.append(runner._portal_entered_from)
        return True
    runner._run_task_setup = setup
    repeats = []
    def handle(*args, repeat, **kwargs):
        repeats.append(repeat)
        runner._portal_expect_chooser = repeat
        return True
    runner._handle_match_result = handle
    task = dict(mode="portals", map="Portals", extract_after=4, runs_before_lobby=2)
    assert runner._run_task(123, threading.Event(), task, 1, 1, {}, 3, 8, {}, {})
    assert repeats == [True, False, True, False]
    assert entries == ["lobby", "chooser", "lobby", "chooser"]
