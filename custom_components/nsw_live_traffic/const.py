# Version: 0.1.0
# This file contains constants used by the NSW Live Traffic Home Assistant integration.
# Changes:
# - Added MANUFACTURER and MODEL constants.

from datetime import timedelta
from typing import Final, List, Dict

DOMAIN: Final[str] = "nsw_live_traffic"

ATTRIBUTION: Final[str] = "Data provided by Transport for NSW"

# Constants for Device Info
MANUFACTURER: Final[str] = "Transport for NSW"
MODEL: Final[str] = "Live Traffic Data"

# API Configuration
API_ENDPOINT_BASE: Final[str] = "https://api.transport.nsw.gov.au/v1/live/hazards"
API_PARAM_FORMAT: Final[str] = "geojson"
API_HEADER_ACCEPT: Final[str] = "application/json"
API_TIMEOUT_SECONDS: Final[int] = 20 # Increased timeout

# API Path Segments (for selecting hazard categories as per Swagger)
API_PATH_ALPINE: Final[str] = "alpine"
API_PATH_FIRE: Final[str] = "fire"
API_PATH_FLOOD: Final[str] = "flood"
API_PATH_INCIDENT: Final[str] = "incident" # Covers accidents, breakdowns, hazards etc.
API_PATH_MAJOREVENT: Final[str] = "majorevent"
API_PATH_ROADWORK: Final[str] = "roadwork"
# Other paths from Swagger - can be added if deemed necessary later
# API_PATH_REGIONAL_LGA_INCIDENT: Final[str] = "regional-lga-incident"
# API_PATH_REGIONAL_LGA_PARTICIPATION: Final[str] = "regional-lga-participation"

# Default Configuration Values
DEFAULT_SCAN_INTERVAL_MINUTES: Final[int] = 5
MIN_SCAN_INTERVAL_MINUTES: Final[int] = 1
DEFAULT_HOME_RADIUS_KM: Final[float] = 10.0
DEFAULT_DEVICE_RADIUS_KM: Final[float] = 5.0

# Configuration Keys
CONF_API_KEY: Final[str] = "api_key"
CONF_HAZARD_TYPES: Final[str] = "hazard_types" # This will now store a list of API_PATH_... values
CONF_HOME_RADIUS: Final[str] = "home_radius"
CONF_DEVICE_TRACKERS: Final[str] = "device_trackers"
CONF_DEVICE_RADIUS: Final[str] = "device_radius"
CONF_SCAN_INTERVAL: Final[str] = "scan_interval"

# Granular Hazard Types (based on 'mainCategory' field in API response features)
# These are used for sensor creation and display names AFTER data is fetched.
GRANULAR_HAZARD_TYPE_ACCIDENT: Final[str] = "accident"
GRANULAR_HAZARD_TYPE_BREAKDOWN: Final[str] = "breakdown"
GRANULAR_HAZARD_TYPE_ROADWORK: Final[str] = "roadwork"
GRANULAR_HAZARD_TYPE_FIRE: Final[str] = "fire"
GRANULAR_HAZARD_TYPE_FLOODING: Final[str] = "flooding"
GRANULAR_HAZARD_TYPE_HEAVY_VEHICLE: Final[str] = "heavy_vehicle"
GRANULAR_HAZARD_TYPE_HAZARD: Final[str] = "hazard"  # General hazard
GRANULAR_HAZARD_TYPE_SPECIAL_EVENT: Final[str] = "special_event"
GRANULAR_HAZARD_TYPE_ALPINE: Final[str] = "alpine"
GRANULAR_HAZARD_TYPE_DIVERSION: Final[str] = "diversion"
GRANULAR_HAZARD_TYPE_CHANGED_TRAFFIC_CONDITIONS: Final[str] = "changedtrafficconditions"

# List of all API Path segments offered to the user for selection in config flow
ALL_HAZARD_TYPES_API_PATHS: Final[List[str]] = [
    API_PATH_INCIDENT, # Broad category, likely includes accidents, breakdowns, general hazards
    API_PATH_ROADWORK,
    API_PATH_FIRE,
    API_PATH_FLOOD,
    API_PATH_MAJOREVENT,
    API_PATH_ALPINE,
]

