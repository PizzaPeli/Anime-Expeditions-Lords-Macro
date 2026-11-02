from unittest.mock import MagicMock

from core import dock


def test_standalone_never_reparents_and_follows_client_origin(monkeypatch):
    wm = MagicMock()
    wm.is_window.return_value = True
    wm.is_minimized.return_value = False
    wm.get_client_rect_screen.return_value = (50, 60, 1970, 1140)
    wm.client_size_to_window_size.return_value = (1152, 756)
    monkeypatch.setattr(dock, "wm", wm)
    docker = dock.GameDocker()
    docker.dock(1, 2, 384, 88)
    wm.place_above_window.assert_called_once_with(1, 2, 434, 148, 1152, 756)
    wm.set_parent.assert_not_called()
    wm.set_always_on_top.assert_called_once_with(1, False)
    wm.is_minimized.return_value = True
    docker.dock(1, 2, 384, 88)
    wm.hide_window.assert_called_once_with(1)
    assert wm.place_above_window.call_count == 1
    wm.is_minimized.return_value = False
    docker.dock(1, 2, 384, 88)
    assert wm.place_above_window.call_count == 2
    assert docker.undock(1)
    wm.restore_borders.assert_called_once_with(1)
    wm.show_window.assert_called_once_with(1)
    wm.set_parent.assert_not_called()
    assert not docker.docked



def test_dialog_visibility_is_preserved_during_resize():
    import ast
    import sys
    import threading
    from pathlib import Path
    from types import SimpleNamespace
    from core.ui_layout import centered_game_offset

    path = Path(__file__).resolve().parents[1] / "main.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    api = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Api")
    names = {"show_game", "hide_game", "sync_game_position", "dock_game_centered"}
    methods = [n for n in api.body if isinstance(n, ast.FunctionDef) and n.name in names]
    wm = MagicMock()
    wm.is_window.return_value = True
    wm.get_client_rect_screen.return_value = (50, 60, 1970, 1140)
    env = dict(wm=wm, sys=sys, centered_game_offset=centered_game_offset)
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(path), "exec"), env)
    obj = SimpleNamespace(game_cutout=True, _cutout_game_visible=True,
                          game_hwnd=1, gui_hwnd=2, docker=MagicMock(docked=True),
                          stopping=threading.Event(), _game_layout_lock=threading.Lock())
    obj.dock_game_centered = lambda *args: env["dock_game_centered"](obj, *args)
    env["hide_game"](obj)
    wm.hide_window.assert_called_once_with(1)
    env["sync_game_position"](obj)
    obj.docker.dock.assert_not_called()
    assert not obj._cutout_game_visible
    env["show_game"](obj)
    obj.docker.dock.assert_called_once_with(1, 2, x=384, y=88)
    assert obj._cutout_game_visible
