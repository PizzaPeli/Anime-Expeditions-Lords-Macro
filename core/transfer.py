"""Selective backup bundles. Dependencies travel with the category using them."""
import copy
import datetime
import os
import uuid
from pathlib import Path

from . import settings, templates, task_presets, paths, input_record, share
from .jsonstore import write_json_atomic

CATEGORIES = ("settings", "tasks", "macros", "resources")
RESOURCE_KEYS = {"challenge", "crafting", "auto_shop", "fuel_refill", "demonic_rifts"}
KIND = "anime-expeditions-backup"


def _refs(value, key=""):
    macros, walks = set(), set()
    if isinstance(value, dict):
        for k, v in value.items():
            m, p = _refs(v, k if key not in ("paths", "default_walk_paths", "encounter_walk_paths") else "path")
            macros.update(m)
            walks.update(p)
    elif isinstance(value, list):
        for v in value:
            m, p = _refs(v, key)
            macros.update(m)
            walks.update(p)
    elif isinstance(value, str) and value:
        if key == "macro":
            macros.add(value)
        if key in ("path", "pathName", "path_name"):
            walks.add(value)
    return macros, walks


def _dependencies(section, all_macros=False):
    names, walk_names = _refs(section)
    if all_macros:
        names.update(templates.list_templates())
        walk_names.update(paths.list_custom_paths())
    bundled = {}
    recordings = set(input_record.list_recordings()) if all_macros else set()
    for name in sorted(names):
        if not templates.template_exists(name):
            raise ValueError(f'Missing macro "{name}". Fix its assignment before exporting.')
        t = templates.load_template(name)
        if not isinstance(t.get("blocks"), (dict, list)):
            raise ValueError(f'Unreadable macro "{name}".')
        bundled[name] = t
        walk_names.update(share.collect_walk_path_names(t["blocks"]))
        recordings.update(share.collect_recording_names(t["blocks"]))
    walks = {}
    for name in sorted(walk_names):
        if name not in paths.list_paths():
            raise ValueError(f'Missing path "{name}".')
        walks[name] = paths.load_path(name)
    for name in recordings:
        if name not in input_record.list_recordings():
            raise ValueError(f'Missing recording "{name}".')
    section.update(templates=bundled, paths=walks,
                   recordings=input_record.collect_recordings(recordings))


def export_bundle(selected, setting_defaults, resource_defaults):
    selected = _selection(selected)
    saved = settings.load()
    sections = {}
    for category in selected:
        section = {}
        if category == "settings":
            section["config"] = {k: copy.deepcopy(saved.get(k, v)) for k, v in setting_defaults.items()}
        elif category == "resources":
            section["config"] = {k: copy.deepcopy(saved.get(k, v)) for k, v in resource_defaults.items()}
        elif category == "tasks":
            presets = {}
            for name in task_presets.list_presets():
                preset = task_presets.load_preset(name)
                if preset.get("error"):
                    raise ValueError(f'Unreadable task preset "{name}".')
                presets[name] = preset["tasks"]
            section.update(queue=copy.deepcopy(saved.get("tasks", [])), presets=presets)
        _dependencies(section, category == "macros")
        sections[category] = section
    return {"kind": KIND, "version": 1,
            "exported": datetime.datetime.now(datetime.timezone.utc).isoformat(), "sections": sections}


def _selection(selected):
    if not isinstance(selected, list) or not selected or any(k not in CATEGORIES for k in selected):
        raise ValueError("Select at least one valid category.")
    return list(dict.fromkeys(selected))


def validate_bundle(bundle):
    if not isinstance(bundle, dict) or bundle.get("kind") != KIND or bundle.get("version") != 1:
        raise ValueError("Choose a combined Import / Export backup file (version 1).")
    sections = bundle.get("sections")
    if not isinstance(sections, dict) or not sections or any(k not in CATEGORIES for k in sections):
        raise ValueError("Invalid backup categories.")
    for category, section in sections.items():
        if not isinstance(section, dict):
            raise ValueError("Invalid backup section.")
        for key in ("templates", "paths", "recordings"):
            entries = section.get(key)
            if not isinstance(entries, dict):
                raise ValueError(f"Invalid {key} in {category}.")
            for name, entry in entries.items():
                field = "blocks" if key == "templates" else "events"
                expected = (dict, list) if key == "templates" else (list,)
                if not isinstance(name, str) or not name.strip() or not isinstance(entry, dict) or not isinstance(entry.get(field), expected):
                    raise ValueError(f"Invalid {key} entry.")
        if category in ("settings", "resources") and not isinstance(section.get("config"), dict):
            raise ValueError("Invalid configuration.")
        if category == "tasks":
            if not isinstance(section.get("queue"), list) or not isinstance(section.get("presets"), dict):
                raise ValueError("Invalid task queue or presets.")
            for queue in [section["queue"], *section["presets"].values()]:
                if not isinstance(queue, list) or any(not isinstance(t, dict) or not isinstance(t.get("mode"), str) for t in queue):
                    raise ValueError("Invalid task entry.")
            if any(not isinstance(name, str) or not name.strip() for name in section["presets"]):
                raise ValueError("Invalid preset name.")
    return list(sections)


