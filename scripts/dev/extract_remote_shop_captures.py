"""Extract navigation templates from the October 2026 remote-shop captures."""
from pathlib import Path

import cv2


ROOT = Path(__file__).resolve().parents[2]
CAPTURES = ROOT / "Assets/reference/auto_shop/remote_20261031"


def main():
    crops = {
        "shop_remote_menu": ("142647", (225, 23, 23, 23)),
        "shop_remote_all_shops": ("142652", (237, 186, 116, 28)),
        "shop_remote_restocking": ("142701", (232, 347, 94, 20)),
        "shop_remote_gold_card": ("142709", (737, 214, 66, 16)),
        "shop_remote_header": ("142814", (237, 177, 88, 22)),
        "shop_remote_close": ("142814", (896, 175, 22, 22)),
    }
    for name, (stamp, (x, y, width, height)) in crops.items():
        source = CAPTURES / f"screen_manual_20261031_{stamp}.png"
        image = cv2.imread(str(source))
        if image is None:
            raise RuntimeError(f"Cannot read {source}")
        target = ROOT / "Assets/ui" / name / f"{name}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(target), image[y:y + height, x:x + width]):
            raise RuntimeError(f"Cannot write {target}")


if __name__ == "__main__":
    main()
