# custom_components/travaux_besancon/sensor.py
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TravauxCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TravauxCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TravauxSensor(coordinator, entry)])


class TravauxSensor(CoordinatorEntity[TravauxCoordinator], SensorEntity):
    """Capteur global : nombre d'arrêtés actifs sur les zones suivies.

    Attributs = liste détaillée des arrêtés (rues, type, date, lien PDF)
    exploitée par la carte Lovelace et les automatisations.
    """

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "arrêtés"
    _attr_icon = "mdi:traffic-cone"
    _attr_name = "Travaux Besançon"

    def __init__(self, coordinator: TravauxCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_arretes_actifs"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Travaux Besançon",
            manufacturer="Ville de Besançon",
            model="Arrêtés temporaires de voirie",
        )

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return len(self.coordinator.data["suivis"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if not data:
            return {}
        arretes = [data["arretes"][aid] for aid in data["suivis"]]
        return {
            "arretes": arretes,
            "zones": data["zones"],
            "jours_expiration": self.coordinator.jours_expiration,
            # Permet à la carte Lovelace de filtrer les entités de cette intégration
            "integration": DOMAIN,
        }
