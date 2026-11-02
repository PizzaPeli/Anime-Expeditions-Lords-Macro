import base64
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from core import maps
from core.runner import MacroRunner
from main import Api
import main


@pytest.mark.parametrize('task,label', [
    ({'mode': 'story', 'is_challenge': True, 'challenge_slot': '1'}, 'Challenge #1'),
    ({'mode': 'story', 'is_challenge': True, 'challenge_slot': '3'}, 'Challenge #3'),
    ({'mode': 'story', 'is_challenge': True, 'is_daily_challenge': True}, 'Daily Challenge'),
    ({'mode': 'expedition'}, None),
    ({}, None),
])
def test_history_persists_match_identity(monkeypatch, task, label):
    data = {'run_history': [{'result': 'win', 'map': 'Old run', 'at': 1}]}
    monkeypatch.setattr(main.cfg, 'load', lambda: data.copy())
    monkeypatch.setattr(main.cfg, 'update', lambda updates: data.update(updates))
    api = Api.__new__(Api)
    api._session_wins = api._session_losses = 0
    api._run_status = {}
    api.docker = MagicMock(docked=False)
    api.get_challenge_settings = lambda: {}
    api._record_match_result('win', 'School Grounds', '1m 19s', task)
    row = data['run_history'][0]
    assert row['challenge'] == label
    assert row['mode'] == ('challenge' if label else task.get('mode'))
    assert data['all_time_wins'] == 1
    status = api.get_status()
    assert status['run_history'][0]['challenge'] == label
    assert status['run_history'][1]['challenge'] is None


def test_background_result_forwards_task_identity():
    callback = MagicMock()
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock(), record_result=callback)
    runner._send_result_webhook = MagicMock()
    task = {'is_challenge': True, 'challenge_slot': '3'}
    runner._finish_match_result_background('win', 'East Town', '79s', task, {})
    callback.assert_called_once_with('win', 'East Town', '79s', task)


def capture_uri(width=1152, height=756):
    ok, png = cv2.imencode('.png', np.zeros((height, width, 3), np.uint8))
    assert ok
    return 'data:image/png;base64,' + base64.b64encode(png).decode('ascii')


def test_replacing_single_default_preserves_shipped_reference(monkeypatch, tmp_path):
    shipped = tmp_path / 'dataset'
    (shipped / 'Expedition').mkdir(parents=True)
    old = shipped / 'Expedition' / 'Expedition.png'
    shipped_uri = capture_uri()
    old.write_bytes(base64.b64decode(shipped_uri.split(',')[1]))
    monkeypatch.setattr(maps, 'MAPS_DIR', str(shipped))
    monkeypatch.setattr(maps, 'EXPEDITION_SCREENS_DIR', str(tmp_path / 'screens'))
    assert 'Expedition' in maps.list_categories()
    assert maps.list_maps('Expedition') == ['Expedition']
    assert maps.map_image_data_uri('Expedition', 'Expedition') == shipped_uri
    uri = capture_uri()
    maps.save_expedition_screen('School Grounds', uri)
    assert maps.list_maps('Expedition') == ['Expedition']
    assert maps.map_image_data_uri('Expedition', 'School Grounds') == uri
    assert old.read_bytes() == base64.b64decode(shipped_uri.split(',')[1])
    maps.save_expedition_screen('School Grounds', uri)
    assert maps.list_maps('Expedition') == ['Expedition']


@pytest.mark.parametrize('name,uri', [('../escape', None), ('', None), ('School Grounds', 'invalid'),
                                      ('School Grounds', 'data:image/png;base64,bad!')])
def test_invalid_screens_are_rejected(monkeypatch, tmp_path, name, uri):
    monkeypatch.setattr(maps, 'EXPEDITION_SCREENS_DIR', str(tmp_path / 'screens'))
    with pytest.raises(ValueError):
        maps.save_expedition_screen(name, uri or capture_uri())
    assert not (tmp_path / 'screens').exists()


def test_wrong_coordinate_size_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(maps, 'EXPEDITION_SCREENS_DIR', str(tmp_path / 'screens'))
    with pytest.raises(ValueError):
        maps.save_expedition_screen('School Grounds', capture_uri(576, 378))


def test_shipped_expedition_reference_available_until_user_overrides_it(monkeypatch, tmp_path):
    shipped = tmp_path / 'dataset' / 'Expedition'
    shipped.mkdir(parents=True)
    shipped_uri = capture_uri()
    (shipped / 'School Grounds.png').write_bytes(base64.b64decode(shipped_uri.split(',')[1]))
    (shipped / 'Expedition.png').write_bytes(base64.b64decode(shipped_uri.split(',')[1]))
    monkeypatch.setattr(maps, 'MAPS_DIR', str(shipped.parent))
    monkeypatch.setattr(maps, 'EXPEDITION_SCREENS_DIR', str(tmp_path / 'screens'))
    assert maps.list_maps('Expedition') == ['Expedition']
    assert maps.map_image_data_uri('Expedition', 'School Grounds') == shipped_uri
    image = np.full((756, 1152, 3), 255, np.uint8)
    _, png = cv2.imencode('.png', image)
    custom_uri = 'data:image/png;base64,' + base64.b64encode(png).decode('ascii')
    maps.save_expedition_screen('School Grounds', custom_uri)
    assert maps.list_maps('Expedition') == ['Expedition']
    assert maps.map_image_data_uri('Expedition', 'School Grounds') == custom_uri


def test_every_expedition_map_uses_the_updated_default(monkeypatch, tmp_path):
    from pathlib import Path
    dataset = Path(__file__).resolve().parents[1] / 'Assets/map_previews'
    monkeypatch.setattr(maps, 'MAPS_DIR', str(dataset))
    monkeypatch.setattr(maps, 'EXPEDITION_SCREENS_DIR', str(tmp_path / 'screens'))
    archived = dataset.parent / 'reference/expedition/20261031/screen_manual_20261031_135059.png'
    expected = 'data:image/png;base64,' + base64.b64encode(archived.read_bytes()).decode('ascii')
    assert maps.list_maps('Expedition') == ['Expedition']
    for name in ('Expedition', 'School Grounds', 'Rose Kingdom', 'East Town'):
        assert maps.map_image_data_uri('Expedition', name) == expected
    # Old map-specific overrides must not silently replace the default.
    personal = tmp_path / 'screens'
    personal.mkdir()
    (personal / 'School Grounds.png').write_bytes(b'obsolete map-specific image')
    assert maps.map_image_data_uri('Expedition', 'School Grounds') == expected
