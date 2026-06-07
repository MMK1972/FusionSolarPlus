"""Number platform for FusionSolar Plus."""

import logging
from typing import Dict, Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .device_handler import BaseDeviceHandler

_LOGGER = logging.getLogger(__name__)

# Vikasietoiset tuonnit
try:
    from .devices.charger.number import ChargerNumberHandler
except ImportError:
    ChargerNumberHandler = None

try:
    from .devices.dongle.number import DongleNumberHandler
except ImportError:
    DongleNumberHandler = None

class NumberHandlerFactory:
    """Create appropriate number handlers."""

    @staticmethod
    def create_handler(
        hass: HomeAssistant, entry: ConfigEntry, device_info: Dict[str, Any]
    ) -> BaseDeviceHandler | None:
        device_type = device_info.get("model") or entry.data.get("device_type")
        
        # Laturin säätimet
        if (device_type == "Charger" or device_type == "Charging Pile") and ChargerNumberHandler:
            return ChargerNumberHandler(hass, entry, device_info)
            
        # Donglen säätimet (UUSI!)
        elif device_type == "Dongle" and DongleNumberHandler:
            return DongleNumberHandler(hass, entry, device_info)
            
        return None

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up number platform."""
    device_name = entry.data.get("device_name")
    device_info = hass.data[DOMAIN].get(f"{entry.entry_id}_device_info")

    if not device_info:
        return

    try:
        handler = NumberHandlerFactory.create_handler(hass, entry, device_info)

        if handler is None:
            return

        coordinator = hass.data[DOMAIN].get(f"{entry.entry_id}_coordinator")
        if not coordinator:
            return

        entities = handler.create_entities(coordinator)
        async_add_entities(entities)

    except Exception as e:
        _LOGGER.error("Failed to set up numbers for device %s: %s", device_name, e)