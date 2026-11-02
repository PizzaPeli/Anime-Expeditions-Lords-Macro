from core import map_setups


def test_halloween_catalog_import_preserves_customizations_and_removals(monkeypatch):
    custom = {"mode": "both", "image": "Custom label", "path": "Custom route"}
    stored = {"map_setups": {"Hollow Desert": custom}}
    monkeypatch.setattr(map_setups.settings, "load", lambda: stored)
    monkeypatch.setattr(map_setups.settings, "update", lambda change: stored.update(change))
    loaded = map_setups.load()
    assert loaded["Hollow Desert"] == custom
    assert loaded["Flaming Monastery"]["path"] == ""
    map_setups.remove("Crimson Shore")
    assert "Crimson Shore" not in map_setups.load()


def test_map_setup_list_is_expandable_and_keeps_legacy_paths(monkeypatch):
    stored = {"default_walk_paths": {"Rose Kingdom": "Old Rose route"}}
    monkeypatch.setattr(map_setups.settings, "load", lambda: stored)
    monkeypatch.setattr(map_setups.settings, "update", lambda change: stored.update(change))
    monkeypatch.setattr(map_setups.paths, "load_shipped_default_walk_paths", lambda: {})
    monkeypatch.setattr(map_setups.paths, "load_path",
                        lambda name: {"events": [("w", "down", 0)]} if name else {"events": []})

    initial = map_setups.load()
    assert initial["Rose Kingdom"]["path"] == "Old Rose route"
    assert map_setups.save("New Map", "story", "New Map label", "New route")["ok"]
    assert map_setups.load()["New Map"]["image"] == "New Map label"

    map_setups.remove("New Map")
    assert "New Map" not in map_setups.load()
    assert "Rose Kingdom" in map_setups.load()


def test_one_identification_image_cannot_claim_two_maps(monkeypatch):
    stored = {"map_setups": {"First": {"mode": "story", "image": "Shared"}}}
    monkeypatch.setattr(map_setups.settings, "load", lambda: stored)
    monkeypatch.setattr(map_setups.settings, "update", lambda change: stored.update(change))

    result = map_setups.save("Second", "raid", "Shared")

    assert result["reason"] == "image_already_identifies_another_map"
    assert "Second" not in map_setups.load()
