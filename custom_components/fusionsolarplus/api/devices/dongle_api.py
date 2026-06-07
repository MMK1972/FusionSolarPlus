"""Dongle API helpers.

This module contains all dongle-related HTTP calls and payload normalization.
The dongle device is used for system-level configuration like active power control.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlencode

_LOGGER = logging.getLogger(__name__)


# Active Power Control options mapping
POWER_SETTING_OPTIONS = {
    "No limit": 0,
    "Zero Export Limitation": 5,
    "Limited Power Grid (kW)": 6,
    "Limited Power Grid (%)": 7,
}

POWER_SETTING_REVERSE = {
    0: "No limit",
    5: "Zero Export Limitation",
    6: "Limited Power Grid (kW)",
    7: "Limited Power Grid (%)",
}

# Signal ID for Active Power Control
SIGNAL_ACTIVE_POWER_CONTROL = "230190032"

# Uudet signaalit lukuarvojen lähettämiseen (kW ja %)
SIGNAL_ACTIVE_POWER_LIMIT_KW = "230190033"
SIGNAL_ACTIVE_POWER_LIMIT_PERCENT = "230190034"


def get_dongle_id(client: Any) -> str | None:
    """Get the dongle device ID from the device list.
    
    :param client: FusionSolarClient instance
    :return: Dongle device DN or None if not found
    """
    device_ids = client.get_device_ids()
    dongle_devices = list(filter(lambda e: e["type"] == "Dongle", device_ids))
    if not dongle_devices:
        return None
    return dongle_devices[0]["deviceDn"]


def set_active_power_control(client: Any, power_setting: str) -> None:
    """Apply active power control setting.
    
    This can be useful when electricity prices are negative (sunny summer holiday)
    and you want to limit the power exported into the grid.
    
    :param client: FusionSolarClient instance
    :param power_setting: One of 'No limit', 'Zero Export Limitation', 
                          'Limited Power Grid (kW)', 'Limited Power Grid (%)'
    :raises ValueError: If power_setting is not a valid option or no dongle found
    """
    if power_setting not in POWER_SETTING_OPTIONS:
        raise ValueError(
            f"Unknown power setting: {power_setting}. "
            f"Valid options: {list(POWER_SETTING_OPTIONS.keys())}"
        )

    dongle_id = get_dongle_id(client)
    if not dongle_id:
        raise ValueError("No Dongle device found. Active power control requires a Dongle.")

    url = f"https://{client._huawei_subdomain}.fusionsolar.huawei.com/rest/pvms/web/device/v1/deviceExt/set-config-signals"
    params = {
        "dn": dongle_id,
        "changeValues": f'[{{"id":"{SIGNAL_ACTIVE_POWER_CONTROL}","value":"{POWER_SETTING_OPTIONS[power_setting]}"}}]'
    }
    data = urlencode(params)
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    r = client._session.post(url, data=data, headers=headers)
    r.raise_for_status()


def get_active_power_control(client: Any) -> str:
    """Get the current active power control setting.
    
    :param client: FusionSolarClient instance
    :return: Current power setting name, defaults to 'No limit' if unable to determine
    """
    dongle_id = get_dongle_id(client)
    if not dongle_id:
        return "No limit"

    url = f"https://{client._huawei_subdomain}.fusionsolar.huawei.com/rest/pvms/web/device/v1/deviceExt/get-config-signals"
    params = {
        "dn": dongle_id,
        "signalIds": SIGNAL_ACTIVE_POWER_CONTROL,
        "_": round(time.time() * 1000),
    }
    
    r = client._session.get(url, params=params)
    r.raise_for_status()
    
    data = r.json()

    def _extract_signals(payload):
        if isinstance(payload, dict):
            if "id" in payload and "value" in payload:
                return [payload]
            signals = []
            for value in payload.values():
                signals.extend(_extract_signals(value))
            return signals
        if isinstance(payload, list):
            signals = []
            for item in payload:
                signals.extend(_extract_signals(item))
            return signals
        return []

    def _get_signal_id(signal):
        for key in ("id", "signalId", "signal_id"):
            if isinstance(signal, dict) and key in signal:
                return signal.get(key)
        return None

    def _get_signal_value(signal):
        for key in ("value", "signalValue", "signal_value", "val"):
            if isinstance(signal, dict) and key in signal:
                return signal.get(key)
        return None

    def _get_signal_name(signal):
        for key in ("name", "signalName", "signal_name"):
            if isinstance(signal, dict) and key in signal:
                return signal.get(key)
            return None

    entries = _extract_signals(data)
    for signal in entries:
        signal_id = _get_signal_id(signal)
        signal_name = _get_signal_name(signal)
        value = _get_signal_value(signal)

        if (
            signal_id == 230190032
            or str(signal_id) == SIGNAL_ACTIVE_POWER_CONTROL
            or str(signal_id) == "21115"
            or (signal_name and signal_name.lower() == "active power control mode")
        ):
            if value is not None:
                try:
                    return POWER_SETTING_REVERSE.get(int(value), "No limit")
                except (ValueError, TypeError):
                    pass

    return "No limit"


def get_dongle_data(client: Any) -> dict:
    """Fetch dongle configuration data including active power control setting.
    
    :param client: FusionSolarClient instance
    :return: Dictionary with dongle configuration data
    """
    dongle_id = get_dongle_id(client)
    active_power_setting = get_active_power_control(client)
    
    return {
        "dongle_id": dongle_id,
        "active_power_control": active_power_setting,
        "active_power_control_options": list(POWER_SETTING_OPTIONS.keys()),
    }


def set_active_power_limit(client: Any, value: float) -> None:
    """Asettaa aktiivitehon rajan (kW tai %)."""
    dongle_id = get_dongle_id(client)
    if not dongle_id:
        raise ValueError("No Dongle device found. Cannot set limit.")

    # Tarkistetaan, mikä tila on valittuna, jotta tiedämme lähetämmekö watteja vai prosentteja
    current_mode = get_active_power_control(client)
    
    if current_mode == "Limited Power Grid (kW)":
        signal_id = SIGNAL_ACTIVE_POWER_LIMIT_KW
    elif current_mode == "Limited Power Grid (%)":
        signal_id = SIGNAL_ACTIVE_POWER_LIMIT_PERCENT
    else:
        _LOGGER.warning("Yritettiin asettaa lukuarvo, mutta valittuna on tila: %s", current_mode)
        return

    url = f"https://{client._huawei_subdomain}.fusionsolar.huawei.com/rest/pvms/web/device/v1/deviceExt/set-config-signals"
    
    # Huawei API haluaa luvun merkkijonona
    val_str = str(value)
    
    params = {
        "dn": dongle_id,
        "changeValues": f'[{{"id":"{signal_id}","value":"{val_str}"}}]'
    }
    data = urlencode(params)
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    r = client._session.post(url, data=data, headers=headers)
    r.raise_for_status()