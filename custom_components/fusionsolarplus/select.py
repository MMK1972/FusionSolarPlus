"""Select platform for FusionSolar Plus."""

import logging
from typing import Dict, Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .device_handler import BaseDeviceHandler

_LOGGER = logging.getLogger(__name__)

# Vikasietoiset tuonnit: ladataan vain ne tiedostot, jotka oikeasti ovat kansiossa
try:
    from .devices.inverter.select import InverterSelectHandler
except ImportError:
    InverterSelectHandler = None

try:
    from .devices.dongle.select import DongleSelectHandler
except ImportError:
    DongleSelectHandler = None

try:
    from .devices.charger.select import ChargerSelectHandler
except ImportError:
    ChargerSelectHandler = None

try:
    from .devices.emma.select import EMMASelectHandler
except ImportError:
    EMMASelectHandler = None


class SelectHandlerFactory:
    """Create appropriate select handlers."""

    @staticmethod
    def create_handler(
        hass: HomeAssistant, entry: ConfigEntry, device_info: Dict[str, Any]
    ) -> BaseDeviceHandler | None:
        device_type = device_info.get("model") or entry.data.get("device_type")
        installer = entry.options.get("installer", entry.data.get("installer", False))

        if device_type == "Inverter" and installer and InverterSelectHandler:
            return InverterSelectHandler(hass, entry, device_info)
        elif device_type == "Dongle" and DongleSelectHandler:
            return DongleSelectHandler(hass, entry, device_info)
        elif (device_type == "Charger" or device_type == "Charging Pile") and ChargerSelectHandler:
            return ChargerSelectHandler(hass, entry, device_info)
        elif device_type in ("SmartAssistant", "EMMA") and EMMASelectHandler:
            return EMMASelectHandler(hass, entry, device_info)
            
        return None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up select platform."""
    device_name = entry.data.get("device_name")
    device_info = hass.data[DOMAIN].get(f"{entry.entry_id}_device_info")

    if not device_info:
        _LOGGER.debug(
            "Device info not found for device %s. Skipping select setup.", device_name
        )
        return

    try:
        handler = SelectHandlerFactory.create_handler(hass, entry, device_info)

        if handler is None:
            return

        coordinator = hass.data[DOMAIN].get(f"{entry.entry_id}_coordinator")
        if not coordinator:
            _LOGGER.debug(
                "No coordinator found for device %s. Skipping select setup.", device_name
            )
            return

        entities = handler.create_entities(coordinator)

        _LOGGER.info(
            "Adding %d select entities for device %s", len(entities), device_name
        )
        async_add_entities(entities)

    except Exception as e:
        _LOGGER.error("Failed to set up select entities for device %s: %s", device_name, e)