"""Verify selective forgetting and race protection against real HA registries."""

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import attr
import pytest
from homeassistant.core import CoreState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.registry_inspector import registry as module
from custom_components.registry_inspector.registry import InspectorError


def selections(inspector, kind=None):
    return [
        {key: row[key] for key in ("kind", "id", "fingerprint")}
        for row in inspector.inventory()["rows"]
        if row["deleted"] and (kind is None or row["kind"] == kind)
    ]


async def test_inventory_separates_active_deleted_disabled_and_unavailable(hass, seed, inspector):
    seed()
    _, active = seed("0x9999", deleted=False)
    hass.states.async_set(active.entity_id, "unavailable")
    rows = inspector.inventory()["rows"]
    assert len(rows) == 4
    assert {row["section"] for row in rows} == {
        "entities",
        "deleted_entities",
        "devices",
        "deleted_devices",
    }
    tombstone = next(row for row in rows if row["section"] == "deleted_entities")
    assert tombstone["name"] == "Old entity name"
    assert tombstone["record"]["icon"] == "mdi:fan"
    assert tombstone["area"] == "Old room"
    assert tombstone["integration"] == "mqtt"
    live = next(row for row in rows if row["section"] == "entities")
    assert not live["deleted"] and live["state"] == "unavailable"
    er.async_get(hass).async_update_entity(
        active.entity_id, disabled_by=er.RegistryEntryDisabler.USER
    )
    live = next(row for row in inspector.inventory()["rows"] if row["section"] == "entities")
    assert live["disabled"] and not live["deleted"]


@pytest.mark.parametrize("kind", ["entity", "device", None])
async def test_forget_is_selective_and_backup_is_restorable(hass, seed, inspector, tmp_path, kind):
    device, _ = seed()
    seed("0x9999", deleted=False)
    before = inspector._snapshots()
    preview = inspector.preview("admin", selections(inspector, kind))
    result = await inspector.apply("admin", preview["token"])
    assert result["forgotten"] == (2 if kind is None else 1)
    backup = json.loads(Path(result["backup_path"]).read_bytes())
    assert backup["registries"]["entity"]["data"] == before["entity"]
    assert backup["registries"]["device"]["data"] == before["device"]
    assert json.loads(result["backup_content"]) == backup
    assert os.stat(result["backup_path"]).st_mode & 0o777 == 0o600
    after = inspector._snapshots()
    assert after["entity"]["entities"] == before["entity"]["entities"]
    assert after["device"]["devices"] == before["device"]["devices"]
    assert len(after["entity"]["deleted_entities"]) == (1 if kind == "device" else 0)
    assert len(after["device"]["deleted_devices"]) == (1 if kind == "entity" else 0)
    if kind != "entity":
        assert device.id not in dr.async_get(hass)._deleted_devices
        # The indexed container must forget its identifier, too.
        assert (
            dr.async_get(hass)._deleted_devices.get_entry(
                identifiers=device.identifiers,
                connections=set(),
                config_entry_id=device.config_entry_id,
            )
            is None
        )
    # Normal HA shutdown flushes pending registry writes to valid Core storage files.
    await hass.async_stop(force=True)
    for name, kind_name in (("entity", "entity"), ("device", "device")):
        path = tmp_path / ".storage" / f"core.{name}_registry"
        saved = json.loads(path.read_bytes())
        assert saved["data"] == after[kind_name]


async def test_forgotten_settings_do_not_return_on_repair(hass, seed, inspector, config_entry):
    old_device, old_entity = seed()
    preview = inspector.preview("admin", selections(inspector))
    await inspector.apply("admin", preview["token"])
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers=old_device.identifiers,
        name="New plug",
    )
    entity = er.async_get(hass).async_get_or_create(
        "switch",
        "mqtt",
        old_entity.unique_id,
        config_entry=config_entry,
        device_id=device.id,
        original_name="New switch",
    )
    assert device.id != old_device.id
    assert device.name_by_user is None and device.area_id is None
    assert entity.id != old_entity.id
    assert entity.name is None and entity.icon is None and entity.area_id is None


async def test_active_id_cannot_be_forgotten(hass, seed, inspector):
    seed(deleted=False)
    row = inspector.inventory()["rows"][0]
    with pytest.raises(InspectorError, match="changed or disappeared"):
        inspector.preview("admin", [{key: row[key] for key in ("kind", "id", "fingerprint")}])


async def test_user_binding_expiry_and_replay(seed, inspector):
    seed()
    preview = inspector.preview("alice", selections(inspector))
    with pytest.raises(InspectorError, match="another user"):
        await inspector.apply("bob", preview["token"])
    # A different user cannot invalidate the original administrator's preview.
    result = await inspector.apply("alice", preview["token"])
    assert result["forgotten"] == 2
    with pytest.raises(InspectorError, match="missing"):
        await inspector.apply("alice", preview["token"])
    seed("0x5678")
    preview = inspector.preview("alice", selections(inspector))
    inspector.previews[preview["token"]]["expires"] = time.monotonic() - 1
    with pytest.raises(InspectorError, match="expired"):
        await inspector.apply("alice", preview["token"])


