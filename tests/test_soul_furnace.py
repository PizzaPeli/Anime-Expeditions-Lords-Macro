from pathlib import Path
import threading
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from core import runner_soul_furnace as soul
from core.runner import MacroRunner
from core.wave import read_wave


@pytest.mark.parametrize("heat,current", [(0, 1), (1, 5), (2, 10), (3, 11), (4, 14), (5, 21), (6, 28)])
def test_real_hud_captures_read_wave_and_heat_without_confusing_the_fill(heat, current):
    root = Path(__file__).resolve().parents[1]
    crop = cv2.imread(str(root / f"Assets/reference/soul_furnace/heat_{heat}_wave_{current}.png"))
    frame = np.zeros((756, 1152, 3), dtype=np.uint8)
    frame[15:110, 380:780] = crop
    assert soul.read_heat(frame) == heat
    assert read_wave(frame[21:82, 467:571]) == (current, None)


def test_default_schedule_and_explicit_empty_schedule_are_distinct():
    assert soul.normalize_purchases({}) == [{"item": "final_boss", "trigger": "heat", "target": 3}]
    assert soul.normalize_purchases({"soul_purchases": []}) == []
    assert soul.normalize_purchases({"soul_purchases": [{"item": "unknown"}]}) == []


def test_saved_purchase_threshold_is_not_replaced_by_new_default():
    rows = [{"item": "final_boss", "trigger": "heat", "target": 5}]
    assert soul.normalize_purchases({"soul_purchases": rows}) == rows


def runner_for_tick(monkeypatch, *, current=16, heat=5, purchase=True):
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    runner._set_status = MagicMock()
    runner._soul_result = MagicMock(return_value=None)
    runner._checkpoint = MagicMock(return_value=False)
    runner._soul_purchase_attempt = MagicMock(return_value=purchase)
    runner._soul_close_shop = MagicMock(return_value=True)
    runner._interruptible_sleep = MagicMock()
    runner._click_and_verify_gone = MagicMock(return_value=True)
    runner._click_return_to_lobby_if_found = MagicMock()
    monkeypatch.setattr(soul.vision, "capture_game_bgr", lambda _: np.zeros((756, 1152, 3), dtype=np.uint8))
    monkeypatch.setattr(soul.wave, "read_wave", lambda _: (current, None))
    monkeypatch.setattr(soul, "read_heat", lambda _: heat)
    return runner


def tick(runner, state, task=None):
    state["next_check"] = 0
    return runner._soul_tick(123, threading.Event(), task or {}, state)


def test_default_boss_waits_for_two_heat_reads_and_only_buys_once(monkeypatch):
    runner = runner_for_tick(monkeypatch)
    state = {}
    tick(runner, state)
    runner._soul_purchase_attempt.assert_not_called()
    tick(runner, state)
    tick(runner, state)
    tick(runner, state)
    runner._soul_purchase_attempt.assert_called_once()
    assert state["completed"] == {0}


def test_default_boss_starts_at_heat_three_and_not_heat_two(monkeypatch):
    runner = runner_for_tick(monkeypatch, heat=2)
    state = {}
    tick(runner, state)
    tick(runner, state)
    runner._soul_purchase_attempt.assert_not_called()
    monkeypatch.setattr(soul, "read_heat", lambda _: 3)
    tick(runner, state)
    runner._soul_purchase_attempt.assert_not_called()
    tick(runner, state)
    runner._soul_purchase_attempt.assert_called_once()
    runner._soul_close_shop.assert_called_once()


def test_fifth_attempt_can_succeed_and_uses_four_three_second_delays(monkeypatch):
    runner = runner_for_tick(monkeypatch, heat=3)
    runner._soul_purchase_attempt.side_effect = [False, False, False, False, True]
    state = {}
    tick(runner, state)
    tick(runner, state)
    tick(runner, state)
    assert runner._soul_purchase_attempt.call_count == 5
    assert [c.args[0] for c in runner._interruptible_sleep.call_args_list] == [3.0] * 4
    assert state["completed"] == {0}
    assert not state.get("skip_remaining")


def test_menu_close_retries_a_dropped_click_and_confirms_disappearance():
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    runner._checkpoint = MagicMock(return_value=False)
    runner._soul_find = MagicMock(side_effect=[True, True, False])
    runner._soul_click = MagicMock()
    runner._interruptible_sleep = MagicMock()
    assert runner._soul_close_shop(123, threading.Event()) is True
    assert runner._soul_click.call_count == 2
    assert all(call.args == (123, 907, 186) for call in runner._soul_click.call_args_list)


def test_closed_menu_and_stop_do_not_click_the_close_position():
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    runner._checkpoint = MagicMock(return_value=False)
    runner._soul_find = MagicMock(return_value=None)
    runner._soul_click = MagicMock()
    assert runner._soul_close_shop(123, threading.Event()) is True
    runner._soul_click.assert_not_called()
    runner._checkpoint.return_value = True
    runner._soul_find.return_value = {"score": 1}
    assert runner._soul_close_shop(123, threading.Event()) is False
    runner._soul_click.assert_not_called()


def test_stuck_menu_is_retried_without_rebuying_a_confirmed_purchase(monkeypatch):
    runner = runner_for_tick(monkeypatch, heat=3)
    runner._soul_close_shop.side_effect = [False, False, True]
    state = {}
    tick(runner, state)
    assert tick(runner, state) == "shop_open"
    assert state["completed"] == {0}
    assert tick(runner, state) == "shop_open"
    assert tick(runner, state) is None
    assert not state.get("shop_close_pending")
    runner._soul_purchase_attempt.assert_called_once()


