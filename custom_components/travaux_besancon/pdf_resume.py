# custom_components/travaux_besancon/pdf_resume.py
"""Extraction d'un résumé structuré depuis le texte d'un PDF d'arrêté.

Module pur (aucune dépendance Home Assistant) pour être testable isolément.

Les PDF de la Ville sont générés par le même outil puis océrisés : le texte
est bruité (accents perdus, « Besangon ») mais la structure est très stable :
  - « Vu la demande de <demandeur> »
  - « Considerant que <motif> rend/rendent necessaire… »
  - Articles : « Le DD/MM/YYYY » ou « A compter du DD/MM/YYYY et jusqu'au
    DD/MM/YYYY », horaires « de 8h00 a 17h00 », « la nuit »…
"""
from __future__ import annotations

import re
import unicodedata


def _plat(texte: str) -> str:
    """Minuscules, sans accents, espaces simples — pour la détection."""
    texte = unicodedata.normalize("NFD", texte.lower())
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texte)


def _date_iso(jour: str, mois: str, annee: str) -> str | None:
    try:
        j, m, a = int(jour), int(mois), int(annee)
        if not (1 <= j <= 31 and 1 <= m <= 12 and 2000 <= a <= 2100):
            return None
        return f"{a:04d}-{m:02d}-{j:02d}"
    except ValueError:
        return None


def _heure(h: str, mn: str | None) -> str:
    return f"{int(h)}h{mn if mn else '00'}"


# Phrases clés (texte aplati) → restriction affichable
_RESTRICTIONS = [
    (r"stationnement (?:des vehicules )?(?:est|sera) interdit", "stationnement interdit"),
    (r"circulation (?:des vehicules )?(?:est|sera) interdite", "circulation interdite"),
    (r"route barree", "route barrée"),
    (r"microcoupures?", "microcoupures de circulation"),
    (r"alternat|circulation alternee|feux tricolores", "circulation alternée"),
    (r"mises? en impasse", "mise en impasse"),
    (r"vitesse .{0,30}limitee|limitation de vitesse", "vitesse limitée"),
    (r"sens unique", "sens unique"),
    (r"bande cyclable", "bande cyclable neutralisée"),
    (r"piste cyclable", "piste cyclable neutralisée"),
    (r"chaussee retrecie", "chaussée rétrécie"),
    (r"empietement", "empiétement sur chaussée"),
    (r"pietons? .{0,40}(?:diriges?|devies?|renvoyes?)|cheminement pieton", "cheminement piétons modifié"),
]


def parser_resume(texte: str) -> dict:
    """Extrait {demandeur, motif, date_debut, date_fin, horaires, restrictions}.

    Les champs introuvables valent None (ou liste vide).
    """
    plat = _plat(texte)

    # --- Demandeur -----------------------------------------------------
    demandeur = None
    m = re.search(
        r"vu la demande de\s+(.{3,90}?)\s*(?:vu\s|considerant|\n|$)",
        plat,
    )
    if m:
        demandeur = m.group(1).strip(" ,;.")

    # --- Motif ---------------------------------------------------------
    motif = None
    m = re.search(
        r"considerant\s+(?:que\s+|qu'\s*)?(.{5,160}?)"
        r"(?:\s+rend(?:ent)?\s+necessaires?|\s+necessitent?|\s+afin\s|\s+ainsi que|[.;]|$)",
        plat,
    )
    if m:
        motif = re.sub(r"\s+", " ", m.group(1)).strip(" ,;.")

    # --- Période : min/max des dates citées ----------------------------
    # L'en-tête contient « Publié le : JJ/MM/AAAA » (position variable selon
    # l'ordre d'extraction du PDF) : on l'efface pour ne garder que les dates
    # du chantier elles-mêmes.
    zone_dates = re.sub(r"publie? le\s*:?\s*\d{2}/\d{2}/\d{4}", " ", plat)
    dates = sorted(
        d
        for d in (
            _date_iso(*grp)
            for grp in re.findall(r"\b(\d{2})/(\d{2})/(\d{4})\b", zone_dates)
        )
        if d
    )
    date_debut = dates[0] if dates else None
    date_fin = dates[-1] if dates else None

    # --- Horaires ------------------------------------------------------
    horaires: list[str] = []

    for h1, mn1, h2, mn2 in re.findall(
        r"(?:de|des)\s+(\d{1,2})\s*h\s*(\d{2})?\s*(?:a|jusqu'a)\s+(\d{1,2})\s*h\s*(\d{2})?",
        plat,
    ):
        horaires.append(f"de {_heure(h1, mn1)} à {_heure(h2, mn2)}")

    for h1, mn1, h2, mn2 in re.findall(
        r"entre\s+(\d{1,2})\s*h\s*(\d{2})?\s+et\s+(\d{1,2})\s*h\s*(\d{2})?",
        plat,
    ):
        horaires.append(f"de {_heure(h1, mn1)} à {_heure(h2, mn2)}")

    if not horaires:
        for h1, mn1 in re.findall(r"a partir de\s+(\d{1,2})\s*h\s*(\d{2})?", plat):
            horaires.append(f"à partir de {_heure(h1, mn1)}")

    if re.search(r"\b(?:de|la) nuit\b|\bnocturnes?\b", plat):
        horaires.append("de nuit")
    if re.search(r"24\s*h\s*/\s*24", plat):
        horaires.append("24h/24")

    # Dédoublonnage en conservant l'ordre, borné pour rester lisible
    vus: set[str] = set()
    horaires = [h for h in horaires if not (h in vus or vus.add(h))][:4]

    # --- Restrictions --------------------------------------------------
    restrictions = [
        libelle for motif_re, libelle in _RESTRICTIONS if re.search(motif_re, plat)
    ]

    return {
        "demandeur": demandeur,
        "motif": motif,
        "date_debut": date_debut,
        "date_fin": date_fin,
        "horaires": horaires,
        "restrictions": restrictions,
    }


def texte_depuis_pdf(contenu: bytes) -> str:
    """Extrait le texte d'un PDF (appel bloquant — passer par l'executor)."""
    import io

    from pypdf import PdfReader

    lecteur = PdfReader(io.BytesIO(contenu))
    return "\n".join(page.extract_text() or "" for page in lecteur.pages)
