import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/windows/playtest_session.py"
spec = importlib.util.spec_from_file_location("playtest_session", SCRIPT)
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)


def make_data(tmp_path):
    dist = tmp_path / "Macro1" / "dist"
    dist.mkdir(parents=True)
    files = {
        "debug/screen_manual.png": b"screenshot pixels",
        "debug/unrecognized_maps/map_miss_test.png": b"unknown map pixels",
        "debug/unrecognized_maps/map_miss_test.json": b'{"mode": "raid"}',
        "settings.json": b'{"tasks": [1]}',
        "Templates/test.json": b"template",
        "Recordings/input.json": b"recording",
        "Paths/new.json": b"movement",
        "placement_screens/Expedition/School Grounds.png": b"placement pixels",
        "Assets/custom.png": b"custom reference",
        "camera_profiles.json": b"camera",
        "new-data-folder/future.txt": b"future data",
        "debug.log": b"log",
    }
    for name, content in files.items():
        path = dist / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (dist / "Lords Macro - Anime Expeditions.exe").write_bytes(b"binary")
    return dist, tmp_path / "shared project", files


def test_export_includes_all_data_in_launching_project(tmp_path, monkeypatch):
    dist, project, files = make_data(tmp_path)
    monkeypatch.setattr(session.getpass, "getuser", lambda: "Macro1")
    first = session.export_session(dist, project, phase="closed", exit_code=0)
    second = session.export_session(dist, project, phase="closed", exit_code=0)
    assert first != second
    assert first.parent == project / "test-output"
    assert "Macro1" in first.name
    for name, content in files.items():
        assert (first / name).read_bytes() == content
        assert (dist / name).read_bytes() == content
    assert not (first / "Lords Macro - Anime Expeditions.exe").exists()
    assert "Windows account: Macro1" in (first / "session-info.txt").read_text()


def test_failed_export_keeps_source_and_marks_incomplete(tmp_path, monkeypatch):
    dist, project, files = make_data(tmp_path)
    monkeypatch.setattr(session.shutil, "copy2", lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("denied")))
    with pytest.raises((OSError, session.shutil.Error)):
        session.export_session(dist, project, phase="closed")
    assert all((dist / name).read_bytes() == content for name, content in files.items())
    assert all(path.name.endswith(".incomplete") for path in (project / "test-output").iterdir())


@pytest.mark.parametrize("exit_code", [0, 1, 255])
def test_run_waits_for_exit_before_exporting_even_after_crash(tmp_path, monkeypatch, exit_code):
    dist, project, files = make_data(tmp_path)

    def run(command, cwd, check):
        assert command == [str(dist / "Lords Macro - Anime Expeditions.exe")]
        assert cwd == dist
        (dist / "written-at-exit.txt").write_text("last data")
        return SimpleNamespace(returncode=exit_code)

    monkeypatch.setattr(session.subprocess, "run", run)
    report = session.run_session(dist, project)
    assert (report / "written-at-exit.txt").read_text() == "last data"
    assert f"Executable exit code: {exit_code}" in (report / "session-info.txt").read_text()


def test_unwritable_project_prevents_launch(tmp_path, monkeypatch):
    dist, project, _ = make_data(tmp_path)
    monkeypatch.setattr(session, "check_report_access", lambda *args: (_ for _ in ()).throw(PermissionError("denied")))
    monkeypatch.setattr(session.subprocess, "run", lambda *args, **kwargs: pytest.fail("must not launch"))
    with pytest.raises(PermissionError):
        session.run_session(dist, project)


def test_archive_cannot_recurse_into_itself(tmp_path):
    with pytest.raises(ValueError):
        session.export_session(tmp_path, tmp_path, phase="closed")


def test_launcher_checks_preparation_before_syncing_current_build():
    source = SCRIPT.with_name("test_build.bat").read_text()
    prepare = source.index('--prepare')
    sync = source.index('--sync-exe')
    assert prepare < source.index("if errorlevel 1 goto export_failed", prepare) < sync
    assert 'build_pyinstaller.py' not in source
    assert 'pip install' not in source
    assert 'start "" /WAIT' not in source


