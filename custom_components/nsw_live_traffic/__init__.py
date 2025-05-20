# Version: 0.1.0
# This file is the main entry point for the NSW Live Traffic Home Assistant integration.
# It sets up the integration and handles unloading when Home Assistant stops or the integration is removed.

# Updated: 2024-07-29
# - Added setup for geo_location platform.
# - Added PLATFORMS constant.

import logging
import aiohttp
import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_API_KEY, PLATFORMS
from .api import NswLiveTrafficApiClient, ApiError, InvalidApiKeyError, ApiForbiddenError
from .coordinator import NswLiveTrafficDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# List of platforms to support in this integration.
# These will be set up by the DataUpdateCoordinator.
# PLATFORMS: list[str] = ["sensor", "geo_location"] # Will be uncommented as platforms are built

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up NSW Live Traffic from a config entry."""
    _LOGGER.debug("Setting up NSW Live Traffic integration for entry: %s", entry.entry_id)
    hass.data.setdefault(DOMAIN, {})

    api_key = entry.data.get(CONF_API_KEY)
    if not api_key:
        _LOGGER.error("API key not found in config entry data.")
        return False # Should not happen if config flow is correct

    # Create an aiohttp session and our API client instance
    session = async_get_clientsession(hass)
    api_client = NswLiveTrafficApiClient(session, api_key)

    # Create the DataUpdateCoordinator
    coordinator = NswLiveTrafficDataUpdateCoordinator(
        hass,
        api_client=api_client,
        config_entry=entry,
    )

    # Perform the initial data fetch. If this fails, bail out.
    # ConfigEntryNotReady will be raised by the coordinator if initial fetch fails due to API errors.
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed: # Specific exception from coordinator
        _LOGGER.error("Authentication failed during initial refresh. Check API key.")
        raise # Re-raise to let HA handle it
    except ApiError as err: # Broader API errors handled by coordinator, re-raise as ConfigEntryNotReady
        _LOGGER.error("API error during initial refresh: %s", err)
        raise ConfigEntryNotReady(f"Failed to connect to NSW Live Traffic API: {err}") from err
    except Exception as err: # Catch any other unexpected error during setup
        _LOGGER.error("Unexpected error during initial refresh: %s", err, exc_info=True)
        raise ConfigEntryNotReady(f"Unexpected error setting up NSW Live Traffic: {err}") from err

    if not coordinator.last_update_success:
        # This case might be redundant if async_config_entry_first_refresh raises appropriately
        _LOGGER.error("Initial data fetch failed for NSW Live Traffic.")
        raise ConfigEntryNotReady("Failed to fetch initial data for NSW Live Traffic.")

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Set up platforms
    # Using hass.config_entries.async_setup_platforms which is the modern way
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Add options update listener
    entry.add_update_listener(options_update_listener)
    
    _LOGGER.info("NSW Live Traffic integration successfully set up for entry: %s", entry.entry_id)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading NSW Live Traffic integration for entry: %s", entry.entry_id)
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.info("NSW Live Traffic integration successfully unloaded for entry: %s", entry.entry_id)

    return unload_ok

async def options_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    _LOGGER.debug("NSW Live Traffic options updated for entry %s, reloading integration.", entry.entry_id)
    # Reload the integration to apply changes
    await hass.config_entries.async_reload(entry.entry_id) 