def test_match_loop_does_not_run_battle_blocks_while_menu_is_still_open(monkeypatch):
    runner = runner_for_tick(monkeypatch)
    runner._soul_tick = MagicMock(side_effect=["shop_open", "win"])
    runner._run_battle_blocks_tick = MagicMock()
    result = runner._wait_for_match_result(
        123, threading.Event(), battle_blocks=[{"type": "upgrade_unit"}],
        mode="soul_furnace", task={"mode": "soul_furnace"})
    assert result == "win"
    runner._run_battle_blocks_tick.assert_not_called()


def test_duplicate_rows_each_buy_once_and_wave_trigger_is_independent(monkeypatch):
    runner = runner_for_tick(monkeypatch, current=16, heat=0)
    task = {"soul_purchases": [{"item": "final_boss", "trigger": "wave", "target": 16}] * 2}
    state = {}
    for _ in range(5):
        tick(runner, state, task)
    assert runner._soul_purchase_attempt.call_count == 2


def test_five_failed_attempts_do_not_leave_live_match_or_stop_macro(monkeypatch):
    runner = runner_for_tick(monkeypatch, purchase=False)
    state = {}
    tick(runner, state)
    tick(runner, state)
    for _ in range(3):
        assert tick(runner, state) is None
    assert runner._soul_purchase_attempt.call_count == 5
    assert runner._interruptible_sleep.call_count == 4
    assert runner._soul_task_purchase_failed
    runner._click_and_verify_gone.assert_not_called()
    runner._soul_result.return_value = "loss"
    assert tick(runner, state) == "loss"


def test_wave_30_finishes_before_top_bar_exit_and_confirmation(monkeypatch):
    runner = runner_for_tick(monkeypatch, current=30, heat=0)
    state = {}
    tick(runner, state, {"soul_purchases": []})
    tick(runner, state, {"soul_purchases": []})
    runner._click_and_verify_gone.assert_not_called()
    monkeypatch.setattr(soul.wave, "read_wave", lambda _: (31, None))
    assert tick(runner, state, {"soul_purchases": []}) is None
    assert tick(runner, state, {"soul_purchases": []}) == "wave_limit"
    assert runner._click_and_verify_gone.call_args.args[2] == "soul_to_lobby"
    runner._click_return_to_lobby_if_found.assert_called_once()


def test_match_result_wins_over_shop_and_wave_exit(monkeypatch):
    runner = runner_for_tick(monkeypatch, current=31)
    runner._soul_result.return_value = "win"
    assert tick(runner, {}) == "win"
    runner._soul_purchase_attempt.assert_not_called()
    runner._click_and_verify_gone.assert_not_called()


def test_bad_reads_cannot_trigger_any_purchase(monkeypatch):
    runner = runner_for_tick(monkeypatch, current=None, heat=None)
    state = {}
    for _ in range(3):
        tick(runner, state)
    runner._soul_purchase_attempt.assert_not_called()


@pytest.mark.parametrize("count,due", [(0, False), (1, False), (2, True), (3, True)])
def test_lobby_batch_threshold(count, due):
    assert soul.lobby_batch_due({"runs_before_lobby": 2}, count) is due
    assert not soul.lobby_batch_due({"runs_before_lobby": 0}, count)
    assert soul.lobby_batch_due({"mode": "portals", "runs_before_lobby": 2}, count) is due
    assert soul.lobby_batch_due({"play_mode": "matchmaking", "runs_before_lobby": 2}, count) is due


def task_runner(monkeypatch):
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    runner._set_status = MagicMock()
    for name in ("_challenge_has_ready_stage", "_crafting_wants_in", "_fuel_wants_in",
                 "_auto_shop_wants_in", "_memory_refresh_due", "_checkpoint"):
        monkeypatch.setattr(runner, name, MagicMock(return_value=False))
    runner._run_task_setup = MagicMock(return_value=True)
    runner._wait_teleport_in = MagicMock(return_value=True)
    runner._handle_match_result = MagicMock(return_value=True)
    runner._send_progress_webhook = MagicMock()
    return runner


def test_actual_task_loop_counts_wins_and_losses_and_reenters_after_two(monkeypatch):
    runner = task_runner(monkeypatch)
    runner._play_one_match = MagicMock(side_effect=["win", "loss", "win", "loss"])
    task = {"map": "School Grounds", "mode": "story", "repeat": 4, "runs_before_lobby": 2}
    assert runner._run_task(123, threading.Event(), task, 1, 1, {}, 3, 8, {}, {})
    assert [c.kwargs["repeat"] for c in runner._handle_match_result.call_args_list] == [True, False, True, False]
    assert runner._run_task_setup.call_count == 2
    assert runner._wait_teleport_in.call_count == 2
    assert [c.kwargs["first_repeat"] for c in runner._play_one_match.call_args_list] == [True, False, True, False]


def test_failed_shop_task_finishes_match_once_then_skips_remaining_repeats(monkeypatch):
    runner = task_runner(monkeypatch)
    def play(*args, **kwargs):
        runner._soul_task_purchase_failed = True
        return "win"
    runner._play_one_match = MagicMock(side_effect=play)
    task = {"map": "Soul Furnace", "mode": "soul_furnace", "repeat": 10}
    assert runner._run_task(123, threading.Event(), task, 1, 2, {}, 3, 8, {}, {})
    runner._play_one_match.assert_called_once()
    assert runner._handle_match_result.call_args.kwargs["repeat"] is False