def prepare_data(tmp_path):
    dist = tmp_path / "account" / "LordsMacroTestBuild" / "dist"
    project = tmp_path / "project"
    (project / "Assets").mkdir(parents=True)
    (project / "Assets/default.png").write_bytes(b"shipped")
    dist.mkdir(parents=True)
    return dist, project


def test_resume_preserves_complete_setup_and_updates_shipped_assets(tmp_path):
    dist, project = prepare_data(tmp_path)
    session.prepare_session(dist, project, fresh=False)
    for name in ("settings.json", "Templates/Tasks/preset.json", "Recordings/a.json",
                 "placement_screens/ref.png", "Paths/walk.json", "future/data.json"):
        path = dist / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("private")
    (project / "Assets/default.png").write_bytes(b"updated")
    session.prepare_session(dist, project, fresh=False)
    assert (dist / "settings.json").read_text() == "private"
    assert (dist / "future/data.json").read_text() == "private"
    assert (dist / "Assets/default.png").read_bytes() == b"updated"
    assert not (project / "settings.json").exists()


def test_private_asset_edits_and_deletions_survive_rebuilds(tmp_path):
    dist, project = prepare_data(tmp_path)
    (project / "Assets/deleted.png").write_bytes(b"delete me")
    session.prepare_session(dist, project, fresh=False)
    (dist / "Assets/default.png").write_bytes(b"private edit")
    (dist / "Assets/deleted.png").unlink()
    (dist / "Assets/custom.png").write_bytes(b"custom")
    (project / "Assets/default.png").write_bytes(b"new source")
    session.prepare_session(dist, project, fresh=False)
    assert (dist / "Assets/default.png").read_bytes() == b"private edit"
    assert not (dist / "Assets/deleted.png").exists()
    assert (dist / "Assets/custom.png").read_bytes() == b"custom"
    assert (project / "Assets/default.png").read_bytes() == b"new source"


def test_fresh_archives_everything_then_resets_only_test_data(tmp_path):
    dist, project = prepare_data(tmp_path)
    (dist / "settings.json").write_text('{"tasks": [1]}')
    (dist / session.EXE_NAME).write_bytes(b"exe")
    session.prepare_session(dist, project, fresh=True)
    assert not (dist / "settings.json").exists()
    assert (dist / session.EXE_NAME).read_bytes() == b"exe"
    assert (dist / "Assets/default.png").read_bytes() == b"shipped"
    reports = list((project / "test-output").glob("*-before-fresh"))
    assert (reports[0] / "settings.json").read_text() == '{"tasks": [1]}'


def test_failed_archive_prevents_fresh_reset(tmp_path, monkeypatch):
    dist, project = prepare_data(tmp_path)
    (dist / "settings.json").write_text("private")
    monkeypatch.setattr(session, "export_session", lambda *a, **k: (_ for _ in ()).throw(PermissionError()))
    with pytest.raises(PermissionError):
        session.prepare_session(dist, project, fresh=True)
    assert (dist / "settings.json").read_text() == "private"


def test_accounts_keep_independent_data(tmp_path):
    dist, project = prepare_data(tmp_path)
    other = tmp_path / "other" / "LordsMacroTestBuild/dist"
    other.mkdir(parents=True)
    (other / "settings.json").write_text("other account")
    session.prepare_session(dist, project, fresh=True)
    assert (other / "settings.json").read_text() == "other account"


def test_close_report_lists_changes_without_private_values(tmp_path, monkeypatch):
    dist, project = prepare_data(tmp_path)
    (dist / "settings.json").write_text("before")
    def run(*a, **k):
        (dist / "settings.json").write_text("secret webhook")
        (dist / "new.txt").write_text("new")
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(session.subprocess, "run", run)
    report = session.run_session(dist, project)
    changes = (report / "changes.txt").read_text()
    assert "Changed: settings.json" in changes
    assert "Added: new.txt" in changes
    assert "secret webhook" not in changes


@pytest.mark.parametrize("answer,fresh", [("", False), ("r", False), ("f", True)])
def test_prompt_defaults_to_resume(tmp_path, monkeypatch, answer, fresh):
    monkeypatch.setattr("builtins.input", lambda prompt: answer)
    monkeypatch.setattr(session.sys, "argv", ["playtest_session.py", "--dist", str(tmp_path / "dist"),
                                           "--project", str(tmp_path / "project"), "--prepare"])
    calls = []
    monkeypatch.setattr(session, "prepare_session", lambda d, p, **kw: calls.append(kw))
    assert session.main() == 0
    assert calls == [{"fresh": fresh}]


