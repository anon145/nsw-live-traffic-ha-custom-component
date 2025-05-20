# // Updated: 2024-07-29
# // Initially created to define geolocation entities for NSW Live Traffic hazards.
# // - Added NswLiveTrafficHazardGeoLocationEntity class structure.
# // - Implemented async_setup_entry.
# // - Defined basic properties for the geolocation entity.
# // - Added logic to create entities based on fetched hazards.
# // - Changed update_entities to be an async function to support await for entity removal.
# // - Ensured hass.data["entity_registry"] is correctly accessed via entity_platform.async_get_entity_registry.
# // - Added firing of specific events: EVENT_NEW_HAZARD_NEARBY, EVENT_HAZARD_CLEARED_NEARBY, EVENT_HAZARD_DETAILS_UPDATED.
# // - Defined SIGNIFICANT_ATTRIBUTE_KEYS for tracking detail changes.
# // - Added Final import and state change listeners for device_trackers.
"""Geolocation platform for nsw_live_traffic."""
import logging
from typing import Any, Dict, List, Optional, Tuple, Set, Final

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify
from homeassistant.util.dt import utc_from_timestamp
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    ATTRIBUTION,
    CONF_DEVICE_RADIUS,
    CONF_DEVICE_TRACKERS,
    CONF_HOME_RADIUS,
    DEFAULT_DEVICE_RADIUS_KM,
    DEFAULT_HOME_RADIUS_KM,
    DOMAIN,
    EVENT_HAZARDS_UPDATED,
    EVENT_NEW_HAZARD_NEARBY,
    EVENT_HAZARD_CLEARED_NEARBY,
    EVENT_HAZARD_DETAILS_UPDATED,
    HAZARD_TYPE_DISPLAY_NAME_MAP
)
from .coordinator import NswLiveTrafficDataUpdateCoordinator
from .util import get_geojson_properties_get_first_url, haversine_distance

_LOGGER = logging.getLogger(__name__)

