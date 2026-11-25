"""Check sidebar registration, API registration and unload behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components import registry_inspector as integration
from custom_components.registry_inspector.const import DOMAIN, PANEL_PATH


async def test_setup_and_unload(hass, config_entry, monkeypatch):
    static_paths = AsyncMock()
    monkeypatch.setattr(
        hass, "http", SimpleNamespace(async_register_static_paths=static_paths), raising=False
    )
    commands = Mock()
    register_panel = AsyncMock()
    remove_panel = Mock()
    monkeypatch.setattr(integration, "async_register_commands", commands)
    monkeypatch.setattr(integration.panel_custom, "async_register_panel", register_panel)
    monkeypatch.setattr(integration.frontend, "async_remove_panel", remove_panel)
    assert await integration.async_setup(hass, {})
    commands.assert_called_once_with(hass)
    assert static_paths.call_args.args[0][0].url_path == "/registry_inspector/panel.js"
    assert await integration.async_setup_entry(hass, config_entry)
    assert register_panel.call_args.kwargs["require_admin"] is True
    assert register_panel.call_args.kwargs["webcomponent_name"] == "registry-inspector-panel"
    inspector = hass.data[DOMAIN]
    assert await integration.async_unload_entry(hass, config_entry)
    assert DOMAIN not in hass.data and not inspector.enabled
    remove_panel.assert_called_once_with(hass, PANEL_PATH)


async def test_failed_panel_registration_does_not_enable_backend(hass, config_entry, monkeypatch):
    monkeypatch.setattr(
        integration.panel_custom,
        "async_register_panel",
        AsyncMock(side_effect=ValueError("collision")),
    )
    with pytest.raises(ValueError, match="collision"):
        await integration.async_setup_entry(hass, config_entry)
    assert DOMAIN not in hass.data
