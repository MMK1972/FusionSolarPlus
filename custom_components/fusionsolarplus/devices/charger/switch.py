"""Switch platform for Charger devices."""

import logging
from typing import Dict, Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.components.switch import SwitchEntity

from ...device_handler import BaseDeviceHandler
from ...const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Signal id for Working Status on the charging pile child
SIGNAL_ID_WORKING_STATUS = 10004

# Working Status values that mean charging is active
CHARGING_ACTIVE_STATES = {
    "3",   # Charging
    "8",   # Starting Charging
    "10",  # PV Power Waiting
    "11",  # PV Power Charging
}

class ChargerSwitchHandler(BaseDeviceHandler):
    """Handler that reads charger data and creates Switch entities."""

    async def _async_get_data(self) -> Dict[str, Any]:
        """Haetaan sekä reaaliaikainen data että asetukset (config)."""
        async def fetch(client):
            charger_data = await self.hass.async_add_executor_job(
                client.get_charger_data, self.device_id
            )
            
            charger_config = await self.hass.async_add_executor_job(
                client.get_charger_config, self.device_id
            )
            
            value_map = {}
            if "value_map" in charger_data:
                value_map.update(charger_data["value_map"])
                
            if "data" in charger_config:
                for dn_id, signals in charger_config["data"].items():
                    for signal in signals:
                        if "id" in signal and "value" in signal:
                            value_map[(None, int(signal["id"]))] = signal["value"]

            return {
                "raw_data": charger_data.get("raw_data", {}),
                "config_data": charger_config,
                "value_map": value_map
            }
            
        return await self._get_client_and_retry(fetch)

    def create_entities(self, coordinator: DataUpdateCoordinator) -> list:
        return [
            FusionSolarChargerControlSwitch(
                coordinator=coordinator,
                device_info=self.device_info,
            )
        ]

class FusionSolarChargerControlSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to start/stop EV charging."""

    def __init__(self, coordinator, device_info):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._optimistic_state = None

        device_id = list(device_info["identifiers"])[0][1]
        self._attr_unique_id = f"{device_id}_charge_control"
        self._attr_name = "Charge Control"
        self._attr_icon = "mdi:ev-station"

    @property
    def is_on(self) -> bool:
        """Tarkistaa, onko lataus käynnissä."""
        if self._optimistic_state is not None:
            return self._optimistic_state
            
        value_map = self.coordinator.data.get("value_map", {})
        status = value_map.get((None, SIGNAL_ID_WORKING_STATUS))
        return str(status) in CHARGING_ACTIVE_STATES

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Käynnistää latauksen."""
        self._optimistic_state = True
        self.async_write_ha_state()
        
        try:
            client = self.coordinator.hass.data[DOMAIN][self.coordinator.config_entry.entry_id]
            device_id = list(self._attr_device_info["identifiers"])[0][1]
            
            await self.coordinator.hass.async_add_executor_job(
                client.start_charge, device_id
            )
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to start charging: %s", err)
        finally:
            self._optimistic_state = None
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Pysäyttää latauksen."""
        self._optimistic_state = False
        self.async_write_ha_state()
        
        try:
            client = self.coordinator.hass.data[DOMAIN][self.coordinator.config_entry.entry_id]
            device_id = list(self._attr_device_info["identifiers"])[0][1]
            
            await self.coordinator.hass.async_add_executor_job(
                client.stop_charge, device_id
            )
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to stop charging: %s", err)
        finally:
            self._optimistic_state = None
            self.async_write_ha_state()