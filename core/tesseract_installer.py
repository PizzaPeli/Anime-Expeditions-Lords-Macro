"""One-click Tesseract OCR engine install via winget, for Settings' "Install
Tesseract" button -- so someone who hits TesseractNotAvailable doesn't have
to go find/download/run the UB-Mannheim installer by hand.

winget (not a hosted download URL) on purpose: UB-Mannheim's installer
filenames are versioned and change over time with no stable "latest"
download link to hardcode, whereas winget's package id stays constant and
it handles the download/verify/install itself. It also ships preinstalled
on Windows 10 1809+/Windows 11 as "App Installer", so this covers the vast
majority of users this macro already targets (see README's Windows 10/11
requirement) without bundling or downloading anything ourselves.
"""
import os
import shutil
import subprocess

WINGET_PACKAGE_ID = "UB-Mannheim.TesseractOCR"
INSTALL_TIMEOUT = 300.0  # winget downloads ~50MB -- generous for a slow connection

# winget returns 0x8A15002B or 0x8A15002C when the package is already
# installed at its latest version and no update is available. Both the
# unsigned and the sign-extended reading of each code are listed, since which
# one subprocess surfaces as returncode depends on how the exit status is
# interpreted. NOTE: 0x8A15002B and 2316632107 are the SAME number written two
# ways (likewise 0x8A15002C and 2316632084/0x8A150014 etc.).
_NO_UPDATE_APPLICABLE = {
    0x8A15002B, -1978335189, 2316632107,
    0x8A15002C, -1978335188, 2316632108,
    0x8A150014, -1978335212, 2316632084,
}


def install_tesseract(log=None):
    """Blocking -- run this off the UI thread.

    Returns the PATH of a Tesseract that actually runs, or "" if there
    isn't one. Not a bool, and not winget's exit code: winget returning 0
    means winget finished, which is not the same as OCR working. It reported
    "Installed successfully" while every read still failed, because winget
    without admin installs into %LOCALAPPDATA%\\Programs\\Tesseract-OCR and
    puts nothing on PATH -- so the engine was genuinely on disk and genuinely
    unusable. The install is now only called a success once the binary has
    been found and run.

    `log`, if given, is called with progress/result strings (same convention
    as core.updater.check_for_update).
    """
    log = log or (lambda msg: None)

    try:
        subprocess.run(
            ["winget", "--version"], capture_output=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        log("[Tesseract] winget isn't available on this system -- install manually from "
            "https://github.com/UB-Mannheim/tesseract/wiki instead.")
        return _verify(log, "winget is unavailable")

    log("[Tesseract] Installing via winget -- this can take a minute...")
    try:
        result = subprocess.run(
            ["winget", "install", "--id", WINGET_PACKAGE_ID, "-e", "--silent",
             "--accept-package-agreements", "--accept-source-agreements"],
            capture_output=True, text=True, timeout=INSTALL_TIMEOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        log(f"[Tesseract] Install timed out after {INSTALL_TIMEOUT:.0f}s.")
        return _verify(log, "the install timed out")
    except OSError as exc:
        log(f"[Tesseract] Couldn't launch winget: {exc}")
        return _verify(log, f"winget couldn't be launched ({exc})")

    output = (result.stdout or "").strip() or (result.stderr or "").strip()
    output_lower = output.lower()

    # winget returns 0 for a fresh install. 0x8A15002B / 0x8A15002C means "already
    # installed, no update available" -- tesseract.exe is already on disk,
    # so that counts as success too.
    if result.returncode == 0:
        return _verify(log, "winget reported success", installed=True)

    if result.returncode in _NO_UPDATE_APPLICABLE or any(phrase in output_lower for phrase in (
        "pacote existente", "already installed", "no available upgrade",
        "nenhuma atualização disponível", "no upgrade found", "ja instalado", "já instalado"
    )):
        return _verify(log, "winget says it is already installed", installed=True)

    return _verify(log, f"winget exited {result.returncode}: {output or 'no output'}")


def _verify(log, context: str, installed: bool = False) -> str:
    """Did this machine end up with a Tesseract that RUNS?

    The one question that matters, asked the same way whatever winget did.
    core.ocr owns the list of places Windows installs actually land (winget's
    per-user %LOCALAPPDATA% path included), so ask it rather than keeping a
    second copy of that list here to drift out of sync.
    """
    from core import ocr

    ocr.reset_tesseract_cache()
    path = ocr.find_tesseract_binary()
    if path:
        ocr.set_tesseract_cmd(path)
        log(f"[Tesseract] Ready -- verified working at {path}.")
        return path
    if installed:
        log("[Tesseract] winget reported success but no working tesseract.exe could be found "
            "afterwards. Looked in Program Files, Program Files (x86), "
            "%LOCALAPPDATA%\\Programs\\Tesseract-OCR and on PATH. Install it by hand from "
            "https://github.com/UB-Mannheim/tesseract/wiki and it will be picked up "
            "automatically.")
    else:
        log(f"[Tesseract] Not installed ({context}), and no existing tesseract.exe was found. "
            "Install it from https://github.com/UB-Mannheim/tesseract/wiki.")
    return ""
