# Version: 0.1.0
# This file defines the DataUpdateCoordinator for the NSW Live Traffic integration.

import logging
from typing import Any
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryAuthFailed

from .api import (NswLiveTrafficApiClient, ApiError, InvalidApiKeyError, ApiForbiddenError)
from .const import (
    DOMAIN,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    CONF_HAZARD_TYPES,
    DEFAULT_HAZARD_TYPES_API_PATHS,
    CONF_SCAN_INTERVAL # For getting scan interval in minutes from options
)

_LOGGER = logging.getLogger(__name__)

class NswLiveTrafficDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Manages fetching data from the TfNSW Live Traffic API."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: NswLiveTrafficApiClient,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the data update coordinator."""
        self.api_client = api_client
        self.config_entry = config_entry

        # Get scan interval from options, fallback to entry data (initial setup), then default.
        # Options flow will store scan_interval in minutes.
        scan_interval_minutes = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            DEFAULT_SCAN_INTERVAL_MINUTES
        )
        update_interval = timedelta(minutes=scan_interval_minutes)
        if update_interval < timedelta(minutes=1):
            _LOGGER.warning(
                "Scan interval configured too low (%s minutes), defaulting to 1 minute to avoid excessive API calls.",
                scan_interval_minutes
            )
            update_interval = timedelta(minutes=1)
        
        _LOGGER.info(
            "NSW Live Traffic coordinator initialized with update interval: %s", 
            update_interval
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from TfNSW Live Traffic API."""
        selected_hazard_types = self.config_entry.options.get(
            CONF_HAZARD_TYPES, DEFAULT_HAZARD_TYPES_API_PATHS
        )
        
        _LOGGER.debug("Fetching hazards for types: %s", selected_hazard_types)

        try:
            # Subtask 1.3.2.2: Call api_client.async_get_hazards()
            # Subtask 1.3.2.1: Retrieve configured hazard types (done above)
            data = await self.api_client.async_get_hazards(selected_api_paths=selected_hazard_types)
            
            # Subtask 1.3.2.3: Perform any necessary transformation (minimal for now)
            # For now, we assume the API returns a GeoJSON FeatureCollection as a dict.
            # We might want to validate the structure here or extract just the features list.
            if not isinstance(data, dict) or "features" not in data:
                _LOGGER.error("API data is not in expected format (missing 'features'): %s", str(data)[:200])
                raise UpdateFailed("Invalid data format received from API")
            
            _LOGGER.debug("Successfully fetched %s features.", len(data.get("features", [])))
            # Subtask 1.3.2.4: Return the processed data dictionary.
            return data
        except InvalidApiKeyError as err:
            _LOGGER.error("Invalid API Key: %s", err)
            # This will call async_handle_auth_error on the config flow
            raise ConfigEntryAuthFailed(err) from err
        except ApiForbiddenError as err:
            _LOGGER.error("API Forbidden Error: %s", err)
            # For forbidden, it might not be an auth issue that user can fix via reauth.
            # Raising UpdateFailed might be more appropriate if it's a persistent permission issue.
            raise UpdateFailed(f"API access forbidden: {err}") from err
        except ApiError as err:
            _LOGGER.error("API Error fetching data: %s", err)
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error fetching data: %s", err)
            raise UpdateFailed(f"Unexpected error: {err}") from err 