import ast
from pathlib import Path
from types import SimpleNamespace
import threading

import pytest

from core import config
from core.ui_layout import centered_game_offset, GAME_TOP


@pytest.mark.parametrize("width", [1152, 1153, 1280, 1712, 1792, 1920, 2560])
def test_centering_preserves_game_coordinates(width, monkeypatch):
    from core import vision
    x, y = centered_game_offset(width)
    assert x == (width - 1152) // 2
    assert y == GAME_TOP == 88
    # Moving the app and centering Roblox must not change reference pixels.
    origin = (120 + x, 75 + y)
    monkeypatch.setattr(vision.wm, "get_client_rect_screen",
                        lambda _: (*origin, origin[0] + 1152, origin[1] + 756))
    saved = (723, 342)
    screen = vision.ref_to_screen(1, *saved)
    assert screen == (origin[0] + saved[0], origin[1] + saved[1])
    assert vision.screen_to_ref(1, *screen) == saved
    assert (config.FIXED_WIN_W, config.FIXED_WIN_H) == (1152, 756)


def resize_api(*, cutout=False, visible=False, stopping=False):
    # Load only the production geometry methods; importing main also sets DPI
    # awareness and other native process state, unnecessary for these checks.
    path = Path(__file__).resolve().parents[1] / "main.py"
    tree = ast.parse(path.read_text(encoding="utf8"))
    api = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Api")
    wanted = {"dock_game_centered", "sync_game_position"}
    methods = [n for n in api.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    module = ast.Module(body=methods, type_ignores=[])
    calls = []
    env = {"wm": SimpleNamespace(get_client_rect_screen=lambda _: (50, 60, 1970, 1140)),
           "centered_game_offset": centered_game_offset, "sys": SimpleNamespace(platform="win32")}
    exec(compile(module, str(path), "exec"), env)
    obj = SimpleNamespace(_game_layout_lock=threading.Lock(),
                          stopping=SimpleNamespace(is_set=lambda: stopping),
                          docker=SimpleNamespace(docked=True, dock=lambda *a, **kw: calls.append((a, kw))),
                          game_hwnd=1, gui_hwnd=2, game_cutout=cutout,
                          _cutout_game_visible=visible)
    obj.dock_game_centered = lambda *args: env["dock_game_centered"](obj, *args)
    return obj, env["sync_game_position"], calls


def test_native_resize_moves_fixed_game_to_new_center():
    api, resize, calls = resize_api()
    resize(api, 1920, 1080)
    assert calls == [((1, 2), {"x": 384, "y": 88})]


def test_resize_does_not_reveal_hidden_cutout_game():
    api, resize, calls = resize_api(cutout=True, visible=False)
    resize(api, 1920, 1080)
    assert calls == []


def test_resize_never_redocks_during_shutdown():
    api, resize, calls = resize_api(stopping=True)
    resize(api, 1920, 1080)
    assert calls == []


def test_square_control_uses_taskbar_aware_windows_maximize():
    from unittest.mock import MagicMock
    path = Path(__file__).resolve().parents[1] / "main.py"
    tree = ast.parse(path.read_text(encoding="utf8"))
    api = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Api")
    method = next(n for n in api.body if isinstance(n, ast.FunctionDef)
                  and n.name == "maximize_window")
    env = {"sys": SimpleNamespace(platform="win32")}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), "exec"), env)
    window = MagicMock()
    obj = SimpleNamespace(_window=window, fit_window_to_work_area=MagicMock())
    env["maximize_window"](obj)
    obj.fit_window_to_work_area.assert_called_once_with(toggle_maximize=True)
    window.toggle_fullscreen.assert_not_called()


@pytest.mark.parametrize("bounds,area,expected", [
    ((0, 0, 1792, 1004), (0, 0, 1920, 952), (0, 0, 1792, 952)),
    ((100, 80, 1792, 1004), (0, 0, 1920, 1032), (100, 28, 1792, 1004)),
    ((0, 0, 1792, 1004), (48, 0, 1872, 1080), (48, 0, 1792, 1004)),
    ((-1800, 20, 1792, 1004), (-1920, 40, 1920, 1040), (-1800, 40, 1792, 1004)),
])
def test_programmatic_bounds_stay_above_taskbar(bounds, area, expected):
    from core.ui_layout import fit_window_rect
    assert fit_window_rect(*bounds, area) == expected
