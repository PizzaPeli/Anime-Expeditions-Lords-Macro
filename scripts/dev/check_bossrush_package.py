"""Verify the canonical Bossrush executable without launching or focusing Roblox."""
import hashlib
import json
from pathlib import Path
import sys
from types import CodeType

from PyInstaller.archive.readers import CArchiveReader


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def signature(code):
    return (code.co_code, code.co_names, code.co_varnames,
            tuple(signature(c) if isinstance(c, CodeType) else c for c in code.co_consts))


def main():
    exe = ROOT / 'dist/Lords Macro - Anime Expeditions.exe'
    archive = CArchiveReader(str(exe))
    modules = archive.open_embedded_archive('PYZ.pyz')
    checked = ('core.runner', 'core.runner_blocks', 'core.bossrush',
               'core.runner_bossrush', 'core.expedition_vision', 'core.map_capture')
    for module in checked:
        source = ROOT / (module.replace('.', '/') + '.py')
        assert signature(modules.extract(module)) == signature(compile(source.read_bytes(), str(source), 'exec')), module
    resources = ['ui/app.js'] + [f'Paths/defaults/Boss Rush Gate {i}.json' for i in range(1, 7)]
    for resource in resources:
        key = next(k for k in archive.toc if k.replace('\\', '/') == resource)
        assert archive.extract(key) == (ROOT / resource).read_bytes(), resource
    assets = list((ROOT / 'Assets/reference/bossrush').glob('*.png'))
    assets += list((ROOT / 'Assets/ui').glob('bossrush_*/*.png'))
    assets += [ROOT / 'Assets/map_previews/Bossrush/District 7.png',
               ROOT / 'Assets/reference/expedition/20261115/active_elite.png']
    for asset in assets:
        assert asset.read_bytes() == (ROOT / 'dist/Assets' / asset.relative_to(ROOT / 'Assets')).read_bytes(), asset

    from core.image_io import read_image
    scope = {'__name__': 'core.packaged_bossrush_check', '__package__': 'core'}
    exec(modules.extract('core.bossrush'), scope)
    for name, key in [('hub', 'gates'), ('enter', 'enter'), ('start', 'start'),
                      ('card', 'card'), ('decision', 'decision'), ('victory', 'victory')]:
        assert scope['observe'](read_image(ROOT / f'dist/Assets/reference/bossrush/{name}.png'))[key], name
    scope = {'__name__': 'core.packaged_elite_check', '__package__': 'core'}
    exec(modules.extract('core.expedition_vision'), scope)
    failures = ROOT / 'test-output/20261117-044203-404070-Macro2-d4da6e59-closed/debug'
    for name in ('region_expedition_start_stage_unknown.png', 'screen_manual_20261117_044155.png'):
        assert scope['stage'](read_image(failures / name)) == 'defense', name
    report = {
        'packaged_modules_match_source': list(checked),
        'packaged_gate_paths': 6,
        'packaged_capture_checks_passed': True,
        'packaged_elite_detection': 'defense (both Macro2 failure captures)',
        'live_gameplay_verified': False,
        'exe_sha256': hashlib.sha256(exe.read_bytes()).hexdigest(),
        'launcher': 'TEST_BUILD.bat',
    }
    output = ROOT / 'test-output/bossrush-package-check.json'
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
