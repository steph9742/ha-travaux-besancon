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


# L'OCR de la Ville perd accents et apostrophes ; on répare les mots fréquents
# des arrêtés via un lexique fermé (aucune correction ambiguë).
_APOSTROPHES = {
    "dun": "d'un", "dune": "d'une", "dacces": "d'accès",
    "lacces": "l'accès", "leau": "l'eau", "lecole": "l'école",
    "leglise": "l'église", "lentreprise": "l'entreprise",
    "lassociation": "l'association", "limmeuble": "l'immeuble",
    "linstallation": "l'installation", "lintervention": "l'intervention",
    "lorganisation": "l'organisation",
}
_ACCENTS = {
    "acces": "accès", "amenagement": "aménagement", "amenagements": "aménagements",
    "ceremonie": "cérémonie", "chaussee": "chaussée", "controle": "contrôle",
    "creation": "création", "degagement": "dégagement",
    "demenagement": "déménagement", "demenagements": "déménagements",
    "demolition": "démolition",
    "demolitions": "démolitions", "deploiement": "déploiement",
    "deviation": "déviation", "echafaudage": "échafaudage",
    "eclairage": "éclairage", "ecole": "école", "eglise": "église",
    "elagage": "élagage", "elections": "élections", "energie": "énergie",
    "enrobe": "enrobé", "enrobes": "enrobés", "evenement": "événement",
    "evenements": "événements", "fete": "fête", "hopital": "hôpital",
    "materiaux": "matériaux", "musee": "musée", "necessaire": "nécessaire",
    "pieton": "piéton", "pietons": "piétons", "realisation": "réalisation",
    "refection": "réfection", "rehabilitation": "réhabilitation",
    "renovation": "rénovation", "reparation": "réparation",
    "reparations": "réparations", "reseau": "réseau", "reseaux": "réseaux",
    "securite": "sécurité", "telecom": "télécom",
    "telecommunications": "télécommunications", "theatre": "théâtre",
    "universite": "université", "vegetation": "végétation",
    "vehicule": "véhicule", "vehicules": "véhicules",
    "velo": "vélo", "velos": "vélos",
}
_LEXIQUE = {**_APOSTROPHES, **_ACCENTS}


def nettoyer_texte(texte: str) -> str:
    """Restaure apostrophes et accents perdus par l'OCR (lexique fermé)."""
    return re.sub(
        r"[a-z']+", lambda m: _LEXIQUE.get(m.group(0), m.group(0)), texte
    )


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
        demandeur = nettoyer_texte(m.group(1).strip(" ,;."))

    # --- Motif ---------------------------------------------------------
    motif = None
    m = re.search(
        r"considerant\s+(?:que\s+|qu'\s*)?(.{5,160}?)"
        r"(?:\s+rend(?:ent)?\s+necessaires?|\s+necessitent?|\s+afin\s|\s+ainsi que|[.;]|$)",
        plat,
    )
    if m:
        motif = nettoyer_texte(re.sub(r"\s+", " ", m.group(1)).strip(" ,;."))

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

    # --- Numéros dans la rue (déménagements, échafaudages…) ------------
    numeros: list[str] = []
    for n in re.findall(r"\bn[o°]\s*(\d+(?:\s*(?:bis|ter))?)\b", plat):
        n = re.sub(r"\s+", " ", n)
        if n not in numeros:
            numeros.append(n)
    numeros = numeros[:4]

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
        "numeros": numeros,
        "restrictions": restrictions,
    }


def texte_depuis_pdf(contenu: bytes) -> str:
    """Extrait le texte d'un PDF (appel bloquant — passer par l'executor)."""
    import io

    from pypdf import PdfReader

    lecteur = PdfReader(io.BytesIO(contenu))
    return "\n".join(page.extract_text() or "" for page in lecteur.pages)
