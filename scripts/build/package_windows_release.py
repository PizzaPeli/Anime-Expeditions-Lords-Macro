"""Create the same Windows release archive locally and in GitHub Actions."""

from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"
EXE = DIST / "Lords Macro - Anime Expeditions.exe"
ASSETS = ROOT / "Assets"
OUTPUT = DIST / "Lords-Macro-Anime-Expeditions-Windows.zip"


def main() -> None:
    if not EXE.is_file():
        raise SystemExit(f"Missing built executable: {EXE}")
    if not ASSETS.is_dir():
        raise SystemExit(f"Missing editable assets: {ASSETS}")

    # Archive the canonical inputs directly; an old staging folder may be
    # locked by OneDrive or a different Windows test account.
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(EXE, EXE.name)
        for path in sorted(ASSETS.rglob("*")):
            if path.is_file():
                archive.write(path, Path("Assets") / path.relative_to(ASSETS))
    print(f"Packaged {OUTPUT}")


if __name__ == "__main__":
    main()