# Default API Path segments to monitor if user doesn't specify
DEFAULT_HAZARD_TYPES_API_PATHS: Final[List[str]] = [
    API_PATH_INCIDENT,
    API_PATH_ROADWORK,
    API_PATH_FIRE,
    API_PATH_FLOOD,
]

# Mapping from Granular Hazard Types to the Primary API Path that provides them
# This helps sensor.py create relevant granular sensors based on user's API Path selections.
GRANULAR_TO_PRIMARY_API_PATH_MAP: Final[Dict[str, str]] = {
    GRANULAR_HAZARD_TYPE_ACCIDENT: API_PATH_INCIDENT,
    GRANULAR_HAZARD_TYPE_BREAKDOWN: API_PATH_INCIDENT,
    GRANULAR_HAZARD_TYPE_HAZARD: API_PATH_INCIDENT, 
    GRANULAR_HAZARD_TYPE_HEAVY_VEHICLE: API_PATH_INCIDENT,
    GRANULAR_HAZARD_TYPE_ROADWORK: API_PATH_ROADWORK,
    GRANULAR_HAZARD_TYPE_FIRE: API_PATH_FIRE,
    GRANULAR_HAZARD_TYPE_FLOODING: API_PATH_FLOOD,
    GRANULAR_HAZARD_TYPE_SPECIAL_EVENT: API_PATH_MAJOREVENT,
    GRANULAR_HAZARD_TYPE_ALPINE: API_PATH_ALPINE,
    GRANULAR_HAZARD_TYPE_DIVERSION: API_PATH_INCIDENT, # Estimate: diversions often due to incidents
    GRANULAR_HAZARD_TYPE_CHANGED_TRAFFIC_CONDITIONS: API_PATH_INCIDENT, # Estimate
}

# List of granular types for which specific sensors will be created if their primary API path is selected.
ALL_GRANULAR_HAZARD_TYPES_FOR_SENSORS: Final[List[str]] = list(GRANULAR_TO_PRIMARY_API_PATH_MAP.keys())

# Mapping from granular hazard type (mainCategory from API, lowercase) to a user-friendly display name
# This map is used for sensor names and potentially other display purposes.
HAZARD_TYPE_DISPLAY_NAME_MAP: Final[Dict[str, str]] = {
    GRANULAR_HAZARD_TYPE_ACCIDENT: "Accidents",
    GRANULAR_HAZARD_TYPE_BREAKDOWN: "Breakdowns",
    GRANULAR_HAZARD_TYPE_ROADWORK: "Roadworks",
    GRANULAR_HAZARD_TYPE_FIRE: "Fires",
    GRANULAR_HAZARD_TYPE_FLOODING: "Flooding",
    GRANULAR_HAZARD_TYPE_HEAVY_VEHICLE: "Heavy Vehicle Issues",
    GRANULAR_HAZARD_TYPE_HAZARD: "General Hazards",
    GRANULAR_HAZARD_TYPE_SPECIAL_EVENT: "Special Events",
    GRANULAR_HAZARD_TYPE_ALPINE: "Alpine Conditions",
    GRANULAR_HAZARD_TYPE_DIVERSION: "Diversions",
    GRANULAR_HAZARD_TYPE_CHANGED_TRAFFIC_CONDITIONS: "Changed Traffic Conditions",
    "incident": "Incidents", # Catch-all for generic incidents from the incident path if mainCategory is just 'incident'
    "majorevent": "Major Events", # Catch-all for generic major events
}

# Platforms to set up
PLATFORMS: Final[List[str]] = ["sensor", "geo_location"]

# Event Types for internal and external communication
EVENT_HAZARDS_UPDATED: Final[str] = f"{DOMAIN}_hazards_updated" # General update event

# Specific events for automation triggers as per PRD F4
EVENT_NEW_HAZARD_NEARBY: Final[str] = f"{DOMAIN}_new_hazard_nearby"
EVENT_HAZARD_CLEARED_NEARBY: Final[str] = f"{DOMAIN}_hazard_cleared_nearby"
EVENT_HAZARD_DETAILS_UPDATED: Final[str] = f"{DOMAIN}_hazard_details_updated"

# Sensor specific constants
SENSOR_NAME_NEARBY_HAZARDS_COUNT_PREFIX: Final[str] = "Nearby"
SENSOR_NAME_NEARBY_HAZARDS_COUNT_SUFFIX: Final[str] = "Hazards" 