# NSW Live Traffic Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/hacs/integration) <!-- If/when ready for HACS Default -->

Provides live traffic hazard information from Transport for NSW (TfNSW) Open Data into Home Assistant.

This integration fetches data on traffic incidents, roadworks, fires, floods, and other hazards, making them available as sensors and geolocation entities.

## Features

*   **Real-time Hazard Data:** Fetches the latest hazard information from the TfNSW Live Traffic Hazards API.
*   **Configurable Hazard Types:** Choose which types of hazards you want to monitor (e.g., Accidents, Roadworks, Fires).
*   **Nearby Hazard Count Sensors:** Creates individual sensors showing the count of nearby hazards for each selected hazard type.
*   **Geolocation Entities:** Displays individual hazards as geolocation entities on the map, filtered by proximity to your Home Assistant's home location and/or specified device trackers.
*   **Configurable Radii:** Define detection radii (in km) around your home location and selected device trackers.
*   **Customizable Update Interval:** Set how frequently the integration should fetch new data (minimum 1 minute).
*   **Event Notifications (for automations):
    *   `nsw_live_traffic_new_hazard_nearby`: Fired when a new hazard is detected within a monitored zone.
    *   `nsw_live_traffic_hazard_cleared_nearby`: Fired when a previously detected nearby hazard is cleared or moves out of monitored zones.
    *   `nsw_live_traffic_hazard_details_updated`: Fired when significant details of an existing nearby hazard are updated.
*   **Rich Hazard Attributes:** Both sensors and geolocation entities expose detailed attributes for each hazard, including:
    *   Headline, main category, sub-categories
    *   Creation and last updated timestamps
    *   Affected roads, location qualifier
    *   Start and end times, duration
    *   Advice and other textual information
    *   Web link to the official TfNSW hazard page
    *   Impact, status, and whether it's a major incident or event.

## Prerequisites

