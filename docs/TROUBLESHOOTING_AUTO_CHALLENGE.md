# Troubleshooting Auto Challenge

Auto Challenge in v0.19.1 (the compiled `Lords Macro - Anime Expeditions.exe`
distribution shipped in `Lords-Macro-Anime-Expeditions-Windows/`) will refuse
to run until BOTH conditions below are true. This is not a code bug — the
runner is deliberately strict so it doesn't burn attempts on an unconfigured
setup. The state is stored in `settings.json` and re-checked every time the
loop tries to start.

## Root cause seen in your build

Reading `Lords-Macro-Anime-Expeditions-Windows/settings.json`:

```json
"challenge": {
    "enabled": false,
    "setup_ready": false,
    "missing_maps": [
        "School Grounds", "Rose Kingdom", "Fairy King Forest",
        "King's Tomb", "Flower Forest", "East Town"
    ],
    "maps": {
        "School Grounds":    { "macro": "" },
        "Rose Kingdom":      { "macro": "" },
        "Fairy King Forest": { "macro": "" },
        "King's Tomb":       { "macro": "" },
        "Flower Forest":     { "macro": "" },
        "East Town":         { "macro": "" }
    }
}
```

Every map's `macro` field is empty, so `missing_maps` contains all six and
`setup_ready` is `false`. `challenge.enabled` is also `false`. Auto Challenge
needs at least one map bound to a saved macro template AND its own
enable toggle on — otherwise the runner logs `Backing out after failed map
search...` (which you can see in `debug.log` at 03:22:25 and 03:35:44).

## Fix

1. **Create the macro template you want Auto Challenge to run**
   - Open the block editor and build (or Load Example) the run you want.
   - `File > Save As...` and pick a name, e.g. `Story - default`.

2. **Bind that template to at least one story map**
   - `Settings > Play > Auto Challenge > Maps`.
   - For each story map you want Auto Challenge to cover, click its
     `Macro` cell and pick the saved template.
   - Save. `settings.json`'s `challenge.missing_maps` will shrink and
     `setup_ready` will flip to `true`.

3. **Enable Auto Challenge**
   - Same panel: turn `challenge.enabled` on.
   - Set `cap` (max stages per rotation) if you want a limit lower than 10.

4. **Run** — Auto Challenge will now enter each configured map's Challenge
   stage using the template you bound to it.

## The secondary OCR warning (not the actual blocker)

`debug.log` also shows repeated `[Health] FAIL Text reading (OCR) --
Windows OCR unavailable ...; Tesseract failed: Tesseract OCR engine not
found`. That is a background health-check, not the reason Auto Challenge
won't start. It only affects the code paths that need OCR:

- Auto Bounty wave-number reading
- Stats / reward reading
- Wait-for-Wave (if you use it as a Battle block)

Auto Challenge itself uses image matching for map detection first, and
only falls back to OCR when image matching fails. Fix it if you want the
OCR-dependent features to work reliably:

- `Settings > General > Install Tesseract` — the built-in installer will
  fetch and configure the Windows Tesseract build automatically (see
  `core/tesseract_installer.py`).
- OR: install the RapidOCR extras from `requirements-rapidocr.txt` if
  you're running from source.
- OR: rebuild the .exe with the `winsdk`/`winrt` packages collected by
  PyInstaller (v0.19.0's build script already sets this up — see the
  0.19.0 CHANGELOG entry; the compiled build you have may predate that
  fix).

## Verifying the fix

After binding a template and enabling Auto Challenge, `debug.log` should
show `Challenge map detected: "<map>" (score X.XX)` on the next run
instead of `Backing out after failed map search...`.

If it still logs "failed map search" *after* setup, the map reference
image itself is off (game visual update). Open `Settings > Debug > Image
Manager`, retake the affected map's `Assets/ui/<Map Name>/*.png` from the
live Challenge screen, and rerun.
