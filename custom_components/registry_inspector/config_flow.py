"""Configure one Registry Inspector panel."""

import probatio as vol
from homeassistant import config_entries

from .const import DOMAIN, TITLE


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Set up the panel without credentials or YAML."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Create a single instance."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(title=TITLE, data={})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))