async def test_changed_record_rejects_entire_selection(hass, seed, inspector):
    seed()
    preview = inspector.preview("admin", selections(inspector))
    registry = er.async_get(hass)
    key, entry = next(iter(registry.deleted_entities.items()))
    registry.deleted_entities[key] = attr.evolve(entry, icon="mdi:lightbulb")
    before = inspector._snapshots()
    with pytest.raises(InspectorError, match="changed or disappeared"):
        await inspector.apply("admin", preview["token"])
    assert inspector._snapshots() == before


async def test_repair_during_backup_does_not_remove_restored_device(
    hass, seed, inspector, config_entry, monkeypatch
):
    device, _ = seed()
    preview = inspector.preview("admin", selections(inspector))
    executor = hass.async_add_executor_job

    async def write_then_repair(func, *args):
        result = await executor(func, *args)
        if func is module._write_backup:
            dr.async_get(hass).async_get_or_create(
                config_entry_id=config_entry.entry_id,
                identifiers=device.identifiers,
                name="Returned plug",
            )
        return result

    monkeypatch.setattr(hass, "async_add_executor_job", write_then_repair)
    with pytest.raises(InspectorError, match="changed or disappeared"):
        await inspector.apply("admin", preview["token"])
    assert dr.async_get(hass).async_get(device.id) is not None
    assert len(er.async_get(hass).deleted_entities) == 1


async def test_backup_failure_never_mutates_registry(seed, inspector):
    seed()
    before = inspector._snapshots()
    preview = inspector.preview("admin", selections(inspector))
    with patch.object(module, "_write_backup", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            await inspector.apply("admin", preview["token"])
    assert inspector._snapshots() == before


async def test_unloaded_integration_rejects_pending_preview(seed, inspector):
    seed()
    preview = inspector.preview("admin", selections(inspector))
    inspector.enabled = False
    with pytest.raises(InspectorError, match="unloaded"):
        await inspector.apply("admin", preview["token"])


async def test_duplicate_empty_and_unsupported_selections(seed, inspector, monkeypatch):
    seed()
    selection = selections(inspector)
    with pytest.raises(InspectorError, match="between"):
        inspector.preview("admin", [])
    with pytest.raises(InspectorError, match="duplicate"):
        inspector.preview("admin", [selection[0], selection[0]])
    monkeypatch.setattr(module, "HA_VERSION", "2026.12.0")
    assert inspector.inventory()["write_disabled_reason"]
    with pytest.raises(InspectorError, match="2026.11"):
        inspector.preview("admin", selection)


async def test_schema_change_disables_writes(seed, inspector, monkeypatch):
    seed()
    selection = selections(inspector)
    monkeypatch.setattr(er, "STORAGE_VERSION_MINOR", 99)
    with pytest.raises(InspectorError, match="schema changed"):
        inspector.preview("admin", selection)


async def test_shutdown_during_backup_aborts_before_mutation(hass, seed, inspector, monkeypatch):
    seed()
    before = inspector._snapshots()
    preview = inspector.preview("admin", selections(inspector))
    executor = hass.async_add_executor_job

    async def write_then_shutdown(func, *args):
        result = await executor(func, *args)
        if func is module._write_backup:
            hass.state = CoreState.stopping
        return result

    monkeypatch.setattr(hass, "async_add_executor_job", write_then_shutdown)
    try:
        with pytest.raises(InspectorError, match="starting or stopping"):
            await inspector.apply("admin", preview["token"])
        assert inspector._snapshots() == before
    finally:
        hass.state = CoreState.running


async def test_schedule_failure_rolls_back_all_removed_records(hass, seed, inspector, monkeypatch):
    seed()
    before = inspector._snapshots()
    preview = inspector.preview("admin", selections(inspector))
    original = inspector.entities.async_schedule_save
    calls = 0

    def fail_once():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("schedule failed")
        original()

    monkeypatch.setattr(inspector.entities, "async_schedule_save", fail_once)
    with pytest.raises(RuntimeError, match="schedule failed"):
        await inspector.apply("admin", preview["token"])
    assert inspector._snapshots() == before


async def test_active_child_devices_appear_in_inventory(hass, seed, inspector, config_entry):
    parent, _ = seed(deleted=False)
    child = dr.async_get(hass).async_get_or_create_child(
        config_entry_id=config_entry.entry_id,
        parent_device_id=parent.id,
        identifiers={("mqtt", "child-outlet")},
        name="Second outlet",
    )
    row = next(row for row in inspector.inventory()["rows"] if row["id"] == child.id)
    assert row["section"] == "child_devices" and not row["deleted"]