# Attributes considered significant for firing EVENT_HAZARD_DETAILS_UPDATED
SIGNIFICANT_ATTRIBUTE_KEYS: Final[Set[str]] = {
    "main_category",
    "advice_a",
    "other_advice",
    "roads", # Change in affected roads
    "start_time",
    "end_time",
    "duration_minutes",
    "impact",
    "ended",
    "is_major"
}

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the NSW Live Traffic geolocation entities."""
    coordinator: NswLiveTrafficDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]
    entity_registry = er.async_get(hass)

    tracked_entities: Dict[str, NswLiveTrafficHazardGeoLocationEntity] = {}

    @callback
    async def update_entities() -> None:
        """Update geolocation entities and fire specific events."""
        new_entities_to_add_to_ha: List[NswLiveTrafficHazardGeoLocationEntity] = []
        current_tracked_ids = set(tracked_entities.keys())
        hazards_in_scope: Dict[str, Dict[str, Any]] = {} # hazard_id: hazard_data

        if coordinator.data and "features" in coordinator.data:
            home_zone_state = hass.states.get("zone.home")
            home_latitude = None
            home_longitude = None
            if home_zone_state and home_zone_state.attributes:
                home_latitude = home_zone_state.attributes.get("latitude")
                home_longitude = home_zone_state.attributes.get("longitude")
            
            home_radius_km = coordinator.config_entry.options.get(
                CONF_HOME_RADIUS, DEFAULT_HOME_RADIUS_KM
            )
            device_trackers_to_monitor = coordinator.config_entry.options.get(
                CONF_DEVICE_TRACKERS, []
            )
            device_radius_km = coordinator.config_entry.options.get(
                CONF_DEVICE_RADIUS, DEFAULT_DEVICE_RADIUS_KM
            )
            device_locations = {}
            for entity_id in device_trackers_to_monitor:
                device_state = hass.states.get(entity_id)
                if device_state and device_state.attributes.get("latitude") is not None:
                    device_locations[entity_id] = {
                        "latitude": device_state.attributes.get("latitude"),
                        "longitude": device_state.attributes.get("longitude"),
                        "name": device_state.name
                    }

            for hazard_feature in coordinator.data["features"]:
                try:
                    hazard_id = str(hazard_feature.get("id"))
                    properties = hazard_feature.get("properties", {})
                    geometry = hazard_feature.get("geometry", {})
                    
                    if not hazard_id or not properties or not geometry or geometry.get("type") != "Point":
                        _LOGGER.debug("Skipping hazard with incomplete data: %s", hazard_id if hazard_id else "Unknown ID")
                        continue

                    hazard_coords = geometry.get("coordinates")
                    if not hazard_coords or len(hazard_coords) < 2:
                        _LOGGER.debug("Skipping hazard with invalid coordinates for %s", hazard_id)
                        continue
                    
                    hazard_lat, hazard_lon = hazard_coords[1], hazard_coords[0]
                    is_near_home = False
                    if home_latitude is not None and home_longitude is not None:
                        if haversine_distance(home_latitude, home_longitude, hazard_lat, hazard_lon) <= home_radius_km:
                            is_near_home = True
                    
                    is_near_device = False
                    if not is_near_home: # Only check devices if not already near home to save computation
                        for _device_id, device_info in device_locations.items():
                            if haversine_distance(device_info["latitude"], device_info["longitude"], hazard_lat, hazard_lon) <= device_radius_km:
                                is_near_device = True
                                break

                    if is_near_home or is_near_device:
                        hazards_in_scope[hazard_id] = hazard_feature

                except Exception as e:
                    _LOGGER.error("Error processing hazard feature for scope check: %s. Hazard data: %s", e, hazard_feature, exc_info=True)

        active_hazard_ids_in_scope = set(hazards_in_scope.keys())

        # Process new and updated hazards
        for hazard_id, hazard_data in hazards_in_scope.items():
            if hazard_id not in current_tracked_ids:
                # New hazard detected in scope
                try:
                    entity = NswLiveTrafficHazardGeoLocationEntity(
                        coordinator, config_entry.entry_id, hazard_data
                    )
                    tracked_entities[hazard_id] = entity
                    new_entities_to_add_to_ha.append(entity)
                    _LOGGER.info("New nearby hazard detected: %s (%s)", hazard_id, entity.name)
                    hass.bus.async_fire(EVENT_NEW_HAZARD_NEARBY, {
                        "entry_id": config_entry.entry_id,
                        "hazard_id": hazard_id,
                        "name": entity.name,
                        "latitude": entity.latitude,
                        "longitude": entity.longitude,
                        "attributes": entity.extra_state_attributes
                    })
                except Exception as e:
                    _LOGGER.error("Error creating new geolocation entity for hazard %s: %s", hazard_id, e, exc_info=True)
            else:
                # Existing hazard, check for significant updates
                entity = tracked_entities[hazard_id]
                old_attributes = dict(entity.extra_state_attributes or {}) # Ensure it's a dict
                
                # Temporarily update entity with new data to get new attributes for comparison
                # This is a bit of a workaround; ideally, we'd parse new attributes without full entity update yet
                current_name = entity.name
                current_lat = entity.latitude
                current_lon = entity.longitude
                entity.update_hazard_data(hazard_data) # This updates internal state and _attr_extra_state_attributes
                new_attributes = dict(entity.extra_state_attributes or {})
                
                changed_significant_attrs = {}
                for key in SIGNIFICANT_ATTRIBUTE_KEYS:
                    old_val = old_attributes.get(key)
                    new_val = new_attributes.get(key)
                    if old_val != new_val:
                        changed_significant_attrs[key] = {"old": old_val, "new": new_val}
                
                if changed_significant_attrs:
                    _LOGGER.info("Significant details updated for nearby hazard: %s (%s). Changes: %s", hazard_id, entity.name, changed_significant_attrs)
                    hass.bus.async_fire(EVENT_HAZARD_DETAILS_UPDATED, {
                        "entry_id": config_entry.entry_id,
                        "hazard_id": hazard_id,
                        "name": entity.name, # Could be new name
                        "latitude": entity.latitude, # Could be new lat/lon if it changed
                        "longitude": entity.longitude,
                        "attributes": new_attributes,
                        "changes": changed_significant_attrs
                    })
                # No specific else here; entity.update_hazard_data() already called, HA will handle state write if data changed
        
        if new_entities_to_add_to_ha:
            async_add_entities(new_entities_to_add_to_ha)

        # Process cleared hazards
        cleared_hazard_ids = current_tracked_ids - active_hazard_ids_in_scope
        for hazard_id_to_remove in cleared_hazard_ids:
            entity_to_remove = tracked_entities.pop(hazard_id_to_remove)
            _LOGGER.info("Nearby hazard cleared (no longer in scope or ended): %s (%s)", hazard_id_to_remove, entity_to_remove.name)
            hass.bus.async_fire(EVENT_HAZARD_CLEARED_NEARBY, {
                "entry_id": config_entry.entry_id,
                "hazard_id": hazard_id_to_remove,
                "name": entity_to_remove.name, # Name at the time of removal
                "attributes": entity_to_remove.extra_state_attributes # Attributes at the time of removal
            })
            
            if entity_registry.async_is_registered(entity_to_remove.entity_id):
                try:
                    await entity_registry.async_remove_entity(entity_to_remove.entity_id)
                    _LOGGER.debug("Successfully removed entity %s from registry.", entity_to_remove.entity_id)
                except Exception as e: 
                    _LOGGER.error("Error removing entity %s from registry: %s", entity_to_remove.entity_id, e, exc_info=True)
            else:
                _LOGGER.debug("Entity %s was not registered, no removal from registry needed.", entity_to_remove.entity_id)

    @callback
    async def coordinator_updated():
        """Handle updated data from the coordinator."""
        _LOGGER.debug("Coordinator data updated, triggering geolocation entity update and specific event checks.")
        await update_entities()
        # General event indicating data has been processed for this entry
        hass.bus.async_fire(EVENT_HAZARDS_UPDATED, {"entry_id": config_entry.entry_id, "status": "processed"})

    config_entry.async_on_unload(
        coordinator.async_add_listener(coordinator_updated)
    )
    
    @callback
    async def options_or_location_changed_listener(*args): # Accept any args from listeners
        source_event = args[0].event_type if args and hasattr(args[0], 'event_type') else "options_update"
        _LOGGER.debug("Integration options, HASS zone, or device_tracker state change detected (%s), triggering geolocation entity update.", source_event)
        await update_entities()

    # Listener for option changes
    config_entry.async_on_unload(
        config_entry.add_update_listener(options_or_location_changed_listener)
    )
    
    # Listeners for HASS zone changes (covers home zone)
    config_entry.async_on_unload(
        hass.bus.async_listen("event_zone_added", options_or_location_changed_listener)
    )
    config_entry.async_on_unload(
        hass.bus.async_listen("event_zone_removed", options_or_location_changed_listener)
    )
    config_entry.async_on_unload(
        hass.bus.async_listen("event_zone_updated", options_or_location_changed_listener)
    )
    
    # Listeners for configured device_tracker state changes
    @callback
    def schedule_device_tracker_listeners(options: Dict[str, Any]) -> List[callable]:
        """Set up or update device tracker state change listeners based on options."""
        # Clean up old listeners first, if any were stored from a previous options setup
        # This requires storing the unsubscribe handles, e.g., on config_entry or a local dict
        # For simplicity here, we'll assume this function is called and old ones are handled by async_on_unload
        # of the returned listeners if options change causes a reload.

        unsub_listeners = []
        device_tracker_entity_ids = options.get(CONF_DEVICE_TRACKERS, [])
        if device_tracker_entity_ids:
            _LOGGER.debug("Setting up state change listeners for device_trackers: %s", device_tracker_entity_ids)
            unsub_listeners.append(
                async_track_state_change_event(
                    hass, device_tracker_entity_ids, options_or_location_changed_listener
                )
            )
        return unsub_listeners

    # Initial setup of device tracker listeners based on current options
    current_options = dict(config_entry.options)
    dt_unsub_listeners = schedule_device_tracker_listeners(current_options)
    for unsub in dt_unsub_listeners:
        config_entry.async_on_unload(unsub)

    # Ensure listeners are updated if options change (though a full reload typically happens)
    # The existing options_update_listener will trigger a reload, which will re-run async_setup_entry
    # and thus re-evaluate device trackers.

    # Initial data load
    if coordinator.last_update_success: # Process if data is already available
        _LOGGER.debug("Initial data available on setup, running update_entities.")
        await update_entities()
    else:
        _LOGGER.debug("No initial data or first refresh pending, update_entities will run on coordinator update.")


class NswLiveTrafficHazardGeoLocationEntity(CoordinatorEntity, GeolocationEvent):
    """Representation of a NSW Live Traffic hazard geolocation."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(
        self,
        coordinator: NswLiveTrafficDataUpdateCoordinator,
        config_entry_id: str,
        hazard_data: Dict[str, Any],
    ):
        """Initialize the geolocation entity."""
        super().__init__(coordinator)
        self._config_entry_id = config_entry_id
        # Initial data set, then call update_hazard_data to process it
        # This avoids duplicating logic for attribute parsing here and in update_hazard_data
        self._hazard_data: Dict[str, Any] = {}
        self._properties: Dict[str, Any] = {}
        self._geometry: Dict[str, Any] = {}
        self._hazard_id: str = ""
        self._attr_name = "Unknown Hazard" # Default before first update

        # Call update_hazard_data to parse initial data and set all attributes
        self.update_hazard_data(hazard_data) 

        # Unique ID should be based on the stable hazard ID from the data
        # self._hazard_id is set within update_hazard_data or based on it
        self._attr_unique_id = f"{config_entry_id}_{self._hazard_id}"
        
        # Entity ID: geo_location.domain_slugifiedname
        # self.entity_id is often set by HA core based on unique_id and platform
        # but can be suggested. Let's ensure name is available for slugify.
        # self.name is set by _attr_name in update_state_and_attributes which is called by update_hazard_data
        self.entity_id = f"geo_location.{DOMAIN}_{slugify(self.name if self.name else self._hazard_id)}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._config_entry_id)},
            name=self.coordinator.config_entry.title,
            manufacturer="Transport for NSW",
            model="Live Traffic Hazard",
            configuration_url="https://github.com/anon145/nsw-live-traffic-ha-custom-component",
            entry_type="service", 
        )
        # No need to call update_state_and_attributes here, it was called by update_hazard_data

    def update_hazard_data(self, new_hazard_data: Dict[str, Any]):
        """Update the internal hazard data and refresh the entity state and attributes."""
        self._hazard_data = new_hazard_data
        self._properties = self._hazard_data.get("properties", {})
        self._geometry = self._hazard_data.get("geometry", {})
        
        new_hazard_id = str(self._properties.get("id", self._hazard_data.get("id"))) # Prefer properties.id
        if not new_hazard_id:
            # Fallback for very unusual cases where ID is totally missing from properties and root
            # This should ideally not happen with the API
            temp_name_for_slug = self._properties.get("headline", "unknown_hazard_entity")
            new_hazard_id = slugify(f"missingid_{temp_name_for_slug}_{self._geometry.get('coordinates', [0,0])[0]}")
            _LOGGER.warning("Hazard data missing 'id' in properties and root. Using generated ID: %s", new_hazard_id)
        self._hazard_id = new_hazard_id

        self.update_state_and_attributes() # This sets _attr_name, _attr_latitude, etc.
        
        # If hass is available and entity is added, inform HA of state change
        if self.hass and self.entity_id and self.entity_id in self.hass.states:
            self.async_write_ha_state()

    def update_state_and_attributes(self) -> None:
        """Update state and attributes from the latest hazard data."""
        properties = self._properties
        geometry = self._geometry # Added for clarity
        
        self._attr_name = properties.get("headline", "Unknown Hazard")
        
        coordinates = geometry.get("coordinates") # Use self._geometry consistently
        if coordinates and len(coordinates) == 2:
            self._attr_latitude = coordinates[1]
            self._attr_longitude = coordinates[0]
        else:
            self._attr_latitude = None
            self._attr_longitude = None
            _LOGGER.warning("Missing or invalid coordinates for hazard ID %s: %s", self._hazard_id, coordinates)

        self._attr_source = DOMAIN 
        
        self._attr_extra_state_attributes = {
            "hazard_id": self._hazard_id,
            "created": utc_from_timestamp(properties.get("created", 0) / 1000).isoformat()
            if isinstance(properties.get("created"), (int, float)) and properties.get("created", 0) > 0
            else None,
            "last_updated": utc_from_timestamp(properties.get("lastUpdated", 0) / 1000).isoformat()
            if isinstance(properties.get("lastUpdated"), (int, float)) and properties.get("lastUpdated", 0) > 0
            else None,
            "main_category": properties.get("mainCategory"),
            "sub_category_a": properties.get("subCategoryA"),
            "sub_category_b": properties.get("subCategoryB"),
            "sub_category_c": properties.get("subCategoryC"),
            "sub_category_d": properties.get("subCategoryD"),
            "roads": [road.get("roadName") for road in properties.get("roads", []) if isinstance(road, dict) and road.get("roadName")],
            "location_qualifier": properties.get("locationQualifier"),
            "start_time": utc_from_timestamp(properties.get("start", 0) / 1000).isoformat()
            if isinstance(properties.get("start"), (int, float)) and properties.get("start", 0) > 0
            else None,
            "end_time": utc_from_timestamp(properties.get("end", 0) / 1000).isoformat()
            if isinstance(properties.get("end"), (int, float)) and properties.get("end", 0) > 0
            else None,
            "duration_minutes": properties.get("durationMinutes"),
            "period_type": properties.get("periodType"),
            "advice_a": properties.get("adviceA"),
            "advice_b": properties.get("adviceB"),
            "other_advice": properties.get("otherAdvice"),
            "web_link": get_geojson_properties_get_first_url(properties),
            "is_major": properties.get("isMajor"),
            "impact": properties.get("impact"),
            "incident_dots_display": properties.get("incidentDotsDisplay"),
            "display_order": properties.get("displayOrder"),
            "arr_status": properties.get("arrStatus"),
            "imp_status": properties.get("impStatus"),
            "ended": properties.get("ended", False),
            "is_event": properties.get("isEvent", False),
            "hazard_type_dn": HAZARD_TYPE_DISPLAY_NAME_MAP.get(str(properties.get("mainCategory", "")).lower(), str(properties.get("mainCategory")))
        }
        self._attr_extra_state_attributes = {
            k: v for k, v in self._attr_extra_state_attributes.items() if v is not None
        }

    @property
    def latitude(self) -> Optional[float]:
        """Return latitude value of the geolocation."""
        return self._attr_latitude

    @property
    def longitude(self) -> Optional[float]:
        """Return longitude value of the geolocation."""
        return self._attr_longitude

    @property
    def source(self) -> str:
        """Return source value of the geolocation."""
        return self._attr_source
        
    async def async_added_to_hass(self) -> None:
        """Handle when entity is added."""
        await super().async_added_to_hass()
        _LOGGER.debug("Geolocation entity added to HASS: %s (%s)", self.entity_id, self.name)

    async def async_will_remove_from_hass(self) -> None:
        """Handle when entity will be removed."""
        _LOGGER.debug("Geolocation entity will be removed from HASS: %s (%s)", self.entity_id, self.name)
        await super().async_will_remove_from_hass()

    # The GeolocationEvent class itself provides distance and unit_of_measurement
    # so we don't need to explicitly define them unless we want to override behavior.
    # `distance` will be calculated by HA core based on `latitude`, `longitude` and the home zone.
    # `unit_of_measurement` for distance is typically km or mi based on HA system settings. 
    # `unit_of_measurement` for distance is typically km or mi based on HA system settings. 