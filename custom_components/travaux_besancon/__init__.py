# custom_components/travaux_besancon/__init__.py
from __future__ import annotations

import logging
import os

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import TravauxCoordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.EVENT,
    Platform.GEO_LOCATION,
]

_CARD_URL  = "/travaux_besancon_card"
_CARD_FILE = "travaux-besancon-card.js"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Enregistre le fichier JS de la carte Lovelace."""
    card_dir = hass.config.path("custom_components", "travaux_besancon", "lovelace")

    if not await hass.async_add_executor_job(os.path.isdir, card_dir):
        _LOGGER.warning(
            "Travaux Besançon: dossier lovelace/ introuvable — la carte ne sera pas disponible."
        )
        return True

    try:
        await hass.http.async_register_static_paths([
            StaticPathConfig(_CARD_URL, card_dir, cache_headers=True)
        ])
        add_extra_js_url(hass, f"{_CARD_URL}/{_CARD_FILE}")
        _LOGGER.debug("Travaux Besançon: carte servie depuis %s", card_dir)
    except Exception:
        _LOGGER.exception(
            "Travaux Besançon: erreur lors de l'enregistrement de la carte Lovelace"
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    coordinator = TravauxCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Un changement d'options (zones, fenêtre d'expiration) recharge l'entrée
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator: TravauxCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    return unloaded
