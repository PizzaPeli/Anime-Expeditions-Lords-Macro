import threading

import core.runner as runner_module
from core.runner import MacroRunner


def _offer_runner(cards):
    runner = object.__new__(MacroRunner)
    runner.logged = []
    runner._mouse = object()
    runner._log = runner.logged.append
    runner._set_status = lambda **_kw: None
    runner._interruptible_sleep = lambda *_a, **_kw: None
    runner._find_portal_offer_cards = lambda _hwnd: cards
    return runner


def _cards():
    return [
        {"_slot": 1, "score": 0.91},
        {"_slot": 2, "score": 0.92},
        {"_slot": 3, "score": 0.93},
    ]


def test_portal_offer_mode_normalizes_current_and_legacy_values():
    assert MacroRunner._portal_offer_mode({"card_select": "fast"}) == "fast"
    assert MacroRunner._portal_offer_mode({"card_select": "middle"}) == "fast"
    assert MacroRunner._portal_offer_mode({"card_select": "let_game_decide"}) == "let_game_decide"
    assert MacroRunner._portal_offer_mode({"card_select": "none"}) == "let_game_decide"
    assert MacroRunner._portal_offer_mode({}) == "let_game_decide"


def test_fast_mode_waits_two_minutes_then_polls_every_second(monkeypatch):
    cards = _cards()
    runner = _offer_runner(cards)
    clicks = []
    monkeypatch.setattr(runner_module.wm, "activate_window", lambda _hwnd: True)
    monkeypatch.setattr(runner_module.vision, "click_match",
                        lambda _mouse, _hwnd, card, **_kw: clicks.append(card))

    monkeypatch.setattr(runner_module.time, "monotonic", lambda: 119.9)
    assert runner._poll_fast_portal_offer(1, threading.Event(), 0.0, 0.0) == (False, 0.0)

    monkeypatch.setattr(runner_module.time, "monotonic", lambda: 120.0)
    selected, last_check = runner._poll_fast_portal_offer(
        1, threading.Event(), 0.0, 0.0)
    assert selected is True
    assert last_check == 120.0
    assert clicks == [cards[0]]

    # A miss at 120.0 is eligible again at 121.0, not at the old 125.0 mark.
    runner._find_portal_offer_cards = lambda _hwnd: None
    monkeypatch.setattr(runner_module.time, "monotonic", lambda: 120.5)
    assert runner._poll_fast_portal_offer(
        1, threading.Event(), 0.0, 120.0) == (False, 120.0)
    monkeypatch.setattr(runner_module.time, "monotonic", lambda: 121.0)
    assert runner._poll_fast_portal_offer(
        1, threading.Event(), 0.0, 120.0) == (False, 121.0)
