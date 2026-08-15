# custom_components/travaux_besancon/event.py
from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TravauxCoordinator

EVENT_TYPE_NOUVEL_ARRETE = "nouvel_arrete"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TravauxCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TravauxEvent(coordinator, entry)])


class TravauxEvent(CoordinatorEntity[TravauxCoordinator], EventEntity):
    """Entité événement : se déclenche pour chaque nouvel arrêté sur les zones suivies.

    Le même événement est aussi publié sur le bus HA
    (travaux_besancon_nouvel_arrete) pour les automatisations classiques.
    """

    _attr_event_types = [EVENT_TYPE_NOUVEL_ARRETE]
    # Slugifié en event.travaux_besancon_nouvel_arrete (cf. README)
    _attr_name = "Travaux Besançon nouvel arrêté"
    _attr_icon = "mdi:bell-alert"

    def __init__(self, coordinator: TravauxCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_nouvel_arrete"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data or {}
        for aid in data.get("nouveaux", []):
            self._trigger_event(EVENT_TYPE_NOUVEL_ARRETE, data["arretes"][aid])
        super()._handle_coordinator_update()