def _remap(value, macro_names, walk_names, key=""):
    if isinstance(value, dict):
        return {k: _remap(v, macro_names, walk_names,
                         "path" if key in ("paths", "default_walk_paths", "encounter_walk_paths") else k)
                for k, v in value.items()}
    if isinstance(value, list):
        return [_remap(v, macro_names, walk_names, key) for v in value]
    if isinstance(value, str):
        if key == "macro":
            return macro_names.get(value, value)
        if key in ("path", "pathName", "path_name"):
            return walk_names.get(value, value)
    return value


def _free_name(name, existing):
    candidate, n = name, 2
    folded = {s.casefold() for s in existing}
    while candidate.casefold() in folded:
        candidate = f"{name} imported {n}"
        n += 1
    return candidate


def _merge(current, incoming):
    if isinstance(current, dict) and isinstance(incoming, dict):
        return {**current, **{k: _merge(current.get(k), v) for k, v in incoming.items()}}
    if isinstance(current, list) and isinstance(incoming, list):
        return current + [v for v in incoming if v not in current]
    return incoming


def import_bundle(bundle, selected, mode, setting_defaults):
    available = validate_bundle(bundle)
    selected = _selection(selected)
    if mode not in ("merge", "replace") or any(k not in available for k in selected):
        raise ValueError("Invalid import selection or mode.")
    sections = copy.deepcopy({k: bundle["sections"][k] for k in selected})
    macro_data, walk_data, record_data = {}, {}, {}
    for section in sections.values():
        for key, combined in (("templates", macro_data), ("paths", walk_data), ("recordings", record_data)):
            for name, entry in section[key].items():
                if name in combined and combined[name] != entry:
                    raise ValueError(f'Conflicting bundled dependency "{name}".')
                combined[name] = entry
    for section in sections.values():
        needed, walks = _refs({k: v for k, v in section.items() if k not in ("templates", "paths", "recordings")})
        if needed - macro_data.keys():
            raise ValueError("The backup is missing required macros.")
        if walks - walk_data.keys():
            raise ValueError("The backup is missing required paths.")
    for t in macro_data.values():
        if share.collect_walk_path_names(t["blocks"]) - walk_data.keys():
            raise ValueError("The backup is missing a required path.")
        if share.collect_recording_names(t["blocks"]) - record_data.keys():
            raise ValueError("The backup is missing a required recording.")

    # Snapshot only user-owned JSON files; shipped defaults/examples are untouched.
    directories = (templates.TEMPLATES_DIR, task_presets.PRESETS_DIR, paths.PATHS_DIR, input_record.RECORDINGS_DIR)
    def files():
        return {os.path.join(d, n) for d in directories if os.path.isdir(d)
                for n in os.listdir(d) if n.endswith(".json") and os.path.isfile(os.path.join(d, n))}
    before = {p: Path(p).read_bytes() for p in files()}
    old_config = settings.load()
    try:
        # Replace clears the macro library only when Macros itself is selected.
        if mode == "replace" and "macros" in selected:
            for name in templates.list_templates():
                if not templates.delete_template(name):
                    raise OSError(f'Could not replace macro "{name}".')
        walk_map, record_map, macro_map = {}, {}, {}
        for name, entry in walk_data.items():
            walk_map[name] = (paths.save_path(name, entry["events"]) if mode == "replace"
                              else paths.import_path(name, entry["events"]))
        for name, entry in record_data.items():
            record_map[name] = (input_record.save_recording(name, entry["events"]) if mode == "replace"
                                else input_record.import_recording(name, entry["events"]))
        existing = templates.list_templates()
        for name, t in macro_data.items():
            blocks = t["blocks"]
            share.remap_walk_path_names(blocks, walk_map)
            share.remap_recording_names(blocks, record_map)
            target = name
            if mode == "merge" and name in existing and templates.load_template(name).get("blocks") != blocks:
                target = _free_name(name, existing)
            macro_map[name] = templates.save_template(target, blocks)
            existing.append(target)
        changes = {}
        for category, section in sections.items():
            section = _remap(section, macro_map, walk_map)
            if category in ("settings", "resources"):
                allowed = set(setting_defaults) if category == "settings" else RESOURCE_KEYS
                config = {k: v for k, v in section["config"].items() if k in allowed}
                if mode == "replace" and category == "settings":
                    config = {**copy.deepcopy(setting_defaults), **config}
                for k, v in config.items():
                    changes[k] = _merge(old_config.get(k), v) if mode == "merge" else v
            elif category == "tasks":
                if mode == "replace":
                    for name in task_presets.list_presets():
                        if not task_presets.delete_preset(name):
                            raise OSError(f'Could not replace preset "{name}".')
                existing_presets = task_presets.list_presets()
                def fresh(queue):
                    return [{**t, "id": "t_" + uuid.uuid4().hex} for t in queue]
                for name, queue in section["presets"].items():
                    target = _free_name(name, existing_presets) if mode == "merge" and name in existing_presets else name
                    task_presets.save_preset(target, fresh(queue))
                    existing_presets.append(target)
                changes["tasks"] = (old_config.get("tasks", []) if mode == "merge" else []) + fresh(section["queue"])
        write_json_atomic(settings.SETTINGS_FILE, {**settings.load(), **changes})
    except Exception:
        for p in files() - before.keys():
            os.remove(p)
        for p, content in before.items():
            with open(p, "wb") as f:
                f.write(content)
        write_json_atomic(settings.SETTINGS_FILE, old_config)
        raise
    return {"ok": True, "categories": selected}
