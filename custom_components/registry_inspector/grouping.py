"""Group inventory rows without changing saved records or deletion identities."""

import re
from collections import defaultdict

_HARDWARE = re.compile(
    r"(?<![0-9a-f:])(?:[0-9a-f]{2}:){7}[0-9a-f]{2}(?![0-9a-f:])"
    r"|(?<![0-9a-f:])(?:[0-9a-f]{2}:){5}[0-9a-f]{2}(?![0-9a-f:])"
    r"|(?<![0-9a-f-])(?:[0-9a-f]{2}-){7}[0-9a-f]{2}(?![0-9a-f-])"
    r"|(?<![0-9a-f-])(?:[0-9a-f]{2}-){5}[0-9a-f]{2}(?![0-9a-f-])"
    r"|(?<![0-9a-z])(?:0x)?(?:[0-9a-f]{16}|[0-9a-f]{12})(?![0-9a-f])"
)


def hardware_ids(values) -> set[str]:
    """Extract complete MAC/IEEE addresses, never partial identifiers or names."""
    return {
        match[0].removeprefix("0x").replace(":", "").replace("-", "")
        for value in values
        for match in _HARDWARE.finditer(str(value).lower())
    }


def device_pairs(record: dict, field: str) -> list[tuple[str, str]]:
    """Read usable identifier/connection pairs without altering malformed saved data."""
    values = record.get(field)
    if not isinstance(values, (list, tuple)):
        return []
    return [
        (pair[0], pair[1])
        for pair in values
        if isinstance(pair, (list, tuple))
        and len(pair) == 2
        and all(isinstance(value, str) and value for value in pair)
    ]


def _same_scope(entity: dict, device: dict) -> bool:
    """Keep hardware matches within their owning integration when it is known."""
    entity_config = entity["record"].get("config_entry_id")
    device_config = device["record"].get("config_entry_id")
    if entity_config and device_config:
        return entity_config == device_config
    platform = entity["record"].get("platform") or entity.get("integration")
    namespaces = {pair[0] for pair in device_pairs(device["record"], "identifiers")}
    return bool(platform and (platform == device.get("integration") or platform in namespaces))


def assign_groups(rows: list[dict]) -> None:
    """Prefer explicit links, then unique scoped hardware matches; leave ambiguity alone."""
    devices = {row["id"]: row for row in rows if row["kind"] == "device"}
    by_hardware = defaultdict(set)
    for device_id, row in devices.items():
        row["group_id"] = f"device:{device_id}"
        row["group_name"] = row["name"]
        values = [
            pair[1]
            for field in ("identifiers", "connections")
            for pair in device_pairs(row["record"], field)
        ]
        for address in hardware_ids(values):
            by_hardware[address].add(device_id)

    for row in rows:
        if row["kind"] != "entity":
            continue
        device_id = row["record"].get("device_id")
        addresses = hardware_ids([row["record"].get("unique_id", "")])
        candidates = {
            candidate
            for address in addresses
            for candidate in by_hardware[address]
            if _same_scope(row, devices[candidate])
        }
        if not device_id and len(candidates) == 1:
            device_id = next(iter(candidates))
        if device_id:
            row["group_id"] = f"device:{device_id}"
            row["group_name"] = devices.get(device_id, {}).get("name", device_id)
        elif len(addresses) == 1 and not candidates:
            address = next(iter(addresses))
            scope = row["record"].get("config_entry_id") or row.get("integration") or ""
            row["group_id"] = f"hardware:{scope}:{address}"
            row["group_name"] = f"0x{address}"
        else:
            row["group_id"] = "other"
            row["group_name"] = "Other entities"
