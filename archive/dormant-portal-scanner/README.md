# Dormant portal card reader

This folder preserves the former OCR-based portal card reader. The active
Portal route searches for a requested name in the game UI and selects the
first result; it did not call the card-reading code or pass its calibration
settings into the runner. The active route remains in `core/runner.py`.
