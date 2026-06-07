"""Number platform for Dongle devices."""

import logging
from typing import Dict, Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.number import NumberEntity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from ...device_handler import BaseDeviceHandler
from ...const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class DongleNumberHandler(BaseDeviceHandler):
    """Handler for dongle number entities."""

    def create_entities(self, coordinator: DataUpdateCoordinator) -> list:
        """Create number entities for the dongle."""
        client = self.hass.data[DOMAIN][self.entry.entry_id]
        
        return [
            ActivePowerControlLimit(
                coordinator,
                self.hass,
                self.device_info,
                self.device_id,
                self.device_name,
                client,
            )
        ]

class ActivePowerControlLimit(CoordinatorEntity, NumberEntity):
    """Säädin tehorajoituksen (kW tai %) asettamiseen."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        hass: HomeAssistant,
        device_info: Dict[str, Any],
        device_id: str,
        device_name: str,
        client,
    ):
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.hass = hass
        self._device_info = device_info
        self._device_id = device_id
        self._client = client
        self._attr_unique_id = f"{device_id}_active_power_limit"
        self._attr_name = f"{device_name} Active Power Limit"
        self._attr_icon = "mdi:lightning-bolt"
        
        # Määritetään säätimen rajat (esim. 0 - 100). 
        # Tämä toimii sekä prosentteina (0-100%) että kilowatteina (0-100 kW).
        self._attr_native_min_value = 0.0
        self._attr_native_max_value = 100.0
        self._attr_native_step = 0.1

    @property
    def device_info(self):
        """Return device information."""
        return self._device_info

    @property
    def native_value(self) -> float:
        """Haetaan nykyinen arvo (jos API sen palauttaa)."""
        data = self.coordinator.data or {}
        # Palauttaa nollan oletuksena, jos arvoa ei ole vielä luettu
        return float(data.get("active_power_limit", 0.0))

    async def async_set_native_value(self, value: float) -> None:
        """Lähetetään uusi arvo Huawein pilveen."""
        try:
            # Yritetään käyttää todennäköisintä funktiota dongle_api.py:stä
            if hasattr(self._client, "set_active_power_limit"):
                await self.hass.async_add_executor_job(
                    self._client.set_active_power_limit, value
                )
            elif hasattr(self._client, "active_power_control_value"):
                await self.hass.async_add_executor_job(
                    self._client.active_power_control_value, value
                )
            else:
                _LOGGER.warning("En löytänyt oikeaa funktiota arvon lähettämiseen dongle_api.py -tiedostosta.")
                
            # Päivitetään tiedot
            await self.coordinator.async_request_refresh()
            
        except Exception as e:
            _LOGGER.error("Virhe tehorajan asettamisessa: %s", e)