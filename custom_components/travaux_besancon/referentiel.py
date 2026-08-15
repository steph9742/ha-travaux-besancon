# custom_components/travaux_besancon/referentiel.py
"""Référentiel rues → quartiers de Besançon.

Un rues.json est embarqué dans l'intégration (fonctionnement hors ligne,
config flow instantané). Au démarrage, le coordinator tente de le rafraîchir
depuis le CSV officiel du portail open data ; en cas d'échec, l'embarqué sert
de secours.
"""
from __future__ import annotations

import csv
import io
import json
import logging
from pathlib import Path

import aiohttp

from .const import URL_RUES_CSV
from .matching import normaliser

_LOGGER = logging.getLogger(__name__)

CHEMIN_RUES_JSON = Path(__file__).parent / "rues.json"
CHEMIN_GEO_JSON  = Path(__file__).parent / "rues_geo.json"


class Referentiel:
    """Table rue normalisée → liste de quartiers (une rue peut en traverser plusieurs)."""

    def __init__(self, rues: dict[str, list[str]]) -> None:
        self.rues = rues
        self.quartiers = sorted({q for qs in rues.values() for q in qs})

    def quartiers_de(self, rue_normalisee: str) -> list[str]:
        return self.rues.get(rue_normalisee, [])

    def rues_du_quartier(self, quartier: str) -> set[str]:
        quartier = normaliser(quartier)
        return {r for r, qs in self.rues.items() if quartier in qs}


def charger_embarque() -> Referentiel:
    """Charge le rues.json embarqué (appel bloquant — passer par l'executor)."""
    with open(CHEMIN_RUES_JSON, encoding="utf-8") as f:
        data = json.load(f)
    return Referentiel(data["rues"])


def charger_geo() -> dict[str, list[float]]:
    """Coordonnées [lat, lon] par rue normalisée (appel bloquant — executor).

    Géocodage BAN + Photon/OSM embarqué ; les rues introuvables (certains
    ponts, sentiers…) sont simplement absentes : pas de marqueur pour elles.
    """
    with open(CHEMIN_GEO_JSON, encoding="utf-8") as f:
        return json.load(f)["rues"]


async def rafraichir_depuis_csv(session: aiohttp.ClientSession) -> Referentiel | None:
    """Télécharge et parse le CSV officiel. Retourne None en cas d'échec."""
    try:
        async with session.get(
            URL_RUES_CSV, timeout=aiohttp.ClientTimeout(total=20)
        ) as resp:
            resp.raise_for_status()
            brut = await resp.text(encoding="utf-8-sig")
    except (aiohttp.ClientError, TimeoutError, UnicodeDecodeError) as err:
        _LOGGER.debug("Rafraîchissement du référentiel impossible: %s", err)
        return None

    rues: dict[str, set[str]] = {}
    lignes = list(csv.reader(io.StringIO(brut), delimiter=";"))
    for ligne in lignes[1:]:
        if len(ligne) < 2:
            continue
        rue, quartier = normaliser(ligne[0]), normaliser(ligne[1])
        if rue and quartier:
            rues.setdefault(rue, set()).add(quartier)

    # Garde-fou : un CSV vide ou tronqué ne doit pas remplacer l'embarqué
    if len(rues) < 500:
        _LOGGER.warning(
            "Référentiel distant suspect (%d rues) — utilisation de l'embarqué",
            len(rues),
        )
        return None

    return Referentiel({r: sorted(qs) for r, qs in rues.items()})
