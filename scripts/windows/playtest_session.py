"""Run the isolated executable and archive all its data in the source project."""

import argparse
from datetime import datetime
import getpass
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid


EXE_NAME = "Lords Macro - Anime Expeditions.exe"
ASSET_BASELINE = ".playtest-assets.json"
BUILD_RECEIPT = ".playtest-build.json"


def executable_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def sync_executable(dist: Path, project: Path) -> None:
    """Use the canonical build, never a stale per-account executable."""
    source = project.resolve() / "dist" / EXE_NAME
    target = dist.resolve() / EXE_NAME
    if not source.is_file():
        raise ValueError(f"Missing current executable: {source}. Run BUILD_EXE.bat first.")
    if target == source:
        raise ValueError("Test executable must be separate from the canonical build.")
    # Atomic replacement: a failed copy leaves the previous executable intact.
    dist.mkdir(parents=True, exist_ok=True)
    pending = target.with_suffix(".exe.pending")
    try:
        expected = executable_hash(source)
        shutil.copy2(source, pending)
        if executable_hash(pending) != expected or executable_hash(source) != expected:
            raise ValueError("Project executable changed during copying. Wait for OneDrive to finish syncing and retry.")
        pending.replace(target)
    finally:
        pending.unlink(missing_ok=True)
    print(f"Using current build: {source}", flush=True)
    account = re.sub(r"[^A-Za-z0-9_-]", "_", getpass.getuser()) or "user"
    receipt = {
        "account": getpass.getuser(), "sha256": expected,
        "synced_at": datetime.now().astimezone().isoformat(),
        "source": str(source), "target": str(target),
        "source_modified_at": datetime.fromtimestamp(source.stat().st_mtime).astimezone().isoformat(),
    }
    contents = json.dumps(receipt, indent=2)
    (dist / BUILD_RECEIPT).write_text(contents, encoding="utf-8")
    # Publish immediately, so another account can inspect the running test's build.
    reports = project / "test-output" / "builds"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{account}.json").write_text(contents, encoding="utf-8")
    print(f"Verified build ID: {expected[:12]} (SHA-256)\n"
          f"Project executable modified: {receipt['source_modified_at']}", flush=True)


def inventory(root: Path) -> dict:
    """Hashes let the report describe changes without printing private values."""
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != EXE_NAME
    }


def change_log(before: dict, after: dict) -> str:
    lines = []
    for name in sorted(before.keys() | after.keys()):
        if name not in before:
            lines.append(f"Added: {name}")
        elif name not in after:
            lines.append(f"Deleted: {name}")
        elif before[name] != after[name]:
            lines.append(f"Changed: {name}")
    return "\n".join(lines) + "\n" if lines else "No data files changed.\n"


def sync_assets(dist: Path, project: Path) -> None:
    """Update shipped references while retaining this account's private edits."""
    source = project / "Assets"
    if not source.is_dir():
        raise ValueError(f"Missing source Assets folder: {source}")
    assets = dist / "Assets"
    baseline_path = dist / ASSET_BASELINE
    current = inventory(assets)
    shipped = inventory(source)
    baseline = (json.loads(baseline_path.read_text(encoding="utf-8"))
                if baseline_path.exists() else
                {name: digest for name, digest in shipped.items() if name in current})
    # Leave modified/new files alone; remove only unchanged references that
    # disappeared from source. Remember user deletions across later rebuilds.
    for name, digest in shipped.items():
        if name in baseline and current.get(name) != baseline[name]:
            continue
        if name not in baseline and name in current and current[name] != digest:
            continue
        target = assets / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)
    for name in baseline.keys() - shipped.keys():
        if current.get(name) == baseline[name]:
            (assets / name).unlink()
    baseline_path.write_text(json.dumps(shipped, indent=2), encoding="utf-8")


def prepare_session(dist: Path, project: Path, *, fresh: bool) -> None:
    """Archive before any reset. Only mutate the explicit per-account dist."""
    dist, project = dist.resolve(), project.resolve()
    # This launcher owns precisely LocalAppData/LordsMacroTestBuild/dist.
    # Reject ancestor/overlapping source paths before recursive removal.
    if dist.name != "dist" or dist.parent.name != "LordsMacroTestBuild":
        raise ValueError("Expected the per-account LordsMacroTestBuild/dist folder.")
    if dist == project or project in dist.parents or dist in project.parents:
        raise ValueError("Test data must be separate from source files.")
    check_report_access(project)
    report = export_session(dist, project, phase="before-fresh" if fresh else "before-resume")
    if report:
        print(f"Previous setup archived in:\n{report}", flush=True)
    if fresh and dist.exists():
        for path in dist.iterdir():
            if path.name == EXE_NAME:
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    dist.mkdir(parents=True, exist_ok=True)
    sync_assets(dist, project)
    print("Starting fresh." if fresh else "Resuming this Windows account's saved test setup.", flush=True)


