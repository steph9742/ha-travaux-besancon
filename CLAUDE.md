# ha-travaux-besancon — Travaux & arrêtés de voirie Besançon

## But

Intégration HACS « travaux dans mes rues » : l'utilisateur configure une liste de rues de Besançon (sa rue, son trajet), l'intégration surveille les arrêtés temporaires de circulation/stationnement de la Ville et notifie quand une rue suivie est concernée. Aucun équivalent n'existe.

## Source de données (vérifiée le 15/08/2026)

**Flux XML des actes de la Ville de Besançon** — sans clé, MAJ plusieurs fois par mois :

```
https://datasets.grandbesancon.fr/actes.php?method=getActesVilleDeBesancon
```

Structure réelle observée (un `<acte>` par arrêté, ~69 en août 2026, quasi tous domaine Voirie) :

```xml
<acte id="VOI.26.00.A02365" siret="21250056500016">
  <titre>Arrêté temporaire de circulation RUE DES SAPINS</titre>
  <domaine>Voirie</domaine>
  <type>Arrêté</type>
  <fichier>https://datasets.grandbesancon.fr/fichiers/actes/00/2026/VOI/VOI.26.00.A02365.pdf</fichier>
  <datePublication>2026-08-05</datePublication>
  <dateActe>2026-08-04</dateActe>
</acte>
```

Points clés :
- **Le nom de la rue est dans le titre** (majuscules, après « Arrêté temporaire de circulation/stationnement »). C'est la clé du matching.
- Le flux remonte **tous les actes depuis 2022** (constaté le 22/09/2026 : ≈ 11 145 actes, 4,4 Mo — il ne renvoyait que le mois courant en août 2026). Conséquence : filtrer par date AVANT le matching, et parser/matcher dans l'executor, jamais dans la boucle d'événements (gel HA vécu le 22/09/2026).
- Le détail (dates précises du chantier, nature) n'est que dans le PDF — hors scope v1 ; titre + datePublication suffisent pour alerter.
- Source complémentaire possible (v2) : la page https://www.grandbesancon.fr/infos-pratiques/urbanisme-voirie-travaux/perturbations-de-circulation/ (liste HTML par quartier, hebdo, plus descriptive) — scraping.
- Vérifié : Besançon est **absente** de DiaLog (base nationale) — pas de raccourci par là.

## Travail à faire

1. Explorer le flux : paramètres acceptés par `actes.php` (mois/année ? autres `method=` ? il existe au moins `getJourDeCollecteDechetsParAdresseAction` sur `dechets.php`, donc l'API est une famille de méthodes).
2. `custom_components/travaux_besancon` sur le modèle de `/Users/stephanegouraud/Code/Claude code/Ginko_velo` : coordinator aiohttp (polling 6-12 h suffit), parsing XML (`xml.etree` ou `defusedxml`).
3. Normalisation des noms de rue (majuscules/accents/abréviations : « RUE D'ARENES » vs « rue d'Arènes ») pour un matching robuste. La liste officielle des rues existe sur le portail open data (« Liste des rues par quartier ») — peut servir d'autocomplete dans le config_flow.
4. Entités :
   - `sensor.travaux_besancon` : état = nb d'arrêtés actifs sur les rues suivies ; attributs = liste (rue, type circulation/stationnement, date, lien PDF).
   - un `binary_sensor` par rue suivie (option) pour des automatisations simples.
   - `event` ou déclencheur pour notifier chaque nouvel arrêté matching.
5. Config flow : liste de rues (multi-select ou texte libre), option « tous les arrêtés voirie » sans filtre.
6. README FR, hacs.json, workflow validate, MIT — mêmes conventions que ha-velocite (`@steph9742`, FR+EN).

## Pièges

- Ne pas re-notifier les mêmes arrêtés à chaque refresh → mémoriser les `id` déjà vus (store HA).
- Le flux couvre la **Ville de Besançon** uniquement (SIRET 21250056500016), pas toute l'agglo — le dire dans le README.
