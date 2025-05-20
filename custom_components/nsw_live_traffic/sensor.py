# Version: 0.1.0
# This file defines the sensor entities for the NSW Live Traffic integration.

import logging
from typing import Any, cast, Callable, Coroutine
from datetime import datetime, timezone

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify
from homeassistant.util.location import distance as haversine_distance
from homeassistant.const import UnitOfLength, ATTR_LATITUDE, ATTR_LONGITUDE, ATTR_ATTRIBUTION
from homeassistant.util.dt import utc_from_timestamp

from .const import (
    DOMAIN,
    ATTRIBUTION,
    CONF_HAZARD_TYPES,
    CONF_HOME_RADIUS,
    CONF_DEVICE_TRACKERS,
    CONF_DEVICE_RADIUS,
    DEFAULT_HAZARD_TYPES_API_PATHS,
    DEFAULT_HOME_RADIUS_KM,
    DEFAULT_DEVICE_RADIUS_KM,
    ALL_GRANULAR_HAZARD_TYPES_FOR_SENSORS,
    GRANULAR_TO_PRIMARY_API_PATH_MAP,
    HAZARD_TYPE_DISPLAY_NAME_MAP,
    SENSOR_NAME_NEARBY_HAZARDS_COUNT_PREFIX,
    SENSOR_NAME_NEARBY_HAZARDS_COUNT_SUFFIX,
    MANUFACTURER,
    MODEL,
    CODEOWNER_USERNAME,
    REPO_NAME,
)
from .coordinator import NswLiveTrafficDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the NSW Live Traffic sensor entities."""
    coordinator: NswLiveTrafficDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Get the list of broad API Path hazard categories the user wants to monitor from options
    configured_api_paths = entry.options.get(CONF_HAZARD_TYPES, DEFAULT_HAZARD_TYPES_API_PATHS)

    sensors_to_add = []
    _LOGGER.debug("Configured API paths for data fetching: %s", configured_api_paths)
    _LOGGER.debug("Available granular hazard types for sensor creation: %s", ALL_GRANULAR_HAZARD_TYPES_FOR_SENSORS)

    for granular_hazard_type in ALL_GRANULAR_HAZARD_TYPES_FOR_SENSORS:
        primary_api_path = GRANULAR_TO_PRIMARY_API_PATH_MAP.get(granular_hazard_type)
        
        if primary_api_path and primary_api_path in configured_api_paths:
            # The user has selected the API path that is expected to provide this granular hazard type.
            # So, we create a sensor for this granular type.
            display_name = HAZARD_TYPE_DISPLAY_NAME_MAP.get(granular_hazard_type, granular_hazard_type.replace("_", " ").title())
            
            sensor_description = SensorEntityDescription(
                key=f"nearby_{slugify(granular_hazard_type)}_count",
                name=f"{SENSOR_NAME_NEARBY_HAZARDS_COUNT_PREFIX} {display_name} {SENSOR_NAME_NEARBY_HAZARDS_COUNT_SUFFIX}",
                icon="mdi:traffic-light", # Updated icon, more relevant
            )
            sensors_to_add.append(
                NswLiveTrafficNearbyHazardCountSensor(
                    coordinator=coordinator,
                    description=sensor_description,
                    config_entry_id=entry.entry_id,
                    hazard_type=granular_hazard_type, # This is the specific granular type the sensor will count
                )
            )
            _LOGGER.debug("Preparing sensor for granular hazard type: %s (sourced from API path: %s)", granular_hazard_type, primary_api_path)
        elif not primary_api_path:
            _LOGGER.warning("No primary API path mapping found for granular type '%s', skipping sensor.", granular_hazard_type)
        # If primary_api_path exists but is not in configured_api_paths, we simply don't create the sensor, which is expected.

    if sensors_to_add:
        async_add_entities(sensors_to_add)
        _LOGGER.info("Added %s nearby hazard count sensors.", len(sensors_to_add))
    else:
        _LOGGER.info("No nearby hazard count sensors were added based on current configuration.")


class NswLiveTrafficNearbyHazardCountSensor(CoordinatorEntity[NswLiveTrafficDataUpdateCoordinator], SensorEntity):
    """Sensor representing the count of nearby traffic hazards of a specific type."""

    _attr_has_entity_name = True # Uses the SensorEntityDescription.name as base for entity name
    _attr_attribution = ATTRIBUTION # Moved from __init__ to class level for consistency

    def __init__(
        self,
        coordinator: NswLiveTrafficDataUpdateCoordinator,
        description: SensorEntityDescription,
        config_entry_id: str, # To make unique_id specific to this config entry
        hazard_type: str, # This is a GRANULAR_HAZARD_TYPE
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._hazard_type = hazard_type # Store the specific hazard type this sensor is for
        self.coordinator = coordinator # Ensure coordinator is stored
        self._config_entry_id = coordinator.config_entry.entry_id # Store for unique ID

        # Unique ID: domain_config_entry_id_hazard_type
        self._attr_unique_id = f"{DOMAIN}_{self._config_entry_id}_{slugify(hazard_type)}"
        
        # Device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._config_entry_id)},
            name=self.coordinator.config_entry.title, # Use config entry title
            manufacturer=MANUFACTURER,
            model=MODEL,
            configuration_url="https://github.com/anon145/nsw-live-traffic-ha-custom-component" # Static URL
        )
        self._attr_attribution = ATTRIBUTION

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor (count of nearby hazards of self._hazard_type)."""
        if not self.coordinator.data or "features" not in self.coordinator.data:
            _LOGGER.debug("Coordinator data not available for sensor %s (%s)", self.entity_id, self._hazard_type)
            return 0 # Default to 0 when data isn't ready, or if no hazards

        all_hazards = self.coordinator.data["features"]
        if not isinstance(all_hazards, list):
            _LOGGER.warning("'features' in coordinator data is not a list for sensor %s (%s). Got %s", self.entity_id, self._hazard_type, type(all_hazards))
            return 0

        home_coords = (
            self.hass.config.latitude,
            self.hass.config.longitude
        )
        home_radius_km = self.coordinator.config_entry.options.get(CONF_HOME_RADIUS, DEFAULT_HOME_RADIUS_KM)
        
        device_trackers_to_monitor = self.coordinator.config_entry.options.get(CONF_DEVICE_TRACKERS, [])
        device_radius_km = self.coordinator.config_entry.options.get(CONF_DEVICE_RADIUS, DEFAULT_DEVICE_RADIUS_KM)

        nearby_hazard_count = 0
        counted_hazard_ids: set[str] = set()

        for hazard in all_hazards:
            try:
                properties = hazard.get("properties", {})
                main_category = properties.get("mainCategory")

                # This sensor instance is for a specific granular type (self._hazard_type).
                # It counts features if their mainCategory matches.
                if main_category != self._hazard_type:
                    continue
                
                hazard_id = str(hazard.get("id")) 
                geometry = hazard.get("geometry", {})
                coordinates = geometry.get("coordinates")
                
                if not coordinates or len(coordinates) < 2:
                    _LOGGER.debug("Hazard %s (type %s) missing coordinates, skipping", hazard_id, self._hazard_type)
                    continue
                
                hazard_lat = coordinates[1]
                hazard_lon = coordinates[0]
                is_nearby = False

                if home_coords[0] is not None and home_coords[1] is not None and home_radius_km > 0:
                    distance_to_home_m = haversine_distance(home_coords[0], home_coords[1], hazard_lat, hazard_lon)
                    if distance_to_home_m is not None and (distance_to_home_m / 1000) <= home_radius_km:
                        is_nearby = True
                
                if not is_nearby and device_radius_km > 0:
                    for tracker_entity_id in device_trackers_to_monitor:
                        tracker_state = self.hass.states.get(tracker_entity_id)
                        if tracker_state and tracker_state.attributes.get(ATTR_LATITUDE) and tracker_state.attributes.get(ATTR_LONGITUDE):
                            tracker_lat = tracker_state.attributes[ATTR_LATITUDE]
                            tracker_lon = tracker_state.attributes[ATTR_LONGITUDE]
                            distance_to_device_m = haversine_distance(tracker_lat, tracker_lon, hazard_lat, hazard_lon)
                            if distance_to_device_m is not None and (distance_to_device_m / 1000) <= device_radius_km:
                                is_nearby = True
                                break 
                
                if is_nearby:
                    if hazard_id and hazard_id not in counted_hazard_ids:
                        nearby_hazard_count += 1
                        counted_hazard_ids.add(hazard_id)
                    elif not hazard_id:
                         _LOGGER.debug("Hazard feature for type %s is missing an ID, counting it anyway. Headline: %s", self._hazard_type, properties.get("headline"))
                         nearby_hazard_count += 1 # Count if no ID, cannot deduplicate

            except Exception as e:
                _LOGGER.error("Error processing hazard for sensor %s (%s): %s. Hazard data: %s", self.entity_id, self._hazard_type, e, str(hazard)[:200], exc_info=True)
                continue 
        
        return nearby_hazard_count

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        if not self.coordinator.data or "features" not in self.coordinator.data:
            _LOGGER.debug("Coordinator data not available for sensor attributes %s (%s)", self.entity_id, self._hazard_type)
            return {ATTR_ATTRIBUTION: self._attr_attribution, "nearby_hazards_list": [], "last_updated_list": None}

        all_hazards = self.coordinator.data["features"]
        if not isinstance(all_hazards, list):
            _LOGGER.warning("'features' in coordinator data is not a list for sensor attributes %s (%s)", self.entity_id, self._hazard_type)
            return {ATTR_ATTRIBUTION: self._attr_attribution, "nearby_hazards_list": [], "last_updated_list": None}

        home_coords = (
            self.hass.config.latitude,
            self.hass.config.longitude
        )
        home_radius_km = self.coordinator.config_entry.options.get(CONF_HOME_RADIUS, DEFAULT_HOME_RADIUS_KM)
        
        device_trackers_to_monitor = self.coordinator.config_entry.options.get(CONF_DEVICE_TRACKERS, [])
        device_radius_km = self.coordinator.config_entry.options.get(CONF_DEVICE_RADIUS, DEFAULT_DEVICE_RADIUS_KM)

        nearby_hazards_detail_list = []
        latest_update_timestamp_ms = None # Store as ms for easier comparison
        # Keep track of hazard IDs already added to this list to avoid duplicates in attributes
        # if it somehow passed the native_value deduplication (e.g. if native_value was not called first or had different logic)
        # For attributes, this is mostly for safety, as native_value should handle the core count.
        # However, attributes list all relevant hazards, so duplicates are bad here too.
        added_hazard_ids_for_attributes: set[str] = set()

        for hazard in all_hazards:
            try:
                properties = hazard.get("properties", {})
                main_category = properties.get("mainCategory")

                if main_category != self._hazard_type:
                    continue
                
                hazard_id_api = str(hazard.get("id"))
                if not hazard_id_api or hazard_id_api in added_hazard_ids_for_attributes:
                    if hazard_id_api in added_hazard_ids_for_attributes:
                        _LOGGER.debug("Hazard %s already processed for attributes list of %s, skipping.", hazard_id_api, self._hazard_type)
                    # If no ID, we can't reliably deduplicate for the attributes list here, but it also means it may not have been counted in native_value
                    # For attributes, it's safer to skip if no ID for list consistency unless it's truly desired.
                    # Given native_value might count it, we should probably be consistent or ensure native_value populates IDs for all it counts.
                    # For now, if no ID, we skip for attribute list generation.
                    if not hazard_id_api:
                        _LOGGER.debug("Hazard feature for type %s is missing an ID, skipping for attribute list. Headline: %s", self._hazard_type, properties.get("headline"))
                        continue
                
                geometry = hazard.get("geometry", {})
                coordinates = geometry.get("coordinates")
                
                if not coordinates or len(coordinates) < 2:
                    continue
                
                hazard_lat = coordinates[1]
                hazard_lon = coordinates[0]
                
                distance_val_km = None
                zone_type_val = None
                zone_name_val = None

                if home_coords[0] is not None and home_coords[1] is not None and home_radius_km > 0:
                    dist_home_m = haversine_distance(home_coords[0], home_coords[1], hazard_lat, hazard_lon)
                    if dist_home_m is not None and (dist_home_m / 1000) <= home_radius_km:
                        distance_val_km = round(dist_home_m / 1000, 2)
                        zone_type_val = "home"
                        zone_name_val = self.hass.config.location_name # Use HA's location name for home
                
                if zone_type_val is None and device_radius_km > 0:
                    for tracker_entity_id in device_trackers_to_monitor:
                        tracker_state = self.hass.states.get(tracker_entity_id)
                        if tracker_state and tracker_state.attributes.get(ATTR_LATITUDE) and tracker_state.attributes.get(ATTR_LONGITUDE):
                            tracker_lat = tracker_state.attributes[ATTR_LATITUDE]
                            tracker_lon = tracker_state.attributes[ATTR_LONGITUDE]
                            dist_device_m = haversine_distance(tracker_lat, tracker_lon, hazard_lat, hazard_lon)
                            if dist_device_m is not None and (dist_device_m / 1000) <= device_radius_km:
                                distance_val_km = round(dist_device_m / 1000, 2)
                                zone_type_val = "device_tracker"
                                zone_name_val = tracker_state.name or tracker_entity_id # Use device name or entity_id
                                break 

                if zone_type_val:
                    added_hazard_ids_for_attributes.add(hazard_id_api)
                    last_updated_raw = properties.get("lastUpdated") 
                    last_updated_iso = None
                    if isinstance(last_updated_raw, (int, float)) and last_updated_raw > 0:
                        try:
                            last_updated_iso = datetime.fromtimestamp(last_updated_raw / 1000, tz=timezone.utc).isoformat()
                            if latest_update_timestamp_ms is None or last_updated_raw > latest_update_timestamp_ms:
                                latest_update_timestamp_ms = last_updated_raw
                        except (ValueError, TypeError):
                            _LOGGER.warning("Could not parse lastUpdated timestamp: %s for hazard %s", last_updated_raw, hazard_id_api)
                    
                    web_link_val = properties.get("weblinkUrl")
                    if not web_link_val and properties.get("webLinks"):
                        web_links_list = properties.get("webLinks", [])
                        if isinstance(web_links_list, list) and len(web_links_list) > 0:
                            first_link_obj = web_links_list[0]
                            if isinstance(first_link_obj, dict):
                                web_link_val = first_link_obj.get("url")
                            elif isinstance(first_link_obj, str):
                                web_link_val = first_link_obj # If list of strings
                    
                    hazard_details_for_attr = {
                        "hazard_id": hazard_id_api,
                        "headline": properties.get("headline", "N/A"),
                        "main_category": main_category,
                        "last_updated": last_updated_iso,
                        "distance_km": distance_val_km,
                        "zone_type": zone_type_val,
                        "zone_name": zone_name_val,
                        "latitude": hazard_lat,
                        "longitude": hazard_lon,
                        "web_link": web_link_val,
                        "other_advice": properties.get("otherAdvice"),
                        # Add other relevant fields from PRD F5.3.1 as available
                        "created": utc_from_timestamp(properties.get("created", 0) / 1000).isoformat() if isinstance(properties.get("created"), (int, float)) and properties.get("created", 0) > 0 else None,
                        "sub_category_a": properties.get("subCategoryA"),
                        "roads": [road.get("roadName") for road in properties.get("roads", []) if isinstance(road, dict) and road.get("roadName")],
                        "is_major": properties.get("isMajor"),
                        "impact": properties.get("impact"),
                        "ended": properties.get("ended")
                    }
                    # Filter out None values from this specific hazard detail for cleaner list output
                    nearby_hazards_detail_list.append({k: v for k, v in hazard_details_for_attr.items() if v is not None})

            except Exception as e:
                _LOGGER.error("Error processing hazard for attributes of %s (%s): %s. Hazard: %s", self.entity_id, self._hazard_type, e, str(hazard)[:200], exc_info=True)
                continue

        overall_last_updated_list_iso = None
        if isinstance(latest_update_timestamp_ms, (int, float)) and latest_update_timestamp_ms > 0:
            try:
                overall_last_updated_list_iso = datetime.fromtimestamp(latest_update_timestamp_ms / 1000, tz=timezone.utc).isoformat()
            except (ValueError, TypeError):
                 _LOGGER.warning("Could not parse overall latest_update_timestamp_ms for attributes: %s", latest_update_timestamp_ms)

        return {
            ATTR_ATTRIBUTION: self._attr_attribution,
            "nearby_hazards_list": nearby_hazards_detail_list,
            "last_updated_list": overall_last_updated_list_iso, 
        } 