"""Authenticated administrator-only commands for the panel."""

import logging

import probatio as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .registry import Inspector, InspectorError

_LOGGER = logging.getLogger(__name__)


def _inspector(hass: HomeAssistant) -> Inspector:
    if DOMAIN not in hass.data:
        raise InspectorError("Registry Inspector is not configured.")
    return hass.data[DOMAIN]


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/list"})
@websocket_api.require_admin
@callback
def websocket_list(hass, connection, msg):
    """List registries without allowing non-admin access to their contents."""
    try:
        connection.send_result(msg["id"], _inspector(hass).inventory())
    except InspectorError as err:
        connection.send_error(msg["id"], "inspector_error", str(err))
    except Exception:
        _LOGGER.exception("Could not inspect registries")
        connection.send_error(
            msg["id"],
            "inspector_error",
            "Could not load registry records. See the Home Assistant logs.",
        )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/forget",
        vol.Required("selections"): vol.All(
            [
                {
                    vol.Required("kind"): vol.In(["entity", "device"]),
                    vol.Required("id"): str,
                    vol.Required("fingerprint"): str,
                }
            ],
            vol.Length(min=1),
        ),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_forget(hass, connection, msg):
    """Forget selected deleted records after backup and current-state validation."""
    try:
        result = await _inspector(hass).apply(connection.user.id, msg["selections"])
        connection.send_result(msg["id"], result)
    except InspectorError as err:
        connection.send_error(msg["id"], "inspector_error", str(err))
    except Exception:
        _LOGGER.exception("Could not forget saved deleted records")
        connection.send_error(
            msg["id"], "inspector_error", "Could not complete the operation. Check the HA logs."
        )


@callback
def async_register_commands(hass: HomeAssistant) -> None:
    """Register both endpoints with admin checks."""
    for handler in (websocket_list, websocket_forget):
        websocket_api.async_register_command(hass, handler)
