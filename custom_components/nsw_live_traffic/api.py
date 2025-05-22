# Version: 0.1.0
# This file defines the API client for interacting with the TfNSW Live Traffic Hazards API.

# // Updated: 2024-07-29
# // - Refactored async_get_hazards to use path-based API calls as per Swagger.
# // - Prefers /open endpoints, falls back to /all.
# // - Merges features from multiple API calls if multiple hazard paths are selected.
# // Updated: 2024-07-30 (Previous date was illustrative, actual date of this change)
# // - Added a 1-second delay between API calls in the async_get_hazards loop to mitigate potential rate limiting.
# // Updated: 2024-07-31
# // - CRITICAL FIX: Explicitly ensure no parameters are being sent to the API.
# // - Added detailed logging to debug API calls.

import asyncio
import logging
from typing import Any, Dict, List, Optional

import async_timeout
import aiohttp

from homeassistant.exceptions import HomeAssistantError

from .const import (
    API_ENDPOINT_BASE,
    API_HEADER_ACCEPT,
    API_TIMEOUT_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

class ApiError(HomeAssistantError):
    """Generic API error."""
    pass

class InvalidApiKeyError(ApiError):
    """Error for invalid API key."""
    pass

class ApiForbiddenError(ApiError):
    """Error for API forbidden access (permissions, etc.)."""
    pass

class NswLiveTrafficApiClient:
    """Client to interact with the TfNSW Live Traffic Hazards API."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str):
        """Initialize the API client."""
        self._session = session
        self._api_key = api_key

    async def async_get_hazards(
        self, selected_api_paths: List[str] # Expects a list of API_PATH_... constants
    ) -> Dict[str, Any]:
        """Fetch hazards from the API for selected path segments."""
        if not self._api_key:
            _LOGGER.error("API key is not set.")
            raise InvalidApiKeyError("API Key not configured.")

        # SIMPLIFIED HEADERS - exactly matching the working test script
        headers = {
            "Authorization": f"apikey {self._api_key}",
            "Accept": "application/json",
        }

        all_features: List[Dict[str, Any]] = []
        # To avoid duplicate features if a hazard appears in multiple fetched categories (unlikely but possible)
        seen_feature_ids: set[str] = set()

        if not selected_api_paths:
            _LOGGER.info("No hazard types (API paths) selected to fetch.")
            # Return an empty GeoJSON FeatureCollection structure
            return {"type": "FeatureCollection", "features": []}

        for idx, api_path_segment in enumerate(selected_api_paths):
            # SIMPLIFIED URL CONSTRUCTION - exactly matching the working test script format
            endpoint_url = f"{API_ENDPOINT_BASE}/{api_path_segment}/open"
            
            # EMERGENCY DEBUG LOGGING - to verify exactly what's being sent
            _LOGGER.error("EMERGENCY DEBUG - Calling endpoint: %s", endpoint_url)
            _LOGGER.error("EMERGENCY DEBUG - Headers: %s", headers)
            _LOGGER.error("EMERGENCY DEBUG - Using version 0.2.1 emergency fix")

            try:
                # SIMPLIFIED REQUEST - matching the test script with no params
                response = await self._session.get(
                    url=endpoint_url,
                    headers=headers,
                )

                if response.status == 401:
                    _LOGGER.error("API Key is invalid or not authorized (401). URL: %s", endpoint_url)
                    raise InvalidApiKeyError("Invalid API key.")
                if response.status == 403:
                    _LOGGER.error("API request forbidden (403). URL: %s. Check IP whitelisting or permissions.", endpoint_url)
                    raise ApiForbiddenError("Request forbidden. Check API permissions or IP whitelisting.")
                
                response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

                # Get the response as text first for debugging
                response_text = await response.text()
                _LOGGER.debug("Raw response: %s", response_text[:200])
                
                # Then parse as JSON
                json_response = {}
                try:
                    json_response = await response.json()
                except Exception as e:
                    _LOGGER.error("Failed to parse JSON response: %s. Raw response: %s", e, response_text[:200])
                    continue

                _LOGGER.debug("Successfully fetched data from %s", endpoint_url)

                if isinstance(json_response, dict) and "features" in json_response:
                    features_from_this_call = json_response.get("features", [])
                    if isinstance(features_from_this_call, list):
                        for feature in features_from_this_call:
                            feature_id = str(feature.get("id"))
                            if feature_id and feature_id not in seen_feature_ids:
                                all_features.append(feature)
                                seen_feature_ids.add(feature_id)
                            elif not feature_id:
                                _LOGGER.warning("Found a feature without an ID from %s, adding it without deduplication check.", endpoint_url)
                                all_features.append(feature) # Add if no ID, can't deduplicate
                    else:
                        _LOGGER.warning("'features' key in response from %s is not a list: %s", endpoint_url, type(features_from_this_call))
                else:
                    _LOGGER.warning("Response from %s is not a dict or lacks 'features' key.", endpoint_url)

            except asyncio.TimeoutError:
                _LOGGER.error("Timeout connecting to NSW Live Traffic API at %s", endpoint_url)
                if idx < len(selected_api_paths) - 1:
                    await asyncio.sleep(1)
                continue 
            except aiohttp.ClientResponseError as exc:
                _LOGGER.error(
                    "ClientResponseError fetching data from %s: Status: %s, Message: %s",
                    endpoint_url,
                    exc.status,
                    exc.message,
                )
                if idx < len(selected_api_paths) - 1:
                    await asyncio.sleep(1)
                continue 
            except aiohttp.ClientError as exc: # General ClientError for non-response errors (e.g. connection issues)
                _LOGGER.error("ClientError (non-response) fetching data from %s: %s", endpoint_url, exc)
                if idx < len(selected_api_paths) - 1:
                    await asyncio.sleep(1)
                continue
            except ApiError: 
                raise
            except Exception as exc: 
                _LOGGER.error("Unexpected error fetching data from %s: %s", endpoint_url, exc, exc_info=True)
                if idx < len(selected_api_paths) - 1:
                    await asyncio.sleep(1)
                continue
            
            # If try block was successful and no 'continue' was hit:
            if idx < len(selected_api_paths) - 1:
                await asyncio.sleep(1)

        _LOGGER.info("Completed fetching hazards. Total unique features merged: %d from %d API paths.", len(all_features), len(selected_api_paths))
        return {"type": "FeatureCollection", "features": all_features} 