# custom_components/travaux_besancon/geo_location.py
"""Marqueurs de travaux sur la carte Home Assistant.

Une entité geo_location par couple (arrêté, rue géocodée) : la carte map
native les affiche via `geo_location_sources: [travaux_besancon]`, et un clic
sur un marqueur ouvre la fiche avec le résumé (dates, motif, horaires,
restrictions) extrait du PDF de l'arrêté.

Les entités apparaissent et disparaissent au rythme des arrêtés actifs.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.location import distance

from .const import DOMAIN
from .coordinator import TravauxCoordinator

TYPE_LABELS = {
    "circulation": "Circulation",
    "stationnement": "Stationnement",
    "circulation_stationnement": "Circulation et stationnement",
    "autre": "Voirie",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TravauxCoordinator = hass.data[DOMAIN][entry.entry_id]
    presentes: dict[tuple[str, str], TravauxGeolocationEvent] = {}

    @callback
    def _synchroniser() -> None:
        data = coordinator.data or {}
        cibles: dict[tuple[str, str], list[float]] = {}
        for aid in data.get("suivis", []):
            arrete = data["arretes"][aid]
            for rue, coords in (arrete.get("coordonnees") or {}).items():
                cibles[(aid, rue)] = coords

        for cle in [c for c in presentes if c not in cibles]:
            presentes.pop(cle).demander_suppression()

        nouvelles = [
            TravauxGeolocationEvent(coordinator, aid, rue, coords)
            for (aid, rue), coords in cibles.items()
            if (aid, rue) not in presentes
        ]
        for entite in nouvelles:
            presentes[(entite.arrete_id, entite.rue)] = entite
        if nouvelles:
            async_add_entities(nouvelles)

    _synchroniser()
    entry.async_on_unload(coordinator.async_add_listener(_synchroniser))


class TravauxGeolocationEvent(CoordinatorEntity[TravauxCoordinator], GeolocationEvent):
    """Un marqueur de travaux : un arrêté sur une rue géocodée."""

    _attr_source = DOMAIN
    _attr_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_icon = "mdi:traffic-cone"

    def __init__(
        self,
        coordinator: TravauxCoordinator,
        arrete_id: str,
        rue: str,
        coords: list[float],
    ) -> None:
        super().__init__(coordinator)
        self.arrete_id = arrete_id
        self.rue = rue
        self._attr_latitude = float(coords[0])
        self._attr_longitude = float(coords[1])
        # Pas d'unique_id : comme les intégrations geo_location du core, les
        # marqueurs sont éphémères et ne doivent pas remplir le registre.
        self._attr_name = f"Travaux {rue.title()}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # État = distance (km) entre le domicile et le chantier
        maison = (self.hass.config.latitude, self.hass.config.longitude)
        metres = distance(
            maison[0], maison[1], self._attr_latitude, self._attr_longitude
        )
        if metres is not None:
            self._attr_distance = round(metres / 1000, 2)

    def demander_suppression(self) -> None:
        """L'arrêté n'est plus actif : retire le marqueur de la carte."""
        if self.hass:
            self.hass.async_create_task(self.async_remove(force_remove=True))

    def _arrete(self) -> dict[str, Any] | None:
        data = self.coordinator.data or {}
        return data.get("arretes", {}).get(self.arrete_id)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._arrete() is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        arrete = self._arrete()
        if not arrete:
            return {}
        resume = arrete.get("resume") or {}
        attrs: dict[str, Any] = {
            "arrete": arrete["id"],
            "titre": arrete["titre"],
            "type": TYPE_LABELS.get(arrete["type"], arrete["type"]),
            "rue": self.rue.title(),
            "quartiers": [q.title() for q in arrete["quartiers"]],
            "date_publication": arrete["date_publication"],
            "url_pdf": arrete["url_pdf"],
            "integration": DOMAIN,
        }
        if resume.get("motif"):
            attrs["motif"] = resume["motif"].capitalize()
        if resume.get("date_debut"):
            attrs["du"] = resume["date_debut"]
        if resume.get("date_fin"):
            attrs["au"] = resume["date_fin"]
        if resume.get("horaires"):
            attrs["horaires"] = ", ".join(resume["horaires"])
        else:
            attrs["horaires"] = "toute la journée"
        if resume.get("restrictions"):
            attrs["restrictions"] = ", ".join(resume["restrictions"])
        if resume.get("demandeur"):
            attrs["demandeur"] = resume["demandeur"].title()
        return attrs
