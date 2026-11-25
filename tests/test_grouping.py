"""Grouping must avoid partial addresses, cross-integration matches and ambiguity."""

from copy import deepcopy

import pytest

from custom_components.registry_inspector.grouping import assign_groups, hardware_ids


def device(device_id="device", config="mqtt-1", address="0xf082c0fffee75697"):
    return {
        "kind": "device",
        "id": device_id,
        "name": "Kitchen plug",
        "integration": "mqtt",
        "record": {"config_entry_id": config, "identifiers": [["mqtt", f"zigbee2mqtt_{address}"]]},
    }


def entity(config="mqtt-1", address="0xf082c0fffee75697", device_id=None):
    return {
        "kind": "entity",
        "id": "entity",
        "name": "Plug switch",
        "integration": "mqtt",
        "record": {
            "config_entry_id": config,
            "unique_id": f"{address}_switch",
            "platform": "mqtt",
            "device_id": device_id,
        },
    }


def test_explicit_link_overrides_hardware_and_records_are_unchanged():
    rows = [device(), device("second"), entity(device_id="second")]
    originals = [deepcopy(row["record"]) for row in rows]
    assign_groups(rows)
    assert rows[-1]["group_id"] == "device:second"
    assert [row["record"] for row in rows] == originals


def test_deleted_records_match_full_hardware_address_in_same_integration():
    rows = [device(), device("other", config="mqtt-2"), entity()]
    assign_groups(rows)
    assert rows[-1]["group_id"] == "device:device"
    assert rows[-1]["group_name"] == "Kitchen plug"


def test_ambiguous_devices_do_not_get_arbitrarily_selected():
    rows = [device(), device("second"), entity()]
    assign_groups(rows)
    assert rows[-1]["group_id"] == "other"


def test_unlinked_entities_share_address_but_not_integration():
    rows = [entity(), entity(), entity(config="mqtt-2")]
    assign_groups(rows)
    assert rows[0]["group_id"] == rows[1]["group_id"]
    assert rows[0]["group_id"] != rows[2]["group_id"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0xf082c0fffee75697_switch", {"f082c0fffee75697"}),
        ("f0:82:c0:ff:fe:e7:56:97", {"f082c0fffee75697"}),
        ("f0:82:c0:ff:fe:e7:56:97-1-6", {"f082c0fffee75697"}),
        ("f0:82:c0:e7:56:97_temperature", {"f082c0e75697"}),
        ("f0-82-c0-e7-56-97_temperature", {"f082c0e75697"}),
        ("295fa60c65e526acb640fadaf1b63404", set()),
        ("0xf082c0fffee7569_switch", set()),
        ("plug_kitchen_switch", set()),
    ],
)
def test_complete_addresses_only(value, expected):
    assert hardware_ids([value]) == expected
