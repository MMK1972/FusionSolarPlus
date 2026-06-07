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
from homeassistant.components.switch import SwitchEntity, ENTITY_ID_FORMAT
from homeassistant.helpers.entity import generate_entity_id

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


# ── Handler ───────────────────────────────────────────────────────────────────

class ChargerSwitchHandler(BaseDeviceHandler):
    """Handler that reads charger data and creates Switch entities."""

    async def _async_get_data(self) -> Dict[str, Any]:
        """Haetaan sekä reaaliaikainen data että asetukset (config)."""
        async def fetch(client):
            # 1. Haetaan laturin reaaliaikainen tila
            charger_data = await self.hass.async_add_executor_job(
                client.get_charger_data, self.device_id
            )
            
            # 2. Haetaan laturin asetukset (Working Mode, Max Power)
            charger_config = await self.hass.async_add_executor_job(
                client.get_charger_config, self.device_id
            )
            
            # 3. Luodaan yhteinen arvo-kartta (value_map)
            value_map = {}
            
            # Yhdistetään reaaliaikaiset data-signaalit value_mapiin
            if "value_map" in charger_data:
                value_map.update(charger_data["value_map"])
                
            # Yhdistetään asetussignaalit value_mapiin
            if "data" in charger_config:
                # config palauttaa dnId:t avaimina ja signaalit listana
                for dn_id, signals in charger_config["data"].items():
                    for signal in signals:
                        if "id" in signal and "value" in signal:
                            # Käytetään tuplea (None, signal_id) varmistamaan yhteensopivuus
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


# ── Entity ────────────────────────────────────────────────────────────────────

class FusionSolarChargerControlSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to start/stop EV charging.

    State is derived from Working Status (signal 10004) on the charging pile child.
    Write uses the homemgr charge-control endpoint on port 32800.
    """

    def __init__(self, coordinator, device_info):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._optimistic_state = None  # None = use API, True/False = pending

        device_id = list(device_info["identifiers"])[0][1]
        self._attr_unique_id = f"{device_id}_charge_control"
        self._attr_name      = "Charge Control"
        self._attr