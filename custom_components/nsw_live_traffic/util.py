# // Updated: 2024-07-29
# // Initially created to store utility functions for the NSW Live Traffic integration.
# // - Added haversine_distance function.
# // - Added get_geojson_properties_get_first_url function.
# // - Added get_nested_value function.
"""Utility functions for the NSW Live Traffic integration."""

import logging
from math import radians, sin, cos, sqrt, atan2
from typing import Any, Dict, List, Optional, Union

_LOGGER = logging.getLogger(__name__)

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance in kilometers between two points
    on the earth (specified in decimal degrees).
    """
    if None in [lat1, lon1, lat2, lon2]:
        _LOGGER.debug("Cannot calculate haversine distance with None coordinates.")
        return float('inf') # Return infinity if any coordinate is None

    # Convert decimal degrees to radians
    rlat1, rlon1, rlat2, rlon2 = map(radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlon = rlon2 - rlon1
    dlat = rlat2 - rlat1
    a = sin(dlat / 2)**2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    radius_earth_km = 6371  # Radius of earth in kilometers.
    distance = radius_earth_km * c
    return distance

def get_geojson_properties_get_first_url(properties: Dict[str, Any]) -> Optional[str]:
    """
    Extracts the first available URL from GeoJSON properties.
    Prioritizes 'weblinkUrl', then the first item in 'webLinks' list if 'webLinks' is a list of dicts with 'url'.
    If 'webLinks' is a list of strings, returns the first string.
    """
    if not isinstance(properties, dict):
        return None

    weblink_url = properties.get("weblinkUrl")
    if weblink_url and isinstance(weblink_url, str):
        return weblink_url

    web_links = properties.get("webLinks")
    if isinstance(web_links, list) and web_links:
        first_link = web_links[0]
        if isinstance(first_link, dict) and isinstance(first_link.get("url"), str):
            return first_link.get("url")
        if isinstance(first_link, str): # If it's a list of URL strings
            return first_link
            
    return None

def get_nested_value(data: Dict[str, Any], path: str, default: Any = None) -> Any:
    """
    Safely retrieves a nested value from a dictionary using a dot-separated path.
    Example: get_nested_value(data, "level1.level2.key", "default_value")
    """
    keys = path.split('.')
    current_level = data
    try:
        for key in keys:
            if isinstance(current_level, dict):
                current_level = current_level[key]
            elif isinstance(current_level, list) and key.isdigit(): # Check if key is a digit for list index
                idx = int(key)
                if 0 <= idx < len(current_level): # Check bounds for list index
                    current_level = current_level[idx]
                else:
                    return default # Index out of bounds
            else:
                return default # Not a dict or list, or key is not digit for list
        return current_level
    except (KeyError, TypeError, IndexError) as e:
        _LOGGER.debug("Failed to get nested value for path '%s': %s", path, e)
        return default 