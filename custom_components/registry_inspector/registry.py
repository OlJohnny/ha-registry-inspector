"""The only module that accesses Home Assistant's internal registry structures.

All registry reads and mutations run on HA's event loop. Disk I/O is limited to
our own backup directory. Core owns serialization and persistence of its stores.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
from collections.abc import MutableMapping
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.json import json_bytes

from .const import DOMAIN
from .grouping import assign_groups, device_pairs

_LOGGER = logging.getLogger(__name__)
DELETED = {"deleted_entities", "deleted_devices"}
SECTIONS = {
    "entity": ("entities", "deleted_entities"),
    "device": ("devices", "child_devices", "deleted_devices"),
}


class InspectorError(Exception):
    """A request that cannot safely be completed."""


def fingerprint(record: dict) -> str:
    """Identify the exact saved record shown in the inventory."""
    return hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()


def _write_backup(directory: Path, content: bytes) -> str:
    """Write an exclusive backup and flush it before allowing any mutation."""
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    name = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex}.json"
    path = directory / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as file:
        file.write(content)
        file.flush()
        os.fsync(file.fileno())
    # Persist the new directory entry as well as the file contents on HAOS/Linux.
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return name


class Inspector:
    """Provide an inventory and selectively forget deleted records."""

    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.enabled = True
        self.entities = er.async_get(hass)
        self.devices = dr.async_get(hass)
        self.lock = asyncio.Lock()

    def _snapshots(self) -> dict:
        """Copy Core's serialized representations, including child devices."""
        return json.loads(
            json_bytes(
                {
                    "entity": self.entities._data_to_save(),
                    "device": self.devices._data_to_save(),
                }
            )
        )

    def _compatibility(self) -> str | None:
        """Fail closed for writes outside the supported Core and storage versions."""
        if re.fullmatch(r"2026\.11\.\d+", HA_VERSION) is None:
            return f"Forgetting is supported on HA 2026.11.x; this is {HA_VERSION}."
        versions = (
            er.STORAGE_VERSION_MAJOR,
            er.STORAGE_VERSION_MINOR,
            dr.STORAGE_VERSION_MAJOR,
            dr.STORAGE_VERSION_MINOR,
        )
        if versions != (1, 24, 3, 4):
            return "The registry storage schema changed. Forgetting is disabled."
        if not isinstance(self.entities.deleted_entities, dict) or not isinstance(
            self.devices._deleted_devices, MutableMapping
        ):
            return "The deleted-record containers changed. Forgetting is disabled."
        return None

    def inventory(self) -> dict:
        """Return active and saved deleted records, with independent live status."""
        snapshots = self._snapshots()
        areas = {area.id: area.name for area in ar.async_get(self.hass).areas.values()}
        integrations = {
            entry.entry_id: entry.domain for entry in self.hass.config_entries.async_entries()
        }
        rows = []
        for kind, sections in SECTIONS.items():
            for section in sections:
                for record in snapshots[kind].get(section, []):
                    state = self.hass.states.get(record.get("entity_id", ""))
                    deleted = section in DELETED
                    config_id = record.get("config_entry_id")
                    area_id = record.get("area_id")
                    rows.append(
                        {
                            "kind": kind,
                            "id": record["id"],
                            "section": section,
                            "deleted": deleted,
                            "name": record.get("name_by_user")
                            or record.get("name")
                            or record.get("original_name")
                            or record.get("entity_id")
                            or record["id"],
                            "entity_id": record.get("entity_id"),
                            "integration": integrations.get(config_id)
                            or record.get("platform")
                            or record.get("domain"),
                            "area": areas.get(area_id, area_id),
                            "disabled": bool(record.get("disabled_by")),
                            "state": state.state if state and not deleted else None,
                            "fingerprint": fingerprint(record),
                            "record": record,
                        }
                    )
        assign_groups(rows)
        return {
            "rows": rows,
            "ha_version": HA_VERSION,
            "write_disabled_reason": self._compatibility(),
        }

    def _resolve(self, selections: list[dict], snapshots: dict) -> list[dict]:
        """Resolve exact deleted IDs and reject stale or active identities."""
        if not self.enabled:
            raise InspectorError("Registry Inspector was unloaded. Refresh the page.")
        if self.hass.state is not CoreState.running:
            raise InspectorError("Home Assistant must be running, not starting or stopping.")
        if reason := self._compatibility():
            raise InspectorError(reason)
        if not selections:
            raise InspectorError("Select at least one deleted record.")
        deleted_by_id = {}
        active_ids = {}
        active_entities = set()
        active_devices = set()
        for kind, sections in SECTIONS.items():
            deleted_by_id[kind] = {}
            active_ids[kind] = set()
            for section in sections:
                for record in snapshots[kind].get(section, []):
                    if section in DELETED:
                        if record["id"] in deleted_by_id[kind]:
                            raise InspectorError(
                                "Duplicate registry IDs found. Forgetting is disabled."
                            )
                        deleted_by_id[kind][record["id"]] = record
                        continue
                    active_ids[kind].add(record["id"])
                    if kind == "entity":
                        active_entities.add(
                            (
                                record["entity_id"].split(".")[0],
                                record["platform"],
                                record["unique_id"],
                            )
                        )
                    else:
                        active_devices.update(
                            (field, tuple(pair))
                            for field in ("identifiers", "connections")
                            for pair in device_pairs(record, field)
                        )
        resolved = []
        seen = set()
        for selection in selections:
            kind = selection["kind"]
            identity = (kind, selection["id"])
            if identity in seen:
                raise InspectorError("The selection contains duplicate records.")
            seen.add(identity)
            section = "deleted_entities" if kind == "entity" else "deleted_devices"
            record = deleted_by_id[kind].get(selection["id"])
            if record is None or fingerprint(record) != selection["fingerprint"]:
                raise InspectorError("A selected record changed or disappeared. Refresh the list.")
            same_identity = record["id"] in active_ids[kind]
            if kind == "entity":
                same_identity |= (
                    record["entity_id"].split(".")[0],
                    record["platform"],
                    record["unique_id"],
                ) in active_entities
            else:
                same_identity |= any(
                    (field, tuple(pair)) in active_devices
                    for field in ("identifiers", "connections")
                    for pair in device_pairs(record, field)
                )
            if same_identity:
                raise InspectorError("A selected identity is active again. Refresh the list.")
            resolved.append({"kind": kind, "section": section, "record": record})
        return resolved

    async def apply(self, user_id: str, selections: list[dict]) -> dict:
        """Back up, revalidate and forget only the explicitly selected tombstones."""
        async with self.lock:
            snapshots = self._snapshots()
            records = self._resolve(selections, snapshots)
            backup = {
                "format_version": 1,
                "ha_version": HA_VERSION,
                "created_at": datetime.now(UTC).isoformat(),
                "selected": records,
                "registries": {
                    kind: {
                        "key": f"core.{kind}_registry",
                        "version": module.STORAGE_VERSION_MAJOR,
                        "minor_version": module.STORAGE_VERSION_MINOR,
                        "data": snapshots[kind],
                    }
                    for kind, module in (("entity", er), ("device", dr))
                },
            }
            content = json_bytes(backup)
            directory = Path(self.hass.config.path(".storage", f"{DOMAIN}_backups"))
            filename = await self.hass.async_add_executor_job(_write_backup, directory, content)
            # Pairing or settings may have changed while the backup was being written.
            records = self._resolve(selections, self._snapshots())
            removed = []
            registries = set()
            try:
                # No await between validation, deletion and scheduling Core's saves.
                for item in records:
                    record = item["record"]
                    if item["kind"] == "entity":
                        key = (
                            record["entity_id"].split(".")[0],
                            record["platform"],
                            record["unique_id"],
                        )
                        registry = self.entities
                        container = registry.deleted_entities
                    else:
                        key = record["id"]
                        registry = self.devices
                        container = registry._deleted_devices
                    removed.append((container, key, container.pop(key)))
                    registries.add(registry)
                for registry in registries:
                    registry.async_schedule_save()
            except Exception:
                for container, key, record in reversed(removed):
                    container[key] = record
                for registry in registries:
                    registry.async_schedule_save()
                raise
            _LOGGER.info(
                "Administrator %s forgot %d deleted registry records", user_id, len(records)
            )
            return {
                "forgotten": len(records),
                "backup_path": str(directory / filename),
                "backup_filename": filename,
                "backup_content": content.decode(),
            }
