# custom_components/travaux_besancon/matching.py
"""Normalisation des noms de rue et matching titre d'arrêté ↔ référentiel.

Module pur (aucune dépendance Home Assistant) pour être testable isolément.

Le flux d'actes écrit les rues en majuscules non accentuées (« RUE D'ARENES »),
le référentiel rues.json utilise la même graphie : une normalisation simple
(majuscules, accents, apostrophes, espaces) suffit pour un matching exact.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from .const import TYPE_AUTRE, TYPE_CIRCULATION, TYPE_MIXTE, TYPE_STATIONNEMENT


def normaliser(texte: str) -> str:
    """Majuscules, sans accents, apostrophe droite, espaces simples."""
    texte = unicodedata.normalize("NFD", texte.upper())
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    texte = texte.replace("’", "'")
    return re.sub(r"\s+", " ", texte).strip()


def _motif(rue_normalisee: str) -> re.Pattern:
    # Délimiteurs : le nom ne doit pas être précédé/suivi d'un caractère de mot,
    # pour éviter que « RUE DES SAPINS » matche au milieu d'un autre nom.
    return re.compile(
        r"(?<![A-Z0-9'])" + re.escape(rue_normalisee) + r"(?![A-Z0-9'])"
    )


def extraire_rues(titre: str, rues: Iterable[str]) -> list[str]:
    """Retourne les rues du référentiel présentes dans un titre d'arrêté.

    Un titre peut citer plusieurs rues. En cas de noms imbriqués
    (« RUE DE VESOUL » dans « RUE DE VESOUL PROLONGEE »), seul le
    match le plus long à une position donnée est conservé.
    """
    titre_norm = normaliser(titre)

    # Toutes les occurrences (rue, début, fin), les plus longues d'abord
    occurrences: list[tuple[str, int, int]] = []
    for rue in rues:
        for m in _motif(rue).finditer(titre_norm):
            occurrences.append((rue, m.start(), m.end()))
    occurrences.sort(key=lambda o: o[2] - o[1], reverse=True)

    retenues: list[tuple[str, int, int]] = []
    for rue, debut, fin in occurrences:
        contenu = any(debut >= d and fin <= f for _, d, f in retenues)
        if not contenu and rue not in (r for r, _, _ in retenues):
            retenues.append((rue, debut, fin))

    # Ordre d'apparition dans le titre
    retenues.sort(key=lambda o: o[1])
    return [rue for rue, _, _ in retenues]


def type_arrete(titre: str) -> str:
    """Déduit le type (circulation / stationnement / mixte) du titre."""
    titre_norm = normaliser(titre)
    circulation = "CIRCULATION" in titre_norm
    stationnement = "STATIONNEMENT" in titre_norm
    if circulation and stationnement:
        return TYPE_MIXTE
    if circulation:
        return TYPE_CIRCULATION
    if stationnement:
        return TYPE_STATIONNEMENT
    return TYPE_AUTRE
