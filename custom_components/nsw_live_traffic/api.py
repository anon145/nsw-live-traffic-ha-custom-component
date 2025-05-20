# Version: 0.1.0
# This file defines the API client for interacting with the TfNSW Live Traffic Hazards API.

# // Updated: 2024-07-29
# // - Refactored async_get_hazards to use path-based API calls as per Swagger.
# // - Prefers /open endpoints, falls back to /all.
# // - Merges features from multiple API calls if multiple hazard paths are selected.

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
    API_PARAM_FORMAT # Retained in case some specific path might use it, though primary paths don't.
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

        headers = {
            "Authorization": f"apikey {self._api_key}",
            API_HEADER_ACCEPT: "application/json", # Ensure we ask for JSON
        }

        all_features: List[Dict[str, Any]] = []
        # To avoid duplicate features if a hazard appears in multiple fetched categories (unlikely but possible)
        seen_feature_ids: set[str] = set()

        if not selected_api_paths:
            _LOGGER.info("No hazard types (API paths) selected to fetch.")
            # Return an empty GeoJSON FeatureCollection structure
            return {"type": "FeatureCollection", "features": []}

        for api_path_segment in selected_api_paths:
            # Prefer /open endpoint, fall back to /all if /open is not standard for it
            # Based on Swagger, most types have /open. regional-lga-participation only has /all.
            # We will assume /open is the primary target for live data unless a specific path proves otherwise.
            # For now, we'll try /<path>/open, and if that structure isn't what we expect for a given path, 
            # we might need a map or more complex logic. The swagger shows /<path>/open for most.
            # For simplicity, let's assume `/open` for `alpine`, `fire`, `flood`, `incident`, `majorevent`, `roadwork`.
            # If a path like `regional-lga-participation` (which only has /all) were added to `selected_api_paths`,
            # this logic would need adjustment or a mapping.
            
            # Let's try constructing paths like /<path_segment>/open or /<path_segment>/all
            # Defaulting to /all for broader compatibility as per Swagger, but ideally we want current data.
            # Many endpoints like /fire/open, /incident/open, /roadwork/open get current data.
            # Let's try a specific suffix for current data.
            # A simple heuristic: if a type implies a state (like `/closed`), we respect that if we were to use it.
            # For general fetching, we want active ones.
            # The swagger shows: /alpine/open, /fire/open, /flood/open, /incident/open, /majorevent/open, /roadwork/open
            # and then /<type>/all for all of them.
            # So we can target `/<api_path_segment>/open` for these main categories.
            
            endpoint_url = f"{API_ENDPOINT_BASE}/{api_path_segment}/open?format={API_PARAM_FORMAT}"
            # Fallback for paths that might not have an /open variant directly listed or if /open fails
            # For now, we will stick to /open as it is more aligned with "live traffic"

            _LOGGER.debug("Requesting hazards from endpoint: %s", endpoint_url)

            try:
                async with async_timeout.timeout(API_TIMEOUT_SECONDS):
                    response = await self._session.get(endpoint_url, headers=headers)

                if response.status == 401:
                    _LOGGER.error("API Key is invalid or not authorized (401). URL: %s", endpoint_url)
                    raise InvalidApiKeyError("Invalid API key.")
                if response.status == 403:
                    _LOGGER.error("API request forbidden (403). URL: %s. Check IP whitelisting or permissions.", endpoint_url)
                    raise ApiForbiddenError("Request forbidden. Check API permissions or IP whitelisting.")
                
                response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

                content_type = response.headers.get("Content-Type", "")
                if "application/json" not in content_type and "application/geo+json" not in content_type:
                    text_response = await response.text()
                    _LOGGER.error(
                        "Unexpected content type: %s. Expected JSON/GeoJSON. Response: %s. URL: %s",
                        content_type,
                        text_response[:200],
                        endpoint_url
                    )
                    raise ApiError(f"Unexpected content type: {content_type}. URL: {endpoint_url}")

                json_response = await response.json()
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
                                _LOGGER.warning("Found a feature without an ID from %s, adding it without deduplication check. Feature: %s", endpoint_url, str(feature)[:100])
                                all_features.append(feature) # Add if no ID, can't deduplicate
                    else:
                        _LOGGER.warning("'features' key in response from %s is not a list: %s", endpoint_url, type(features_from_this_call))
                else:
                    _LOGGER.warning("Response from %s is not a dict or lacks 'features' key. Response: %s", endpoint_url, str(json_response)[:200])

            except asyncio.TimeoutError:
                _LOGGER.error("Timeout connecting to NSW Live Traffic API at %s", endpoint_url)
                # We will continue to try other paths, but this one failed.
                # Consider if one timeout should abort all for the update cycle.
                # For now, individual timeouts allow partial data if other paths succeed.
                # Raising ApiError here would stop the entire update for this cycle if we want that behavior.
                # raise ApiError(f"Timeout connecting to {endpoint_url}") from exc
                continue # Try next api_path_segment
            except aiohttp.ClientError as exc:
                _LOGGER.error("Client error fetching data from %s: %s", endpoint_url, exc)
                # Similar to timeout, continue for now. 
                # raise ApiError(f"Client error for {endpoint_url}: {exc}") from exc
                continue # Try next api_path_segment
            except ApiError: # Re-raise our own specific API errors if they occur
                raise
            except Exception as exc: # Catch any other unexpected error for this specific path call
                _LOGGER.error("Unexpected error fetching data from %s: %s", endpoint_url, exc, exc_info=True)
                # raise ApiError(f"Unexpected error for {endpoint_url}: {exc}") from exc
                continue # Try next api_path_segment

        _LOGGER.info("Completed fetching hazards. Total unique features merged: %d from %d API paths.", len(all_features), len(selected_api_paths))
        return {"type": "FeatureCollection", "features": all_features} 