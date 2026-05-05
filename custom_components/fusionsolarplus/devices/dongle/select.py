"""Select platform for Dongle devices."""

import asyncio
import logging
from typing import Dict, Any, List

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from ...device_handler import BaseDeviceHandler
from ...const import DOMAIN
from ...api.devices.dongle_api import POWER_SETTING_OPTIONS

_LOGGER = logging.getLogger(__name__)

# Active Power Control options from dongle_api
ACTIVE_POWER_OPTIONS = list(POWER_SETTING_OPTIONS.keys())


class DongleSelectHandler(BaseDeviceHandler):
    """Handler for dongle select entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device_info: Dict[str, Any],
    ):
        super().__init__(hass, entry, device_info)

    def create_entities(self, coordinator: DataUpdateCoordinator) -> list:
        """Create select entities for the dongle."""
        client = self.hass.data[DOMAIN][self.entry.entry_id]

        return [
            ActivePowerControlSelect(
                coordinator,
                self.hass,
                self.device_info,
                self.device_id,
                self.device_name,
                client,
            )
        ]


class ActivePowerControlSelect(CoordinatorEntity, SelectEntity):
    """Representation of an Active Power Control Select entity."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        hass: HomeAssistant,
        device_info: Dict[str, Any],
        device_id: str,
        device_name: str,
        client,
    ):
        """Initialize the select entity."""
        super().__init__(coordinator)
        self.hass = hass
        self._device_info = device_info
        self._device_id = device_id
        self._device_name = device_name
        self._client = client
        self._current_option = "No limit"
        self._is_updating = False
        self._attr_unique_id = f"{device_id}_active_power_control"
        self._attr_name = f"{device_name} Active Power Control"
        self._attr_options = ACTIVE_POWER_OPTIONS
        self._attr_icon = "mdi:transmission-tower"
        self._attr_translation_key = "active_power_control"

    @property
    def device_info(self):
        """Return device information."""
        return self._device_info

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return not self._is_updating and self.coordinator.last_update_success

    @property
    def current_option(self) -> str:
        """Return the current selected option."""
        return self._current_option

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        await super().async_added_to_hass()
        # Fetch the initial state
        await self._async_update_current_option()

    async def _async_update_current_option(self) -> None:
        """Fetch the current active power control setting from the API."""
        try:
            current = await self.hass.async_add_executor_job(
                self._client.get_active_power_control_setting
            )
            if current and current in ACTIVE_POWER_OPTIONS:
                self._current_option = current
                self.async_write_ha_state()
        except Exception:
            pass

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option not in ACTIVE_POWER_OPTIONS:
            _LOGGER.error("Invalid active power control option: %s", option)
            return

        if self._is_updating:
            _LOGGER.warning(
                "Active power control is already being updated. Please wait."
            )
            return

        self._is_updating = True
        previous_option = self._current_option
        self._current_option = option  # Optimistic update
        self.async_write_ha_state()

        try:
            await self.hass.async_add_executor_job(
                self._client.active_power_control, option
            )
            # Wait longer for Huawei API to process and propagate the change
            await asyncio.sleep(10)
            # Refresh coordinator to update all related sensors
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(
                "Failed to set active power control to %s: %s",
                option,
                e,
            )
            # Revert to previous option on failure
            self._current_option = previous_option
        finally:
            # Short cooldown to prevent rapid changes
            await asyncio.sleep(5)
            self._is_updating = False