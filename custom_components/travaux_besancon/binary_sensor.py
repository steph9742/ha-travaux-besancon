# custom_components/travaux_besancon/binary_sensor.py
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    # Les zones sont figées à la mise en place : un changement d'options
    # recharge l'entrée et donc recrée les entités.
    async_add_entities(
        TravauxZoneBinarySensor(coordinator, entry, zone_id, zone)
        for zone_id, zone in coordinator.zones().items()
    )


class TravauxZoneBinarySensor(CoordinatorEntity[TravauxCoordinator], BinarySensorEntity):
    """« Travaux dans ma zone » : on si au moins un arrêté actif concerne la zone."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: TravauxCoordinator,
        entry: ConfigEntry,
        zone_id: str,
        zone: dict[str, str],
    ) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{zone_id}"
        self._attr_name = f"Travaux {zone['nom'].title()}"
        self._attr_icon = (
            "mdi:home-city" if zone["type"] == "ville"
            else "mdi:map" if zone["type"] == "quartier"
            else "mdi:road-variant"
        )
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    def _ids_zone(self) -> list[str]:
        data = self.coordinator.data
        if not data:
            return []
        return data["par_zone"].get(self._zone_id, [])

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return len(self._ids_zone()) > 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if not data:
            return {}
        return {
            "nb_arretes": len(self._ids_zone()),
            "arretes": [data["arretes"][aid] for aid in self._ids_zone()],
            "integration": DOMAIN,
        }
