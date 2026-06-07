"""Select platform for Charger devices."""

import logging
from typing import Dict, Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.components.select import SelectEntity, ENTITY_ID_FORMAT
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.restore_state import RestoreEntity

from ...device_handler import BaseDeviceHandler
from ...const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SIGNAL_ID_WORKING_MODE = 20002

WORKING_MODE_OPTIONS = {
    "0": "Normal charge",
    "1": "PV Power Preferred",
}
WORKING_MODE_REVERSE = {v: k for k, v in WORKING_MODE_OPTIONS.items()}


# ── Handler ───────────────────────────────────────────────────────────────────

class ChargerSelectHandler(BaseDeviceHandler):
    """Handler that creates Select entities for the charger using shared coordinator."""

    def create_entities(self, coordinator: DataUpdateCoordinator) -> list:
        # We don't fetch data here anymore, we use the shared coordinator
        return [
            FusionSolarChargerWorkingModeSelect(
                coordinator=coordinator,
                device_info=self.device_info,
            )
        ]


# ── Entity ────────────────────────────────────────────────────────────────────

class FusionSolarChargerWorkingModeSelect(CoordinatorEntity, SelectEntity, RestoreEntity):
    """Selector for Working Mode (signal 20002)."""

    def __init__(self, coordinator, device_info):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._current_key      = "0"
        self._pending_key      = None

        device_id = list(device_info["identifiers"])[0][1]
        self._attr_unique_id = f"{device_id}_working_mode"
        self._attr_name      = "Working Mode"
        self._attr_icon      = "mdi:solar-power"
        self._attr_options   = list(WORKING_MODE_OPTIONS.values())

        self.entity_id = generate_entity_id(
            ENTITY_ID_FORMAT,
            f"fsp_{device_id}_working_mode",
            hass=coordinator.hass,
        )

    @property
    def current_option(self) -> str | None:
        """Read current working mode from the coordinator's value_map."""
        data = self.coordinator.data
        if not data:
            if self._pending_key is not None:
                return WORKING_MODE_OPTIONS.get(self._pending_key)
            return WORKING_MODE_OPTIONS.get(self._current_key)

        # Read from the shared value_map
        value_map = data.get("value_map", {})
        for key, val in value_map.items():
            if isinstance(key, tuple) and key[1] == SIGNAL_ID_WORKING_MODE:
                try:
                    api_key = str(int(float(val)))
                except (TypeError, ValueError):
                    api_key = str(val)

                self._current_key = api_key
                
                # Clear pending key if the API matches what we set
                if self._pending_key is not None and api_key == self._pending_key:
                    self._pending_key = None
                    
                if self._pending_key is not None:
                    return WORKING_MODE_OPTIONS.get(self._pending_key)
                    
                return WORKING_MODE_OPTIONS.get(api_key, WORKING_MODE_OPTIONS["0"])

        if self._pending_key is not None:
            return WORKING_MODE_OPTIONS.get(self._pending_key)
        return WORKING_MODE_OPTIONS.get(self._current_key)

    async def async_select_option(self, option: str) -> None:
        mode_key = WORKING_MODE_REVERSE.get(option)
        if mode_key is None:
            _LOGGER.error("Unknown working mode: %s", option)
            return
            
        device_dn = list(self._attr_device_info["identifiers"])[0][1]
        _LOGGER.debug("Setting working mode %s → %s (%s)", device_dn, option, mode_key)
        
        self._pending_key = mode_key
        self.async_write_ha_state()
        
        client = self.hass.data[DOMAIN][self.coordinator.config_entry.entry_id]
        
        try:
            await self.hass.async_add_executor_job(
                client.set_charger_working_mode, device_dn, mode_key
            )
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Setting Working Mode %s failed: %s", option, err)
            self._pending_key = None
            self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state in self._attr_options:
            self._current_key = WORKING_MODE_REVERSE.get(last_state.state, "0")


# ── Platform setup ────────────────────────────────────────────────────────────

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up select platform for Charger devices."""
    device_name = entry.data.get("device_name")
    device_info = hass.data[DOMAIN].get(f"{entry.entry_id}_device_info")

    if not device_info:
        _LOGGER.debug("Device info not found for %s. Skipping select setup.", device_name)
        return

    try:
        handler = ChargerSelectHandler(hass, entry, device_info)
        # Fetch the shared coordinator instead of creating a new one
        coordinator = hass.data[DOMAIN].get(f"{entry.entry_id}_coordinator")
        if coordinator is None:
            _LOGGER.debug("No coordinator for %s. Skipping select setup.", device_name)
            return
            
        entities = handler.create_entities(coordinator)
        _LOGGER.info("Adding %d select entities for device %s", len(entities), device_name)
        async_add_entities(entities)
    except Exception as e:
        _LOGGER.error("Failed to set up select entities for device %s: %s", device_name, e)