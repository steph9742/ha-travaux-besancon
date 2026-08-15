# tests/test_matching.py
"""Tests du module de normalisation/matching — sans dépendance Home Assistant."""
import importlib.util
import json
import sys
import types
from pathlib import Path

COMPOSANT = Path(__file__).parent.parent / "custom_components" / "travaux_besancon"

# matching.py utilise un import relatif (.const) : on charge const sous un nom
# plat puis on exécute matching avec l'import réécrit, sans dépendre de HA.
_spec = importlib.util.spec_from_file_location("const", COMPOSANT / "const.py")
_const = importlib.util.module_from_spec(_spec)
sys.modules["const"] = _const
_spec.loader.exec_module(_const)

matching = types.ModuleType("matching")
exec(
    (COMPOSANT / "matching.py")
    .read_text(encoding="utf-8")
    .replace("from .const import", "from const import"),
    matching.__dict__,
)

normaliser = matching.normaliser
extraire_rues = matching.extraire_rues
type_arrete = matching.type_arrete

REFERENTIEL = json.loads((COMPOSANT / "rues.json").read_text(encoding="utf-8"))["rues"]


# ---------------------------------------------------------------- normaliser

def test_normaliser_accents_et_casse():
    assert normaliser("rue d'Arènes") == "RUE D'ARENES"


def test_normaliser_apostrophe_typographique():
    assert normaliser("rue de l’Escale") == "RUE DE L'ESCALE"


def test_normaliser_espaces_multiples():
    assert normaliser("RUE  FERDINAND   BERTHOUD") == "RUE FERDINAND BERTHOUD"


# ------------------------------------------------------------- extraire_rues

def test_extraction_simple():
    titre = "Arrêté temporaire de circulation RUE DES SAPINS"
    assert extraire_rues(titre, REFERENTIEL) == ["RUE DES SAPINS"]


def test_extraction_avec_accents_dans_le_titre():
    titre = "Arrêté temporaire de stationnement rue d'Arènes"
    assert extraire_rues(titre, REFERENTIEL) == ["RUE D'ARENES"]


def test_extraction_plusieurs_rues():
    titre = "Arrêté temporaire de circulation RUE DE VESOUL ET RUE DE VERDUN"
    assert extraire_rues(titre, REFERENTIEL) == ["RUE DE VESOUL", "RUE DE VERDUN"]


def test_pas_de_match_partiel_sur_nom_imbrique():
    # « GRANDE RUE » existe : un mot collé ne doit pas matcher
    rues = ["GRANDE RUE", "RUE DE LA GRANDE OURSE"]
    assert extraire_rues("Travaux RUE DE LA GRANDE OURSE", rues) == [
        "RUE DE LA GRANDE OURSE"
    ]


def test_plus_long_match_prioritaire():
    rues = ["RUE DE VESOUL", "RUE DE VESOUL PROLONGEE"]
    assert extraire_rues("Travaux RUE DE VESOUL PROLONGEE", rues) == [
        "RUE DE VESOUL PROLONGEE"
    ]


def test_aucune_rue():
    assert extraire_rues("Arrêté de délégation de signature", REFERENTIEL) == []


def test_delimiteur_apostrophe():
    # « RUE DU PUITS » ne doit pas matcher dans un mot précédé d'une apostrophe
    rues = ["RUE DU PUITS"]
    assert extraire_rues("Chantier RUE DU PUITS", rues) == ["RUE DU PUITS"]
    assert extraire_rues("CHANTIERRUE DU PUITS collé", rues) == []


# ---------------------------------------------------------------- type_arrete

def test_type_circulation():
    assert (
        type_arrete("Arrêté temporaire de circulation RUE X")
        == _const.TYPE_CIRCULATION
    )


def test_type_stationnement():
    assert (
        type_arrete("Arrêté temporaire de stationnement RUE X")
        == _const.TYPE_STATIONNEMENT
    )


def test_type_mixte():
    assert (
        type_arrete("Arrêté temporaire de circulation et de stationnement RUE X")
        == _const.TYPE_MIXTE
    )


def test_type_autre():
    assert type_arrete("Arrêté de voirie divers") == _const.TYPE_AUTRE


# ------------------------------------------------- validation sur le flux réel

def test_referentiel_charge():
    assert len(REFERENTIEL) > 1000
    assert "RUE DE DOLE" in REFERENTIEL
    assert len(REFERENTIEL["RUE DE DOLE"]) >= 2  # rue traversant plusieurs quartiers
