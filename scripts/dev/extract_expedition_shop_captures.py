"""Preserve November 1 captures and derive Expedition Coin shop references."""
from pathlib import Path
import shutil
import cv2

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "test-output/20261101-153324-573034-Macro1-d0fa726a-closed/debug"
TARGET = ROOT / "Assets/reference/auto_shop/expedition_20261101"


def main():
    TARGET.mkdir(parents=True, exist_ok=True)
    for stamp in ("144737", "144746", "144750", "144758", "144802"):
        filename = f"screen_manual_20261101_{stamp}.png"
        if not (TARGET / filename).exists():
            shutil.copy2(SOURCE / filename, TARGET / filename)

    def crop(stamp, bounds, target):
        frame = cv2.imread(str(TARGET / f"screen_manual_20261101_{stamp}.png"))
        if frame is None:
            raise RuntimeError("Missing source capture")
        x, y, w, h = bounds
        target.parent.mkdir(parents=True, exist_ok=True)
        assert cv2.imwrite(str(target), frame[y:y+h, x:x+w])

    for name, stamp, bounds in (
        ("shop_remote_expedition_card", "144737", (553, 215, 102, 16)),
        ("shop_remote_expedition_header", "144746", (238, 177, 142, 23)),
    ):
        crop(stamp, bounds, ROOT / "Assets/ui" / name / f"{name}.png")
    for key, stamp, cx, cy in (
        ("gem", "144746", 347, 303), ("gold", "144746", 494, 303),
        ("stat_lock", "144746", 643, 303), ("stat_reroll", "144746", 790, 303),
        ("trait_crystal", "144750", 347, 403), ("enhanced_katana", "144750", 494, 403),
        ("equipment_reroll", "144750", 643, 403), ("equipment_lock", "144750", 790, 403),
    ):
        name = "shop_exp_" + key
        crop(stamp, (cx-30, cy-30, 60, 60), ROOT / "Assets/ui" / name / f"{name}.png")
        crop(stamp, (cx-68, cy-25, 140, 110),
             ROOT / "Assets/reference/auto_shop/identities" / ("exp_"+key) / "expedition_20261101.png")


if __name__ == "__main__":
    main()
