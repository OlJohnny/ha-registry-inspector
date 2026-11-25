"""Small fixtures using real Core registries, without loading device integrations."""

import asyncio
from types import MappingProxyType

import pytest
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.registry_inspector.const import DOMAIN
from custom_components.registry_inspector.registry import Inspector


@pytest.fixture
async def hass(tmp_path):
    instance = HomeAssistant(str(tmp_path))
    instance.config_entries = ConfigEntries(instance, {})
    instance.config_entries._initialized.set()
    dr.async_setup(instance)
    await asyncio.wait_for(ar.async_load(instance), 3)
    await asyncio.wait_for(dr.async_load(instance), 3)
    await asyncio.wait_for(er.async_load(instance), 3)
    instance.state = CoreState.running
    yield instance
    await instance.async_stop(force=True)


@pytest.fixture
async def config_entry(hass):
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain="mqtt",
        title="Test MQTT",
        data={},
        options={},
        source="user",
        unique_id=None,
        discovery_keys=MappingProxyType({}),
        subentries_data=[],
    )
    hass.config_entries._entries[entry.entry_id] = entry
    return entry


@pytest.fixture
async def inspector(hass):
    service = Inspector(hass)
    hass.data[DOMAIN] = service
    return service


@pytest.fixture
async def seed(hass, config_entry):
    """Create and optionally remove a real registered device and its switch."""

    def create(unique="0x1234", deleted=True):
        device_registry = dr.async_get(hass)
        entity_registry = er.async_get(hass)
        area = ar.async_get(hass).async_get_or_create("Old room")
        device = device_registry.async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={("mqtt", unique)},
            name="Spare plug",
        )
        device_registry.async_update_device(
            device.id, name_by_user="Old device name", area_id=area.id
        )
        entity = entity_registry.async_get_or_create(
            "switch",
            "mqtt",
            f"{unique}_switch",
            config_entry=config_entry,
            device_id=device.id,
            original_name="Plug",
        )
        entity = entity_registry.async_update_entity(
            entity.entity_id, name="Old entity name", icon="mdi:fan", area_id=area.id
        )
        if deleted:
            entity_registry.async_remove(entity.entity_id)
            device_registry.async_remove_device(device.id)
        return device, entity

    return create
