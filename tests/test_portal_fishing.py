import threading
from unittest.mock import MagicMock

from core.runner import MacroRunner


def _runner():
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    runner._coords["portal_fishing_spot_x"] = 420
    runner._coords["portal_fishing_spot_y"] = 200
    runner._interruptible_sleep = MagicMock()
    runner._checkpoint = MagicMock(return_value=False)
    return runner


def test_portal_fishing_does_not_toggle_when_rod_is_already_equipped(monkeypatch):
    runner = _runner()
    runner._portal_fishing_icon = MagicMock(return_value={"score": 0.99})
    monkeypatch.setattr("core.runner.vision.ref_to_screen", lambda _hwnd, x, y: (x, y))

    assert runner._start_portal_fishing(1, threading.Event())
    assert [call.args for call in runner._mouse.click.call_args_list] == [(420, 200)]


def test_portal_fishing_enables_then_casts_after_icon_appears(monkeypatch):
    runner = _runner()
    runner._portal_fishing_icon = MagicMock(side_effect=[None, None, {"score": 0.99}])
    monkeypatch.setattr("core.runner.vision.ref_to_screen", lambda _hwnd, x, y: (x, y))

    assert runner._start_portal_fishing(1, threading.Event())
    assert [call.args for call in runner._mouse.click.call_args_list] == [
        (75, 670),
        (420, 200),
    ]


def test_portal_fishing_does_not_cast_without_equipped_confirmation(monkeypatch):
    runner = _runner()
    runner._portal_fishing_icon = MagicMock(return_value=None)
    monkeypatch.setattr("core.runner.vision.ref_to_screen", lambda _hwnd, x, y: (x, y))
    monkeypatch.setattr("core.runner.time.time", MagicMock(side_effect=[0.0, 9.0]))

    assert not runner._start_portal_fishing(1, threading.Event())
    assert [call.args for call in runner._mouse.click.call_args_list] == [(75, 670)]


def test_portal_fishing_uses_configured_spot(monkeypatch):
    runner = _runner()
    runner._coords["portal_fishing_spot_x"] = 512
    runner._coords["portal_fishing_spot_y"] = 234
    runner._portal_fishing_icon = MagicMock(return_value={"score": 0.99})
    monkeypatch.setattr("core.runner.vision.ref_to_screen", lambda _hwnd, x, y: (x, y))

    assert runner._start_portal_fishing(1, threading.Event())
    assert [call.args for call in runner._mouse.click.call_args_list] == [(512, 234)]
