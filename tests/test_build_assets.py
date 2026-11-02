"""Keep editable vision captures available across local packaged builds."""
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def test_windows_build_deploys_an_exact_fresh_asset_tree():
    script = (REPO / "scripts" / "windows" / "build_exe.bat").read_text(encoding="utf-8")

    build = "%PYTHON_CMD% scripts\\build\\build_pyinstaller.py"
    reset = 'rmdir /S /Q "dist\\Assets"'
    deploy = 'xcopy "Assets" "dist\\Assets\\" /D /E /I /Y /Q'

    assert reset in script
    assert deploy in script
    assert script.index(build) < script.index(reset) < script.index(deploy)


def test_test_build_exports_reviewable_session_evidence():
    script = (REPO / "scripts" / "windows" / "test_build.bat").read_text(encoding="utf-8")

    assert 'set "TEST_PROJECT_ROOT=%CD%"' in script
    command = 'scripts\\windows\\playtest_session.py --dist "%TEST_DIST%" --project "%TEST_PROJECT_ROOT%"'
    assert command in script
    assert command + ' --recover' in script
    launch = script.index(command, script.index('echo Launching %APP_EXE%'))
    assert 'if errorlevel 1 goto export_failed' in script[launch:]
