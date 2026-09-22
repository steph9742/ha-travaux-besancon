# custom_components/travaux_besancon/coordinator.py
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import aiohttp
from defusedxml import ElementTree

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util, slugify

from .const import (
    CODE_INSEE,
    CONF_INCLURE_DEVIATIONS,
    CONF_JOURS_EXPIRATION,
    CONF_QUARTIERS,
    CONF_RUES,
    CONF_TOUTE_LA_VILLE,
    DEFAUT_JOURS_EXPIRATION,
    DOMAIN,
    EVENEMENT_NOUVEL_ARRETE,
    MAX_PDF_PAR_REFRESH,
    SCAN_INTERVAL_HEURES,
    URL_ACTES,
    URL_BAN,
)
from .matching import extraire_rues, normaliser, type_arrete
from .pdf_resume import parser_resume, texte_depuis_pdf
from .referentiel import Referentiel, charger_embarque, charger_geo, rafraichir_depuis_csv

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)

# Durée de rétention des ids d'arrêtés déjà vus (bien au-delà de la fenêtre d'affichage)
RETENTION_VUS = timedelta(days=400)

ZONE_VILLE = "ville"


class TravauxCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Surveille le flux des arrêtés de voirie de la Ville de Besançon.

    Cycle de vie :
      1. Premier refresh : charge le référentiel rues/quartiers (embarqué,
         puis tentative de rafraîchissement depuis le CSV officiel) et la
         mémoire des arrêtés déjà vus (Store HA).
      2. Chaque refresh : télécharge le flux XML, matche les titres contre
         les zones suivies (ville / quartiers / rues), déclenche un événement
         par nouvel arrêté correspondant.

    Le flux remonte tous les actes depuis 2022 (constaté le 22/09/2026 :
    ≈ 11 000 actes, 4,4 Mo) et ne donne pas la date de fin des chantiers :
    un arrêté est considéré « actif » pendant jours_expiration jours après
    sa publication, et les arrêtés expirés sont écartés dès le parsing.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self._session = async_get_clientsession(hass)
        self._store: Store = Store(hass, 1, f"{DOMAIN}_arretes_vus")
        # {id d'acte: date ISO de première détection}
        self._vus: dict[str, str] = {}
        self._store_resumes: Store = Store(hass, 1, f"{DOMAIN}_resumes")
        # {id d'acte: résumé extrait du PDF} — cache persistant, un PDF n'est lu qu'une fois
        self._resumes: dict[str, dict] = {}
        self._initialise = False
        self._premiere_synchro = False
        self.referentiel: Referentiel | None = None
        self.geo: dict[str, list[float]] = {}

        super().__init__(
            hass,
            _LOGGER,
            name="Travaux Besançon",
            update_interval=timedelta(hours=SCAN_INTERVAL_HEURES),
        )

    # ------------------------------------------------------------------
    # Configuration (options prioritaires sur data)
    # ------------------------------------------------------------------

    def _conf(self, cle: str, defaut: Any) -> Any:
        if cle in self.entry.options:
            return self.entry.options[cle]
        return self.entry.data.get(cle, defaut)

    @property
    def toute_la_ville(self) -> bool:
        return bool(self._conf(CONF_TOUTE_LA_VILLE, False))

    @property
    def quartiers_suivis(self) -> list[str]:
        return [normaliser(q) for q in self._conf(CONF_QUARTIERS, [])]

    @property
    def rues_suivies(self) -> list[str]:
        return [normaliser(r) for r in self._conf(CONF_RUES, [])]

    @property
    def jours_expiration(self) -> int:
        return int(self._conf(CONF_JOURS_EXPIRATION, DEFAUT_JOURS_EXPIRATION))

    @property
    def inclure_deviations(self) -> bool:
        return bool(self._conf(CONF_INCLURE_DEVIATIONS, False))

    def zones(self) -> dict[str, dict[str, str]]:
        """Zones de veille : {zone_id: {type, nom}}."""
        zones: dict[str, dict[str, str]] = {}
        if self.toute_la_ville:
            zones[ZONE_VILLE] = {"type": "ville", "nom": "Ville de Besançon"}
        for quartier in self.quartiers_suivis:
            zones[f"quartier_{slugify(quartier)}"] = {"type": "quartier", "nom": quartier}
        for rue in self.rues_suivies:
            zones[f"rue_{slugify(rue)}"] = {"type": "rue", "nom": rue}
        return zones

    # ------------------------------------------------------------------
    # Initialisation (référentiel + mémoire des arrêtés vus)
    # ------------------------------------------------------------------

    async def _initialiser(self) -> None:
        self.referentiel = await self.hass.async_add_executor_job(charger_embarque)
        self.geo = await self.hass.async_add_executor_job(charger_geo)

        distant = await rafraichir_depuis_csv(self._session)
        if distant is not None:
            self.referentiel = distant
            _LOGGER.debug(
                "Référentiel rafraîchi depuis le CSV officiel (%d rues)",
                len(distant.rues),
            )

        memoire = await self._store.async_load()
        if memoire is None:
            # Première installation : les arrêtés du flux seront mémorisés
            # sans déclencher d'événements (évite une rafale de notifications).
            self._premiere_synchro = True
        else:
            self._vus = memoire.get("vus", {})

        resumes = await self._store_resumes.async_load()
        if resumes is not None:
            self._resumes = resumes.get("resumes", {})

        self._initialise = True

    async def _sauvegarder_vus(self) -> None:
        limite = (dt_util.now() - RETENTION_VUS).date().isoformat()
        self._vus = {i: d for i, d in self._vus.items() if d >= limite}
        await self._store.async_save({"vus": self._vus})

    # ------------------------------------------------------------------
    # Refresh principal
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        if not self._initialise:
            await self._initialiser()

        try:
            async with self._session.get(URL_ACTES, timeout=REQUEST_TIMEOUT) as resp:
                resp.raise_for_status()
                brut = await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Erreur réseau flux des actes: {err}") from err

        # Le flux remonte TOUS les actes depuis 2022 (≈ 11 000, 4,4 Mo) : parsing
        # XML et matching des rues sont du CPU pur → hors de la boucle d'événements,
        # sinon HA gèle le temps du refresh (vécu 22/09/2026).
        try:
            racine = await self.hass.async_add_executor_job(ElementTree.fromstring, brut)
        except ElementTree.ParseError as err:
            raise UpdateFailed(f"Flux des actes illisible: {err}") from err

        arretes = await self.hass.async_add_executor_job(self._parser_actes, racine)
        actifs = self._filtrer_actifs(arretes)

        # Matching préliminaire sur les rues du titre : détermine quels PDF
        # lire. Le matching final se fait ensuite sur les rues classées
        # (travaux vs déviation) extraites de ces PDF.
        prelim = self._matcher_zones(actifs)
        suivis_prelim = {aid for ids in prelim.values() for aid in ids}
        await self._resumer_pdfs(actifs, sorted(suivis_prelim))
        self._enrichir(actifs)

        par_zone = self._matcher_zones(actifs)
        suivis = sorted(
            {aid for ids in par_zone.values() for aid in ids},
            key=lambda aid: actifs[aid]["date_publication"],
            reverse=True,
        )

        nouveaux = [aid for aid in suivis if aid not in self._vus]
        if nouveaux:
            aujourd_hui = dt_util.now().date().isoformat()
            for aid in nouveaux:
                self._vus[aid] = aujourd_hui
            await self._sauvegarder_vus()

            if self._premiere_synchro:
                _LOGGER.info(
                    "Première synchronisation: %d arrêtés mémorisés sans notification",
                    len(nouveaux),
                )
            else:
                for aid in nouveaux:
                    zones_touchees = [z for z, ids in par_zone.items() if aid in ids]
                    self.hass.bus.async_fire(
                        EVENEMENT_NOUVEL_ARRETE,
                        {**actifs[aid], "zones": zones_touchees},
                    )
        if self._premiere_synchro:
            self._premiere_synchro = False
            nouveaux = []

        return {
            "arretes": actifs,
            "suivis": suivis,
            "par_zone": par_zone,
            "nouveaux": nouveaux,
            "zones": self.zones(),
        }

    # ------------------------------------------------------------------
    # Parsing et matching
    # ------------------------------------------------------------------

    def _parser_actes(self, racine) -> dict[str, dict[str, Any]]:
        arretes: dict[str, dict[str, Any]] = {}
        # Le matching des rues ne sert qu'aux arrêtés encore actifs : on écarte
        # les autres AVANT (même critère que _filtrer_actifs), sinon les
        # ~10 000 arrêtés historiques du flux passaient tous au matching.
        limite = (
            dt_util.now().date() - timedelta(days=self.jours_expiration)
        ).isoformat()
        for acte in racine.iter("acte"):
            aid = acte.get("id", "")
            titre = (acte.findtext("titre") or "").strip()
            domaine = (acte.findtext("domaine") or "").strip()
            if not aid or not titre or domaine != "Voirie":
                continue
            publication = (acte.findtext("datePublication") or "").strip()
            if not publication or publication < limite:
                continue

            rues = extraire_rues(titre, self.referentiel.rues)
            quartiers = sorted(
                {q for r in rues for q in self.referentiel.quartiers_de(r)}
            )
            arretes[aid] = {
                "id": aid,
                "titre": titre,
                "type": type_arrete(titre),
                "rues": rues,
                "quartiers": quartiers,
                "date_publication": (acte.findtext("datePublication") or "").strip(),
                "date_acte": (acte.findtext("dateActe") or "").strip(),
                "url_pdf": (acte.findtext("fichier") or "").strip(),
            }
        return arretes

    def _filtrer_actifs(
        self, arretes: dict[str, dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        limite = (
            dt_util.now().date() - timedelta(days=self.jours_expiration)
        ).isoformat()
        actifs = {}
        for aid, arrete in arretes.items():
            publication = arrete["date_publication"]
            if not publication:
                continue
            try:
                date.fromisoformat(publication)
            except ValueError:
                continue
            if publication >= limite:
                actifs[aid] = arrete
        return actifs

    async def _geocoder_adresse(self, numero: str, rue: str) -> list[float] | None:
        """Coordonnées BAN du numéro dans la rue, ou None si introuvable."""
        try:
            async with self._session.get(
                URL_BAN,
                params={
                    "q": f"{numero} {rue}",
                    "citycode": CODE_INSEE,
                    "type": "housenumber",
                    "limit": 1,
                },
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            _LOGGER.debug("Géocodage BAN de « %s %s » impossible: %s", numero, rue, err)
            return None

        features = data.get("features") or []
        if not features:
            return None
        props = features[0].get("properties", {})
        if props.get("score", 0) < 0.6:
            return None
        lon, lat = features[0]["geometry"]["coordinates"]
        return [round(lat, 6), round(lon, 6)]

    async def _completer_adresse(self, aid: str, arrete: dict[str, Any]) -> None:
        """Géocode le numéro dans la rue (une seule tentative, résultat en cache)."""
        resume = self._resumes.get(aid)
        if (
            not resume
            or not resume.get("numeros")
            or "adresse_coords" in resume
        ):
            return
        rues = resume.get("rues_travaux") or arrete["rues"]
        if len(rues) != 1:
            return
        resume["adresse_coords"] = await self._geocoder_adresse(
            resume["numeros"][0], rues[0]
        )

    async def _resumer_pdfs(
        self, actifs: dict[str, dict[str, Any]], suivis: list[str]
    ) -> None:
        """Télécharge et résume les PDF des arrêtés suivis (avec cache persistant)."""
        # Les résumés d'anciennes versions sans classification des rues sont
        # relus pour en bénéficier (uniquement si l'arrêté cite des rues).
        a_faire = [
            aid for aid in suivis
            if aid not in self._resumes
            or (actifs[aid]["rues"] and "rues_travaux" not in self._resumes[aid])
        ][:MAX_PDF_PAR_REFRESH]

        for aid in a_faire:
            url = actifs[aid]["url_pdf"]
            if not url:
                continue
            try:
                async with self._session.get(url, timeout=REQUEST_TIMEOUT) as resp:
                    resp.raise_for_status()
                    contenu = await resp.read()
            except (aiohttp.ClientError, TimeoutError) as err:
                _LOGGER.debug("PDF %s inaccessible (%s), nouvel essai au prochain refresh", aid, err)
                continue
            try:
                texte = await self.hass.async_add_executor_job(texte_depuis_pdf, contenu)
                self._resumes[aid] = parser_resume(texte, actifs[aid]["rues"])
            except Exception:  # PDF corrompu ou illisible : ne pas réessayer en boucle
                _LOGGER.warning("Impossible de résumer le PDF de l'arrêté %s", aid)
                self._resumes[aid] = {}

        # Géocodage du numéro dans la rue (nouveaux résumés et cache existant)
        for aid in suivis:
            if aid in actifs:
                await self._completer_adresse(aid, actifs[aid])

        # Purge : ne garder que les résumés d'arrêtés encore en mémoire
        self._resumes = {
            aid: r for aid, r in self._resumes.items()
            if aid in self._vus or aid in actifs
        }
        await self._store_resumes.async_save({"resumes": self._resumes})

    def _enrichir(self, actifs: dict[str, dict[str, Any]]) -> None:
        """Attache résumés, classification des rues, coordonnées et surlignage."""
        rues_conf = set(self.rues_suivies)
        quartiers_conf = set(self.quartiers_suivis)

        for aid, arrete in actifs.items():
            resume = self._resumes.get(aid)
            arrete["resume"] = resume

            if resume and "rues_travaux" in resume:
                arrete["rues_travaux"] = resume["rues_travaux"]
                arrete["rues_deviation"] = resume["rues_deviation"]
            else:
                # PDF pas encore lu : toutes les rues du titre par prudence
                arrete["rues_travaux"] = arrete["rues"]
                arrete["rues_deviation"] = []

            alerte = list(arrete["rues_travaux"])
            if self.inclure_deviations:
                alerte += arrete["rues_deviation"]
            arrete["rues_alerte"] = alerte
            arrete["quartiers"] = sorted(
                {q for r in alerte for q in self.referentiel.quartiers_de(r)}
            )
            # Rues mises en évidence par la carte : celles des zones de veille
            arrete["rues_suivies"] = [
                r for r in alerte
                if r in rues_conf
                or quartiers_conf & set(self.referentiel.quartiers_de(r))
            ]

            # Marqueurs : uniquement les rues réellement en travaux ; un numéro
            # géocodé place le marqueur sur l'immeuble plutôt que sur la rue.
            coords = {
                r: self.geo[r] for r in arrete["rues_travaux"] if r in self.geo
            }
            if (
                resume
                and resume.get("adresse_coords")
                and len(arrete["rues_travaux"]) == 1
            ):
                coords = {arrete["rues_travaux"][0]: resume["adresse_coords"]}
            arrete["coordonnees"] = coords

    def _matcher_zones(
        self, actifs: dict[str, dict[str, Any]]
    ) -> dict[str, list[str]]:
        par_zone: dict[str, list[str]] = {zid: [] for zid in self.zones()}

        for aid, arrete in actifs.items():
            rues = arrete.get("rues_alerte", arrete["rues"])
            quartiers = arrete["quartiers"]
            if ZONE_VILLE in par_zone:
                par_zone[ZONE_VILLE].append(aid)
            for quartier in self.quartiers_suivis:
                if quartier in quartiers:
                    par_zone[f"quartier_{slugify(quartier)}"].append(aid)
            for rue in self.rues_suivies:
                if rue in rues:
                    par_zone[f"rue_{slugify(rue)}"].append(aid)

        return par_zone
