# Version: 0.1.0
# This file defines the configuration flow for the NSW Live Traffic integration.

import logging
from typing import Any, Dict, Optional, cast

import voluptuous as vol
import aiohttp

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_HAZARD_TYPES,
    CONF_HOME_RADIUS,
    CONF_DEVICE_TRACKERS,
    CONF_DEVICE_RADIUS,
    CONF_SCAN_INTERVAL,
    ALL_HAZARD_TYPES_API_PATHS,
    DEFAULT_HAZARD_TYPES_API_PATHS,
    DEFAULT_HOME_RADIUS_KM,
    DEFAULT_DEVICE_RADIUS_KM,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES
)
from .api import NswLiveTrafficApiClient, InvalidApiKeyError, ApiError, ApiForbiddenError

_LOGGER = logging.getLogger(__name__)

@config_entries.HANDLERS.register(DOMAIN)
class NswLiveTrafficConfigFlow(config_entries.ConfigFlow):
    """Handle a config flow for NSW Live Traffic."""

    VERSION = 1

    async def _validate_api_key(self, api_key: str) -> Optional[str]:
        """Validate the API key by making a test call."""
        session = async_get_clientsession(self.hass)
        client = NswLiveTrafficApiClient(session, api_key)
        try:
            # Test call with default (or minimal) hazard types to ensure API key is working
            # Using DEFAULT_HAZARD_TYPES_API_PATHS for the test call
            await client.async_get_hazards(DEFAULT_HAZARD_TYPES_API_PATHS) 
        except InvalidApiKeyError:
            _LOGGER.warning("API key validation failed: Invalid API Key")
            return "invalid_auth"
        except ApiForbiddenError:
            _LOGGER.warning("API key validation failed: API Forbidden (check IP whitelist/permissions)")
            return "api_forbidden" # Consider adding a new translation string for this
        except ApiError as e:
            _LOGGER.error("API key validation failed: API Error: %s", e)
            return "cannot_connect" # Generic connection error
        except Exception as e: # Catch any other unexpected error
            _LOGGER.error("API key validation failed: Unexpected error: %s", e, exc_info=True)
            return "unknown" # Generic unknown error
        return None

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> config_entries.FlowResult:
        """Handle the initial step."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            
            # Set a unique ID for the config entry based on the domain, to allow only one instance
            # If you want to allow multiple instances (e.g., with different API keys or settings),
            # you'd use a unique ID derived from the API key or a user-provided name.
            # For this integration, one instance is typical.
            await self.async_set_unique_id(DOMAIN) 
            self._abort_if_unique_id_configured()

            validation_error = await self._validate_api_key(api_key)
            if validation_error:
                errors["base"] = validation_error
            else:
                _LOGGER.info("API key validated successfully.")
                # API key is valid, create the entry. Options will be set in the options flow.
                return self.async_create_entry(
                    title="NSW Live Traffic", 
                    data=user_input, # Store API key here
                    options={ # Initialize with default options
                        CONF_HAZARD_TYPES: DEFAULT_HAZARD_TYPES_API_PATHS,
                        CONF_HOME_RADIUS: DEFAULT_HOME_RADIUS_KM,
                        CONF_DEVICE_TRACKERS: [],
                        CONF_DEVICE_RADIUS: DEFAULT_DEVICE_RADIUS_KM,
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL_MINUTES,
                    }
                )

        # Schema for the user input form (API Key)
        data_schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return NswLiveTrafficOptionsFlowHandler(config_entry)


class NswLiveTrafficOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle an options flow for NSW Live Traffic."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        # Make a mutable copy of the options for modification
        self.options = dict(config_entry.options)

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> config_entries.FlowResult:
        """Manage the options."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            # Validate radii and scan interval
            home_radius = user_input.get(CONF_HOME_RADIUS, DEFAULT_HOME_RADIUS_KM)
            device_radius = user_input.get(CONF_DEVICE_RADIUS, DEFAULT_DEVICE_RADIUS_KM)
            scan_interval = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES)

            if not isinstance(home_radius, (int, float)) or home_radius < 0:
                errors[CONF_HOME_RADIUS] = "invalid_radius"
            if not isinstance(device_radius, (int, float)) or device_radius < 0:
                errors[CONF_DEVICE_RADIUS] = "invalid_radius"
            if not isinstance(scan_interval, int) or scan_interval < MIN_SCAN_INTERVAL_MINUTES:
                errors[CONF_SCAN_INTERVAL] = "invalid_scan_interval"
            
            if not errors:
                # Update the options dictionary with the new values
                self.options.update(user_input)
                _LOGGER.debug("Updating options to: %s", self.options)
                return self.async_create_entry(title="", data=self.options)

        # Define the options schema
        # The `suggested_value` will pre-fill the form with current options or defaults.
        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_HAZARD_TYPES,
                    default=self.options.get(CONF_HAZARD_TYPES, DEFAULT_HAZARD_TYPES_API_PATHS),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=ALL_HAZARD_TYPES_API_PATHS, 
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST, # Dropdown for multiple items
                        # Consider adding translation_key if you want to translate option display names
                    )
                ),
                vol.Optional(
                    CONF_HOME_RADIUS,
                    default=self.options.get(CONF_HOME_RADIUS, DEFAULT_HOME_RADIUS_KM),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="km"
                    )
                ),
                vol.Optional(
                    CONF_DEVICE_TRACKERS,
                    default=self.options.get(CONF_DEVICE_TRACKERS, []),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="device_tracker", multiple=True)
                ),
                vol.Optional(
                    CONF_DEVICE_RADIUS,
                    default=self.options.get(CONF_DEVICE_RADIUS, DEFAULT_DEVICE_RADIUS_KM),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="km"
                    )
                ),
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=self.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL_MINUTES, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="minutes"
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=options_schema, errors=errors
        ) 