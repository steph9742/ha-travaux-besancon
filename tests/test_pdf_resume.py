# tests/test_pdf_resume.py
"""Tests du parseur de résumé PDF — sur des textes OCR réels (bruités)."""
import importlib.util
import sys
from pathlib import Path

COMPOSANT = Path(__file__).parent.parent / "custom_components" / "travaux_besancon"

_spec = importlib.util.spec_from_file_location("pdf_resume", COMPOSANT / "pdf_resume.py")
pdf_resume = importlib.util.module_from_spec(_spec)
sys.modules["pdf_resume"] = pdf_resume
_spec.loader.exec_module(pdf_resume)

parser_resume = pdf_resume.parser_resume

# Texte OCR typique (accents perdus) — chantier avec période et empiétement
TRAVAUX = """
Vu la demande de l'entreprise COLAS
Considerant que des travaux de refection des enrobes rendent necessaire d'arreter
la reglementation appropriee du stationnement et de la circulation, afin d'assurer la
securite des usagers RUE DES SAPINS
ARRETE
Article 1 : A compter du 20/08/2026 et jusqu'au 21/08/2026, les prescriptions
suivantes s'appliquent RUE DES SAPINS au droit de l'ECOLE DES SAPINS:
Le stationnement des vehicules est interdit sur 3 places.
un fort empietement sera instaure;
Les pietons seront diriges sur le trottoir d'en face.
"""

# Déménagement un seul jour, sans horaires — avec l'en-tête « Publié le »
# qui ne doit PAS être compté dans la période du chantier
DEMENAGEMENT = """
Publié le : 05/08/2026
Vu la demande de Madame Zanouda Senia
Considerant qu'un demenagement rend necessaire d'arreter la reglementation
Article 1 : Le 15/08/2026, le stationnement des vehicules est interdit au n°44
"""

# Événement multi-articles avec horaires variés
EVENEMENT = """
Vu la demande de la Commune libre de Saint Ferjeux-la Butte
Considerant L'organisation de la Cavalcade de Saint Ferjeux ainsi que de
la brocante
Article 2 : A compter du 11/09/2026 et jusqu'au 14/09/2026, le stationnement des
vehicules est interdit a partir de 8h00 le 11/09 jusqu'a 20h00 le 14/09
Article 3 : Le 13/09/2026, le stationnement des vehicules est interdit de 6h00 a
20h00
Article 6 : Le 13/09/2026, la circulation des vehicules est interdite de 11h00
"""

NUIT = """
Considerant que des travaux de renouvellement de la couche de roulement
rendent necessaire d'arreter la reglementation
Article 1 : A compter du 01/09/2026 et jusqu'au 05/09/2026, de nuit, la
circulation des vehicules est interdite. La vitesse sera limitee a 30 km/h.
"""


def test_demandeur_entreprise():
    assert parser_resume(TRAVAUX)["demandeur"] == "l'entreprise colas"


def test_demandeur_particulier():
    assert parser_resume(DEMENAGEMENT)["demandeur"] == "madame zanouda senia"


def test_motif_travaux():
    assert parser_resume(TRAVAUX)["motif"] == "des travaux de refection des enrobes"


def test_motif_sans_que():
    r = parser_resume(EVENEMENT)
    assert r["motif"].startswith("l'organisation de la cavalcade")


def test_periode_du_au():
    r = parser_resume(TRAVAUX)
    assert r["date_debut"] == "2026-08-20"
    assert r["date_fin"] == "2026-08-21"


def test_periode_jour_unique():
    r = parser_resume(DEMENAGEMENT)
    assert r["date_debut"] == r["date_fin"] == "2026-08-15"


def test_periode_multi_articles():
    r = parser_resume(EVENEMENT)
    assert r["date_debut"] == "2026-09-11"
    assert r["date_fin"] == "2026-09-14"


def test_horaires_plage():
    assert "de 6h00 à 20h00" in parser_resume(EVENEMENT)["horaires"]


def test_horaires_nuit():
    assert "de nuit" in parser_resume(NUIT)["horaires"]


def test_horaires_absents():
    assert parser_resume(DEMENAGEMENT)["horaires"] == []


def test_restrictions_stationnement():
    assert "stationnement interdit" in parser_resume(TRAVAUX)["restrictions"]


def test_restrictions_multiples():
    r = parser_resume(NUIT)["restrictions"]
    assert "circulation interdite" in r
    assert "vitesse limitée" in r


def test_restrictions_empietement_et_pietons():
    r = parser_resume(TRAVAUX)["restrictions"]
    assert "empiétement sur chaussée" in r
    assert "cheminement piétons modifié" in r


def test_texte_vide():
    r = parser_resume("")
    assert r["demandeur"] is None
    assert r["motif"] is None
    assert r["date_debut"] is None
    assert r["horaires"] == []
    assert r["restrictions"] == []