def test_release_archive_excludes_test_and_personal_data(tmp_path, monkeypatch):
    import zipfile
    spec = importlib.util.spec_from_file_location("release_package", SCRIPT.parents[1] / "build/package_windows_release.py")
    package = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package)
    dist = tmp_path / "dist"
    dist.mkdir()
    assets = tmp_path / "Assets"
    assets.mkdir()
    (assets / "shipped.png").write_bytes(b"reference")
    (dist / session.EXE_NAME).write_bytes(b"binary")
    for name in ("settings.json", session.ASSET_BASELINE, "Templates/private.json", "test-output/session/settings.json"):
        path = dist / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("personal")
    monkeypatch.setattr(package, "DIST", dist)
    monkeypatch.setattr(package, "EXE", dist / session.EXE_NAME)
    monkeypatch.setattr(package, "ASSETS", assets)
    monkeypatch.setattr(package, "OUTPUT", dist / "release.zip")
    package.main()
    with zipfile.ZipFile(package.OUTPUT) as archive:
        assert set(archive.namelist()) == {session.EXE_NAME, "Assets/shipped.png"}


def test_launcher_does_not_promote_private_data_to_source():
    source = SCRIPT.with_name("test_build.bat").read_text()
    assert 'xcopy "%TEST_DIST%' not in source
    assert 'del /F /Q "%TEST_DIST%\\settings.json"' not in source


def test_sync_uses_current_exe_and_preserves_account_data(tmp_path):
    import json
    dist, project = prepare_data(tmp_path)
    source = project / "dist" / session.EXE_NAME
    source.parent.mkdir()
    source.write_bytes(b"current build")
    (dist / session.EXE_NAME).write_bytes(b"old build")
    (dist / "settings.json").write_text("private tasks")
    (dist / "Assets").mkdir()
    (dist / "Assets/custom.png").write_bytes(b"private reference")
    session.sync_executable(dist, project)
    assert (dist / session.EXE_NAME).read_bytes() == b"current build"
    assert (dist / "settings.json").read_text() == "private tasks"
    assert (dist / "Assets/custom.png").read_bytes() == b"private reference"
    receipt = json.loads((dist / session.BUILD_RECEIPT).read_text())
    assert receipt["sha256"] == session.executable_hash(source)
    assert list((project / "test-output/builds").glob("*.json"))


def test_corrupt_sync_preserves_previous_executable(tmp_path, monkeypatch):
    dist, project = prepare_data(tmp_path)
    source = project / "dist" / session.EXE_NAME
    source.parent.mkdir()
    source.write_bytes(b"current build")
    target = dist / session.EXE_NAME
    target.write_bytes(b"previous build")
    monkeypatch.setattr(session.shutil, "copy2", lambda src, dst: dst.write_bytes(b"incomplete"))
    with pytest.raises(ValueError, match="OneDrive"):
        session.sync_executable(dist, project)
    assert target.read_bytes() == b"previous build"


def test_build_replaced_after_sync_is_not_launched(tmp_path, monkeypatch):
    dist, project = prepare_data(tmp_path)
    source = project / "dist" / session.EXE_NAME
    source.parent.mkdir()
    source.write_bytes(b"current build")
    session.sync_executable(dist, project)
    (dist / session.EXE_NAME).write_bytes(b"stale replacement")
    monkeypatch.setattr(session.subprocess, "run", lambda *a, **kw: pytest.fail("must not launch"))
    with pytest.raises(ValueError, match="Build changed"):
        session.run_session(dist, project)


def test_sync_missing_canonical_exe_does_not_launch_stale_build(tmp_path):
    dist, project = prepare_data(tmp_path)
    (dist / session.EXE_NAME).write_bytes(b"old build")
    with pytest.raises(ValueError, match="BUILD_EXE.bat"):
        session.sync_executable(dist, project)
    assert (dist / session.EXE_NAME).read_bytes() == b"old build"
