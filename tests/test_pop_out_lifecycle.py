from unittest.mock import MagicMock

from main import Api


def test_closing_pop_outs_keeps_main_window_open():
    api = Api.__new__(Api)
    api._window = MagicMock()
    api._log_window = MagicMock()
    api._wave_window = MagicMock()
    api._mouse_position_window = MagicMock()
    children = (api._log_window, api._wave_window, api._mouse_position_window)

    api.close_pop_out_windows()

    for child in children:
        child.destroy.assert_called_once_with()
    api._window.destroy.assert_not_called()
    assert all(getattr(api, name) is None for name in (
        "_log_window", "_wave_window", "_mouse_position_window"))

    api.close_pop_out_windows()  # Repeated main close paths are harmless.
    for child in children:
        child.destroy.assert_called_once_with()
