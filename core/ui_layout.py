"""Shared physical-pixel geometry for the fixed-size Windows game viewport."""

from . import config


GAME_TOP = 88
SIDE_PANEL_MIN = 320


def fit_window_rect(x, y, width, height, work_area):
    """Fit app bounds inside a monitor's usable desktop, including its origin."""
    left, top, available_width, available_height = work_area
    width, height = min(width, available_width), min(height, available_height)
    return (max(left, min(x, left + available_width - width)),
            max(top, min(y, top + available_height - height)), width, height)


def centered_game_offset(client_width: int) -> tuple[int, int]:
    """Match the DOM's whole-window horizontal center, rounding down to pixels."""
    return max(0, (int(client_width) - config.FIXED_WIN_W) // 2), GAME_TOP
