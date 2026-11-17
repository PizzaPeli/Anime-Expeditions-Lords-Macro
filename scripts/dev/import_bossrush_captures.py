"""Import the creator's District 7 recordings and measured UI reference crops."""
import json
from pathlib import Path
import shutil

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
SESSION = ROOT / 'test-output/20261117-044215-664604-Macro1-62eabdb5-closed'


def main():
    references = ROOT / 'Assets/reference/bossrush'
    references.mkdir(parents=True, exist_ok=True)
    captures = {
        'menu': '042148', 'district': '042200', 'party': '042210',
        'hub': '042426', 'enter': '042552', 'start': '042601',
        'card': '042711', 'decision': '043007', 'victory': '044134',
    }
    for label, stamp in captures.items():
        shutil.copy2(SESSION / f'debug/screen_manual_20261117_{stamp}.png', references / f'{label}.png')
    # Crops contain stable labels, excluding countdowns, scenery and portraits.
    crops = {
        'bossrush_mode': ('menu', (531, 234, 625, 254)),
        'bossrush_district': ('district', (271, 85, 384, 111)),
        'bossrush_select_stage': ('district', (323, 717, 403, 735)),
        'bossrush_matchmaking': ('district', (528, 717, 647, 735)),
        'bossrush_card': ('card', (520, 131, 633, 175)),
        'bossrush_decision': ('decision', (519, 106, 635, 122)),
        'bossrush_continue': ('decision', (484, 212, 549, 229)),
        'bossrush_fight': ('decision', (602, 212, 672, 229)),
        'bossrush_gate': ('enter', (281, 398, 418, 415)),
        'bossrush_enter': ('enter', (589, 384, 667, 407)),
        'bossrush_boss_health': ('enter', (333, 68, 445, 85)),
    }
    for name, (label, box) in crops.items():
        folder = ROOT / 'Assets/ui' / name
        folder.mkdir(parents=True, exist_ok=True)
        Image.open(references / f'{label}.png').crop(box).save(folder / f'{name}.png')
    preview = ROOT / 'Assets/map_previews/Bossrush'
    preview.mkdir(parents=True, exist_ok=True)
    shutil.copy2(references / 'hub.png', preview / 'District 7.png')
    for gate in range(1, 7):
        name = f'Boss Rush Gate {gate}.json'
        source = SESSION / 'Paths' / name
        data = json.loads(source.read_text(encoding='utf-8'))
        assert data['events'], name
        shutil.copy2(source, ROOT / 'Paths/defaults' / name)


if __name__ == '__main__':
    main()
