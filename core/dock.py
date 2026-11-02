import sys
import threading
import time

from . import window as wm
from . import config


if sys.platform == "darwin":

    class GameDocker:
        """macOS 'docking': arrange, don't embed. macOS flatly cannot
        reparent another app's window (no SetParent equivalent exists), so
        instead of Roblox rendering INSIDE the app like on Windows, the
        game window is resized to the exact same fixed content size
        (config.FIXED_WIN_W/H, in points -- so every fixed coordinate and
        reference image works identically) and parked at the screen
        position main's watchdog asks for, right beside the control
        panel. The watchdog re-calls dock() periodically, which re-asserts
        position/size if the user dragged or resized the game -- the
        arrangement equivalent of a child window that can't drift.

        Same public surface as the Windows docker (dock/undock/docked/
        lock) so main.py's call sites stay platform-blind; x/y here are
        SCREEN coordinates for the game window rather than client offsets
        inside a parent, which is what main's darwin branch passes.
        """

        def __init__(self):
            self.docked = False
            self._lock = threading.Lock()

        def dock(self, game_hwnd: int, gui_hwnd: int, x: int = 0, y: int = 0,
                  width: int = config.FIXED_WIN_W, height: int = config.FIXED_WIN_H) -> None:
            if not game_hwnd or not wm.is_window(game_hwnd):
                return
            with self._lock:
                outer_w, outer_h = wm.client_size_to_window_size(game_hwnd, width, height)
                wm.move_window(game_hwnd, x, y, outer_w, outer_h)
                self.docked = True

        def undock(self, game_hwnd: int, x: int = 100, y: int = 100,
                    width: int = config.FIXED_WIN_W, height: int = config.FIXED_WIN_H) -> bool:
            # Nothing to detach -- the game was never parented to anything.
            # Leave it exactly where it is (moving it away on quit would
            # just be surprising) and report success so close paths never
            # warn about a detach that has no meaning here.
            with self._lock:
                self.docked = False
                return True

else:

    class GameDocker:
        """Arrange Roblox as an independent borderless window; never reparent it."""

        def __init__(self):
            self.docked = False
            self.cutout = True  # compatibility name for standalone arrangement
            self._lock = threading.Lock()

        def dock(self, game_hwnd: int, gui_hwnd: int, x: int = 0, y: int = 0,
                 width: int = config.FIXED_WIN_W, height: int = config.FIXED_WIN_H) -> None:
            if not game_hwnd or not wm.is_window(game_hwnd):
                return
            with self._lock:
                if not self.docked:
                    wm.set_always_on_top(game_hwnd, False)
                    wm.remove_borders(game_hwnd)
                    self.docked = True
                if wm.is_minimized(gui_hwnd):
                    wm.hide_window(game_hwnd)
                    return
                left, top, _, _ = wm.get_client_rect_screen(gui_hwnd)
                outer_w, outer_h = wm.client_size_to_window_size(game_hwnd, width, height)
                wm.place_above_window(game_hwnd, gui_hwnd, left + x, top + y, outer_w, outer_h)

        def undock(self, game_hwnd: int, x: int = 100, y: int = 100,
                   width: int = config.FIXED_WIN_W, height: int = config.FIXED_WIN_H) -> bool:
            with self._lock:
                if game_hwnd and wm.is_window(game_hwnd):
                    wm.set_always_on_top(game_hwnd, False)
                    wm.restore_borders(game_hwnd)
                    outer_w, outer_h = wm.client_size_to_window_size(game_hwnd, width, height)
                    wm.move_window(game_hwnd, x, y, outer_w, outer_h)
                    wm.show_window(game_hwnd)
                    wm.activate_window(game_hwnd)
                self.docked = False
                return True
