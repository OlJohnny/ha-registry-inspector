"""Every registry endpoint must reject non-administrators."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from homeassistant.exceptions import Unauthorized

from custom_components.registry_inspector import websocket as ws
from custom_components.registry_inspector.config_flow import ConfigFlow


@pytest.mark.parametrize("handler", [ws.websocket_list, ws.websocket_preview, ws.websocket_forget])
@pytest.mark.parametrize("user", [None, SimpleNamespace(id="guest", is_admin=False)])
def test_all_endpoints_require_admin(hass, inspector, handler, user):
    connection = SimpleNamespace(user=user, send_result=Mock(), send_error=Mock())
    with pytest.raises(Unauthorized):
        handler(hass, connection, {"id": 1})
    connection.send_result.assert_not_called()


def test_list_admin_and_unconfigured(hass, inspector):
    connection = SimpleNamespace(
        user=SimpleNamespace(id="admin", is_admin=True), send_result=Mock(), send_error=Mock()
    )
    ws.websocket_list(hass, connection, {"id": 1})
    assert connection.send_result.call_args.args[1]["rows"] == []
    hass.data.pop("registry_inspector")
    ws.websocket_list(hass, connection, {"id": 2})
    assert connection.send_error.call_args.args[1] == "inspector_error"


async def test_config_flow_form_and_single_instance(hass):
    flow = ConfigFlow()
    flow.hass = hass
    result = await flow.async_step_user()
    assert result["type"] == "form"
    result = await flow.async_step_user({})
    assert result["type"] == "create_entry" and result["data"] == {}