def export_session(dist: Path, project: Path, *, phase: str, exit_code=None, before=None) -> Path | None:
    dist, project = dist.resolve(), project.resolve()
    if not dist.is_dir():
        return None
    report_root = project / "test-output"
    if dist == project or dist == report_root or dist in report_root.parents:
        raise ValueError("Test data must be separate from the project and report folders.")
    account = re.sub(r"[^A-Za-z0-9_-]", "_", getpass.getuser()) or "user"
    session = f"{datetime.now():%Y%m%d-%H%M%S-%f}-{account}-{uuid.uuid4().hex[:8]}-{phase}"
    report_root.mkdir(parents=True, exist_ok=True)
    pending = report_root / (session + ".incomplete")
    report = report_root / session
    pending.mkdir()
    # Copy every data file, including future data folders. The executable is
    # reproducible build output; everything else is session evidence.
    # A failed copy leaves its partial archive AND original data for recovery.
    for source in dist.iterdir():
        if source.name == "Lords Macro - Anime Expeditions.exe":
            continue
        target = pending / source.name
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    (pending / "session-info.txt").write_text(
        f"Test session: {session}\nWindows account: {getpass.getuser()}\n"
        f"Source folder: {project}\nTest data folder: {dist}\n"
        f"Archive phase: {phase}\nExecutable exit code: {exit_code}\n",
        encoding="utf-8",
    )
    if before is not None:
        (pending / "changes.txt").write_text(change_log(before, inventory(dist)), encoding="utf-8")
    pending.rename(report)
    return report


def check_report_access(project: Path) -> None:
    """Fail before launching or resetting data if this account cannot export."""
    root = project.resolve() / "test-output"
    root.mkdir(parents=True, exist_ok=True)
    probe = root / ("write-check-" + uuid.uuid4().hex + ".tmp")
    try:
        probe.write_text("playtest export check", encoding="utf-8")
    finally:
        probe.unlink(missing_ok=True)


def run_session(dist: Path, project: Path) -> Path:
    check_report_access(project)
    receipt_path = dist / BUILD_RECEIPT
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        expected = receipt["sha256"]
        if any(executable_hash(path) != expected for path in (
                dist / EXE_NAME, project / "dist" / EXE_NAME)):
            raise ValueError("Build changed after syncing. Close the test and rerun TEST_BUILD.bat after OneDrive finishes syncing.")
    before = inventory(dist)
    exit_code = None
    try:
        exit_code = subprocess.run(
            [str(dist.resolve() / "Lords Macro - Anime Expeditions.exe")],
            cwd=dist.resolve(), check=False,
        ).returncode
    finally:
        report = export_session(dist, project, phase="closed", exit_code=exit_code, before=before)
        if report:
            print(f"All test-session data saved to:\n{report}", flush=True)
    if exit_code:
        print(f"The test executable exited with code {exit_code}; its data was preserved.", flush=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--sync-exe", action="store_true")
    args = parser.parse_args()
    try:
        if args.sync_exe:
            sync_executable(args.dist, args.project)
        elif args.prepare:
            while True:
                answer = input("[R] Resume saved setup (default) / [F] Start fresh: ").strip().lower()
                if answer in ("", "r", "resume", "f", "fresh"):
                    break
                print("Enter R or F, or press Enter to resume.")
            prepare_session(args.dist, args.project, fresh=answer in ("f", "fresh"))
        elif args.recover:
            check_report_access(args.project)
            report = export_session(args.dist, args.project, phase="before-reset")
            if report:
                print(f"Previous test data preserved in:\n{report}", flush=True)
        else:
            run_session(args.dist, args.project)
    except (OSError, ValueError, shutil.Error) as exc:
        print(f"Test setup/export failed: {exc}\n"
              f"Original data remains in {args.dist}. No reset is safe until export succeeds.",
              file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
