from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

DONGLE_SIGNALS = [
    {
        "id": "active_power_control",
        "name": "Active Power Control",
        "custom_name": "Active Power Control",
        "device_class": SensorDeviceClass.ENUM,
        "unit": None,
        "options": ["No limit", "Zero Export Limitation", "Limited Power Grid (kW)", "Limited Power Grid (%)"],
    },
]