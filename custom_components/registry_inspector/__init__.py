"""Inspect registries and selectively forget saved deleted records."""

from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PANEL_PATH, STATIC_URL, TITLE
from .registry import Inspector
from .websocket import async_register_commands


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the static module and authenticated API once per HA process."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "panel.js"), False)]
    )
    async_register_commands(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Add the administrator-only panel."""
    inspector = Inspector(hass)
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_PATH,
        webcomponent_name="registry-inspector-panel",
        sidebar_title=TITLE,
        sidebar_icon="mdi:database-search",
        module_url=f"{STATIC_URL}?v=0.2.2",
        require_admin=True,
        config_panel_domain=DOMAIN,
    )
    hass.data[DOMAIN] = inspector
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove the panel and prevent pending operations from mutating registries."""
    inspector = hass.data.pop(DOMAIN)
    inspector.enabled = False
    frontend.async_remove_panel(hass, PANEL_PATH)
    return True