1.  **API Key:** You need an API key for the Transport for NSW Open Data portal. You can register for one at the [TfNSW Open Data Hub](https://opendata.transport.nsw.gov.au/). Make sure to subscribe to the "Live Traffic Hazards API".
2.  **Home Assistant:** Version 2023.x.x or newer (update as appropriate).

## Installation

### Manual Installation

1.  Copy the `nsw_live_traffic` folder from this repository into your Home Assistant `custom_components` folder.
    *   The `custom_components` folder is usually located in your main Home Assistant configuration directory. If it doesn't exist, create it.
    *   The final path should look like: `<config_directory>/custom_components/nsw_live_traffic/`.
2.  Restart Home Assistant.

### HACS Installation (Recommended - when available)

*Currently, this integration is not in the default HACS store. The following are placeholder instructions for when it might be added.* 

1.  Ensure you have [HACS (Home Assistant Community Store)](https://hacs.xyz/) installed.
2.  Open HACS in Home Assistant.
3.  Go to "Integrations".
4.  *(If not in default store yet)* You might need to add this repository as a custom repository in HACS settings.
5.  Search for "NSW Live Traffic" and install it.
6.  Restart Home Assistant.

## Configuration

After restarting Home Assistant, the NSW Live Traffic integration can be configured via the UI:

1.  Go to **Settings > Devices & Services**.
2.  Click the **+ ADD INTEGRATION** button in the bottom right corner.
3.  Search for "NSW Live Traffic" and select it.
4.  **API Key:** Enter your TfNSW Open Data API key.
    *   The integration will validate the API key. If validation fails, an error message will be displayed.
5.  If the API key is valid, the integration will be added, and you will be taken to the options flow.

### Options

You can configure the following options after the initial setup, or by clicking "Configure" on the integration card in Devices & Services:

*   **Hazard Types to Monitor:** Select one or more hazard types you are interested in (e.g., Accident, Roadwork, Fire). Sensors will be created for each selected type.
*   **Home Zone Radius (km):** Define the radius around your Home Assistant home location (zone.home) to monitor for hazards. Geolocation entities will be created for hazards within this radius.
*   **Device Trackers to Monitor:** Select one or more device tracker entities. Hazards near these devices will also be shown as geolocation entities.
*   **Device Tracker Radius (km):** Define the radius around the selected device trackers to monitor for hazards.
*   **Update Interval (minutes):** How often to fetch new data from the API. Minimum is 1 minute. Frequent updates can increase the load on the TfNSW API; please be considerate.

## Entities Provided

### Sensors

For each hazard type selected in the options, a sensor will be created with the following naming convention:
`sensor.nsw_live_traffic_nearby_<hazard_type>_hazards` (e.g., `sensor.nsw_live_traffic_nearby_accidents_hazards`).

*   **State:** The number of unique nearby hazards of that type currently active within any monitored zone (home or device tracker radii).
*   **Attributes:**
    *   `attribution`: Data source attribution.
    *   `last_updated_list`: ISO 8601 timestamp of the most recent `lastUpdated` field among the hazards in the `nearby_hazards_list`.
    *   `nearby_hazards_list`: A list of all unique nearby hazards of this specific type, each with detailed information (hazard_id, headline, main_category, last_updated, distance_km, zone_type, zone_name, latitude, longitude, web_link, other_advice).

### Geolocation Entities

Individual geolocation entities are created for each hazard that falls within your defined home radius or any of the defined device tracker radii.

*   **Entity ID:** `geo_location.nsw_live_traffic_<slugified_hazard_headline>`
*   **State:** The hazard headline.
*   **Map Display:** These entities will appear on your Home Assistant map.
*   **Attributes:**
    *   `latitude`: Latitude of the hazard.
    *   `longitude`: Longitude of the hazard.
    *   `source`: `nsw_live_traffic`.
    *   `attribution`: Data source attribution.
    *   A comprehensive list of other attributes directly from the API, such as `hazard_id`, `created`, `last_updated`, `main_category`, `roads`, `advice_a`, `other_advice`, `web_link`, `is_major`, `ended`, etc. (see `HAZARD_TYPE_DISPLAY_NAME_MAP` in `const.py` and API documentation for more details on available fields).

## Events for Automation

The integration fires the following events on the Home Assistant event bus, which you can use to trigger automations:

*   **`nsw_live_traffic_new_hazard_nearby`**
    *   Fired when a new hazard is detected within one of your monitored zones.
    *   **Event Data:**
        *   `entry_id`: Config entry ID for the integration instance.
        *   `hazard_id`: Unique ID of the hazard.
        *   `name`: Headline/name of the hazard.
        *   `latitude`: Latitude of the hazard.
        *   `longitude`: Longitude of the hazard.
        *   `attributes`: A dictionary of the hazard's attributes (similar to geolocation entity attributes).
*   **`nsw_live_traffic_hazard_cleared_nearby`**
    *   Fired when a previously detected nearby hazard is no longer active or no longer in a monitored zone.
    *   **Event Data:**
        *   `entry_id`: Config entry ID.
        *   `hazard_id`: Unique ID of the hazard.
        *   `name`: Name/headline of the hazard at the time of clearing.
        *   `attributes`: Attributes of the hazard at the time of clearing.
*   **`nsw_live_traffic_hazard_details_updated`**
    *   Fired when significant details of an existing nearby hazard are updated.
    *   **Event Data:**
        *   `entry_id`: Config entry ID.
        *   `hazard_id`: Unique ID of the hazard.
        *   `name`: Current name/headline of the hazard.
        *   `latitude`: Current latitude.
        *   `longitude`: Current longitude.
        *   `attributes`: Current full dictionary of attributes.
        *   `changes`: A dictionary detailing which significant attributes changed, with their `old` and `new` values (e.g., `{"ended": {"old": false, "new": true}}`).

### Example Automation (YAML)

```yaml
automation:
  - alias: "Notify on New Major Traffic Accident Nearby"
    trigger:
      - platform: event
        event_type: nsw_live_traffic_new_hazard_nearby
    condition:
      - condition: template
        value_template: "{{ trigger.event.data.attributes.main_category == 'accident' }}"
      - condition: template
        value_template: "{{ trigger.event.data.attributes.is_major == True }}"
    action:
      - service: notify.mobile_app_my_phone # Replace with your notification service
        data:
          title: "New Major Accident Nearby!"
          message: "{{ trigger.event.data.name }} - {{ trigger.event.data.attributes.other_advice }}"
```

## Troubleshooting

*   **API Key Issues:** Ensure your API key is correct, active, and subscribed to the "Live Traffic Hazards API" in the TfNSW Open Data portal. Errors like "Invalid API Key" or "Authentication Failed" usually point to this.
*   **No Data/Entities:**
    *   Check Home Assistant logs (`config/home-assistant.log`) for errors related to `nsw_live_traffic`.
    *   Verify your configured radii and selected hazard types. There might be no active hazards matching your criteria in your area.
    *   Ensure the TfNSW API service is operational.
*   **Rate Limiting:** The TfNSW API may have rate limits. While the default update interval is conservative, very frequent updates (e.g., every 1 minute for many users) could potentially lead to issues. The integration currently does not implement specific rate limit handling beyond request timeouts.

## Contributing

Contributions are welcome! Please feel free to open an issue or submit a pull request.

## Disclaimer

This integration uses data from Transport for NSW. The developer of this integration is not responsible for the accuracy or timeliness of the data provided by the API.
Always confirm critical travel information through official TfNSW channels.

---
*This is a community-developed integration and is not officially affiliated with Transport for NSW.* 