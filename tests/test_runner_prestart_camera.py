import threading
from unittest.mock import MagicMock

from core import runner as runner_module
from core.runner import MacroRunner


def _runner():
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    # Isolate _run_prestart to just the camera-setup step under test --
    # Team Loadout/prestart blocks are exercised by their own test files.
    runner._apply_team_loadout = lambda *_a, **_kw: True
    runner._run_prestart_blocks = lambda *_a, **_kw: None
    return runner


def test_camera_settle_runs_before_the_drag(monkeypatch):
    calls = []
    monkeypatch.setattr(runner_module.time, "sleep", lambda _s: None)
    monkeypatch.setattr(
        runner_module.camera, "run_camera_profile",
        lambda *_a, **_kw: calls.append("camera"))

    runner = _runner()
    real_sleep = runner._interruptible_sleep

    def spy_sleep(seconds, stop_event=None):
        calls.append(("settle", seconds))
        return real_sleep(seconds, stop_event)

    runner._interruptible_sleep = spy_sleep

    assert runner._run_prestart(123, threading.Event(), {"mode": "story"}, {}) is True
    assert calls == [("settle", runner_module.CAMERA_SETUP_SETTLE), "camera"]


def test_stop_during_camera_settle_skips_the_drag_immediately(monkeypatch):
    """The settle must stay interruptible -- F2/Stop landing during it must
    not block for the full settle duration nor still run the camera drag."""
    calls = []
    monkeypatch.setattr(
        runner_module.camera, "run_camera_profile",
        lambda *_a, **_kw: calls.append("camera"))

    runner = _runner()
    stop_event = threading.Event()
    stop_event.set()

    assert runner._run_prestart(123, stop_event, {"mode": "story"}, {}) is False
    assert calls == [], "camera setup must not run once Stop has already landed"


def test_identified_map_path_runs_before_macro_even_with_autoplay(monkeypatch):
    from core import map_capture
    monkeypatch.setattr(map_capture, "save_placement_reference", lambda *args, **kwargs: None)
    runner = _runner()
    calls = []
    monkeypatch.setattr(runner_module.camera, "run_camera_profile",
                        lambda *_args: calls.append("camera"))
    runner._run_walk_path_block = lambda *_args: calls.append("path")
    runner._run_prestart_blocks = lambda *_args: calls.append("macro")
    task = {"mode": "story", "map": "New Map", "macro": "Some Macro",
            "auto_play": "autoplay", "_identified_map": True,
            "_map_setup": {"path": "New Map path"}}

    assert runner._run_prestart(123, threading.Event(), task, {}) is True
    assert calls == ["camera", "path", "macro"]


def test_placement_capture_follows_camera_and_skips_replays_and_failures(monkeypatch):
    from core import map_capture
    runner = _runner()
    calls = []
    runner._interruptible_sleep = lambda seconds, *_: calls.append(("settle", seconds))
    monkeypatch.setattr(map_capture, "save_placement_reference",
                        lambda *args, **kwargs: calls.append("capture"))
    monkeypatch.setattr(runner_module.camera, "run_camera_profile",
                        lambda *_: calls.append("camera"))
    task = {"mode": "story", "_map_unknown": True}
    assert runner._run_prestart(123, threading.Event(), task, {}) is True
    assert calls == [("settle", runner_module.CAMERA_SETUP_SETTLE), "camera", ("settle", 0.3), "capture"]
    calls.clear()
    assert runner._run_prestart(123, threading.Event(), task, {}, first_repeat=False) is True
    assert "capture" not in calls
    calls.clear()
    def fail(*_):
        raise RuntimeError("camera unavailable")
    monkeypatch.setattr(runner_module.camera, "run_camera_profile", fail)
    assert runner._run_prestart(123, threading.Event(), task, {}) is True
    assert "capture" not in calls
