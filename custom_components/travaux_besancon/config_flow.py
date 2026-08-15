# custom_components/travaux_besancon/config_flow.py
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_JOURS_EXPIRATION,
    CONF_QUARTIERS,
    CONF_RUES,
    CONF_TOUTE_LA_VILLE,
    DEFAUT_JOURS_EXPIRATION,
    DOMAIN,
    MAX_JOURS_EXPIRATION,
    MIN_JOURS_EXPIRATION,
)
from .referentiel import Referentiel, charger_embarque

_LOGGER = logging.getLogger(__name__)


def _schema(referentiel: Referentiel, defauts: dict[str, Any]) -> vol.Schema:
    """Formulaire commun au config flow et à l'options flow."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_TOUTE_LA_VILLE,
                default=defauts.get(CONF_TOUTE_LA_VILLE, False),
            ): BooleanSelector(),
            vol.Optional(
                CONF_QUARTIERS,
                default=defauts.get(CONF_QUARTIERS, []),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=referentiel.quartiers,
                    multiple=True,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_RUES,
                default=defauts.get(CONF_RUES, []),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=sorted(referentiel.rues),
                    multiple=True,
                    custom_value=True,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_JOURS_EXPIRATION,
                default=defauts.get(CONF_JOURS_EXPIRATION, DEFAUT_JOURS_EXPIRATION),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_JOURS_EXPIRATION,
                    max=MAX_JOURS_EXPIRATION,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="jours",
                )
            ),
        }
    )


def _valider(user_input: dict[str, Any]) -> str | None:
    """Au moins une zone de veille doit être définie."""
    if (
        not user_input.get(CONF_TOUTE_LA_VILLE)
        and not user_input.get(CONF_QUARTIERS)
        and not user_input.get(CONF_RUES)
    ):
        return "aucune_zone"
    return None


def _normaliser_input(user_input: dict[str, Any]) -> dict[str, Any]:
    return {
        CONF_TOUTE_LA_VILLE: bool(user_input.get(CONF_TOUTE_LA_VILLE, False)),
        CONF_QUARTIERS: user_input.get(CONF_QUARTIERS, []),
        CONF_RUES: user_input.get(CONF_RUES, []),
        CONF_JOURS_EXPIRATION: int(
            user_input.get(CONF_JOURS_EXPIRATION, DEFAUT_JOURS_EXPIRATION)
        ),
    }


class TravauxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow Travaux Besançon — choix des zones de veille (ville, quartiers, rues)."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        # Une seule instance : toutes les zones se gèrent dans la même entrée
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        referentiel = await self.hass.async_add_executor_job(charger_embarque)

        if user_input is not None:
            erreur = _valider(user_input)
            if erreur:
                errors["base"] = erreur
            else:
                return self.async_create_entry(
                    title="Travaux Besançon",
                    data=_normaliser_input(user_input),
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(referentiel, user_input or {}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> TravauxOptionsFlow:
        return TravauxOptionsFlow()


class TravauxOptionsFlow(OptionsFlow):
    """Modification des zones de veille et de la fenêtre d'expiration."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        referentiel = await self.hass.async_add_executor_job(charger_embarque)

        if user_input is not None:
            erreur = _valider(user_input)
            if erreur:
                errors["base"] = erreur
            else:
                return self.async_create_entry(data=_normaliser_input(user_input))

        defauts = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(referentiel, {**defauts, **(user_input or {})}),
            errors=errors,
        )
