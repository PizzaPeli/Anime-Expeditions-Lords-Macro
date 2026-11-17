import copy

import pytest

from core import transfer as tr


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    for module, key, folder in (
        (tr.templates, "TEMPLATES_DIR", "Templates"),
        (tr.task_presets, "PRESETS_DIR", "Templates/Tasks"),
        (tr.paths, "PATHS_DIR", "Paths"),
        (tr.paths, "DEFAULT_PATHS_DIR", "defaults"),
        (tr.input_record, "RECORDINGS_DIR", "Recordings"),
    ):
        d = tmp_path / folder
        d.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(module, key, str(d))
    monkeypatch.setattr(tr.settings, "SETTINGS_FILE", str(tmp_path / "settings.json"))


def seed():
    tr.paths.save_path("Route", [{"key": "w", "t": 0}])
    tr.input_record.save_recording("Clicks", [{"type": "click", "x": 1}])
    blocks = {"battle": [{"type": "detect", "then": [
        {"type": "walk_path", "mode": "custom", "pathName": "Route"},
        {"type": "record", "params": {"recording": "Clicks"}},
    ]}]}
    tr.templates.save_template("Farm", blocks)
    tasks = [{"id": "old", "mode": "story", "macro": "Farm", "repeat": 7}]
    tr.task_presets.save_preset("Night", tasks)
    tr.settings.save({"tasks": tasks, "theme_base": "dark", "challenge": {"enabled": True,
                     "maps": {"School": {"macro": "Farm"}}},
                     "fuel_refill": {"paths": {"drill": "Route"}}, "run_history": ["keep"]})
    return blocks


DEFAULTS = {"theme_base": "light", "hotkeys": {}}
RESOURCES = {k: {} for k in tr.RESOURCE_KEYS}


def test_complete_round_trip_includes_presets_and_nested_dependencies():
    blocks = seed()
    bundle = tr.export_bundle(list(tr.CATEGORIES), DEFAULTS, RESOURCES)
    assert tr.validate_bundle(bundle) == list(tr.CATEGORIES)
    assert "run_history" not in bundle["sections"]["settings"]["config"]
    assert bundle["sections"]["tasks"]["presets"]["Night"][0]["repeat"] == 7
    assert "Clicks" in bundle["sections"]["tasks"]["recordings"]
    tr.templates.delete_template("Farm")
    tr.task_presets.delete_preset("Night")
    tr.settings.save({})
    tr.import_bundle(bundle, list(tr.CATEGORIES), "replace", DEFAULTS)
    assert tr.templates.load_template("Farm")["blocks"] == blocks
    assert tr.settings.load()["tasks"][0]["id"] != "old"
    assert tr.settings.load()["theme_base"] == "dark"
    assert tr.settings.load()["fuel_refill"]["paths"]["drill"] == "Route"


def test_merge_preserves_conflicts_and_remaps_tasks_resources_and_recordings():
    seed()
    bundle = tr.export_bundle(["tasks", "resources"], DEFAULTS, RESOURCES)
    tr.templates.save_template("Farm", {"battle": []})
    tr.paths.save_path("Route", [{"key": "s"}])
    tr.input_record.save_recording("Clicks", [{"type": "click", "x": 9}])
    tr.import_bundle(bundle, ["tasks", "resources"], "merge", DEFAULTS)
    assert tr.templates.load_template("Farm")["blocks"] == {"battle": []}
    cfg = tr.settings.load()
    assert len(cfg["tasks"]) == 2
    imported = cfg["tasks"][-1]["macro"]
    assert imported != "Farm"
    assert cfg["challenge"]["maps"]["School"]["macro"] == imported
    assert cfg["fuel_refill"]["paths"]["drill"] != "Route"
    blocks = tr.templates.load_template(imported)["blocks"]["battle"][0]["then"]
    assert blocks[0]["pathName"] != "Route"
    assert blocks[1]["params"]["recording"] != "Clicks"
    assert len(tr.task_presets.list_presets()) == 2
    assert cfg["run_history"] == ["keep"]


def test_replace_tasks_does_not_clear_unselected_macros_or_resources():
    seed()
    bundle = tr.export_bundle(["tasks", "resources"], DEFAULTS, RESOURCES)
    tr.templates.save_template("Unrelated", {"battle": []})
    tr.task_presets.save_preset("Extra", [])
    tr.settings.update({"challenge": {"enabled": False}})
    tr.import_bundle(bundle, ["tasks"], "replace", DEFAULTS)
    assert tr.task_presets.list_presets() == ["Night"]
    assert len(tr.settings.load()["tasks"]) == 1
    assert tr.settings.load()["challenge"] == {"enabled": False}
    assert "Unrelated" in tr.templates.list_templates()


def test_macros_replace_clears_only_user_macro_library():
    seed()
    bundle = tr.export_bundle(["macros"], DEFAULTS, RESOURCES)
    tr.templates.save_template("Extra", [])
    tr.import_bundle(bundle, ["macros"], "replace", DEFAULTS)
    assert tr.templates.list_templates() == ["Farm"]
    assert tr.task_presets.list_presets() == ["Night"]


def test_invalid_data_rejected_before_any_changes():
    seed()
    bundle = tr.export_bundle(["tasks"], DEFAULTS, RESOURCES)
    original = copy.deepcopy(tr.settings.load())
    bundle["sections"]["tasks"]["recordings"]["Clicks"]["events"] = "broken"
    with pytest.raises(ValueError):
        tr.import_bundle(bundle, ["tasks"], "replace", DEFAULTS)
    assert tr.settings.load() == original
    assert tr.templates.template_exists("Farm")


def test_failed_import_restores_deleted_macros_and_config(monkeypatch):
    seed()
    bundle = tr.export_bundle(["macros"], DEFAULTS, RESOURCES)
    original = tr.templates.load_template("Farm")
    def fail(*args):
        raise OSError("disk failure")
    monkeypatch.setattr(tr.templates, "save_template", fail)
    with pytest.raises(OSError, match="disk failure"):
        tr.import_bundle(bundle, ["macros"], "replace", DEFAULTS)
    assert tr.templates.load_template("Farm") == original


def test_settings_cannot_overwrite_unselected_queue_or_resources():
    seed()
    bundle = tr.export_bundle(["settings"], DEFAULTS, RESOURCES)
    bundle["sections"]["settings"]["config"].update(tasks=[], challenge={})
    tr.import_bundle(bundle, ["settings"], "replace", DEFAULTS)
    assert tr.settings.load()["tasks"]
    assert tr.settings.load()["challenge"]["enabled"]
