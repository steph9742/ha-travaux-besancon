# Travaux Besançon pour Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Validate](https://github.com/steph9742/ha-travaux-besancon/actions/workflows/validate.yml/badge.svg)](https://github.com/steph9742/ha-travaux-besancon/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Intégration Home Assistant qui surveille les **arrêtés temporaires de circulation et de stationnement** de la Ville de Besançon et vous alerte quand une zone que vous suivez est concernée : **votre rue, votre quartier, ou toute la ville**.

Les données proviennent du flux officiel des actes de la Ville publié sur le portail open data de Grand Besançon Métropole, croisé avec le référentiel officiel des 1 040 rues et 14 quartiers de la ville. Une **carte Lovelace dédiée** est incluse — aucune installation séparée nécessaire.

> *English: Home Assistant integration that watches the City of Besançon's official temporary traffic and parking orders (open data feed) and alerts you when a street, district, or the whole city you watch is affected. Ships with a dedicated Lovelace card.*

## Fonctionnalités

- **Zones de veille au choix** : rues précises (autocomplete sur les 1 040 rues officielles), quartiers (parmi les 14), ou toute la ville
- **Notification des nouveaux arrêtés** via une entité événement et un événement sur le bus HA — sans jamais re-notifier deux fois le même arrêté (mémoire persistante)
- **Résumé automatique de chaque arrêté** extrait du PDF officiel : période réelle du chantier, motif, horaires (jour/nuit/plages), restrictions (stationnement interdit, circulation alternée…), demandeur
- **Marqueurs sur la carte** : chaque chantier apparaît sur la carte map de Home Assistant (93 % des rues géocodées) — un clic sur un marqueur affiche le résumé complet
- Type d'arrêté détecté automatiquement : **circulation**, **stationnement** ou les deux
- **Lien direct vers le PDF** officiel de chaque arrêté
- **Carte Lovelace incluse** avec éditeur visuel : mode flux (liste détaillée avec résumés, regroupable par rue ou quartier) ou compact
- Interface en français (et anglais)

## Installation

### Via HACS (recommandé)

1. Dans HACS, ouvrez le menu **⋮** → **Dépôts personnalisés**
2. Ajoutez l'URL `https://github.com/steph9742/ha-travaux-besancon` avec le type **Intégration**
3. Recherchez **Travaux Besançon** dans HACS et installez
4. Redémarrez Home Assistant
5. Allez dans **Paramètres → Appareils et services → Ajouter une intégration** et cherchez **Travaux Besançon**

### Manuelle

1. Copiez le dossier `custom_components/travaux_besancon` dans le dossier `custom_components/` de votre configuration Home Assistant
2. Redémarrez Home Assistant
3. Ajoutez l'intégration depuis **Paramètres → Appareils et services**

## Configuration

Tout se fait dans l'interface : cochez **toute la ville**, choisissez des **quartiers** et/ou des **rues**. Les zones sont modifiables à tout moment via **Configurer** sur l'intégration.

Le flux officiel ne publie pas la date de fin des chantiers (elle n'est que dans le PDF) : un arrêté est considéré « actif » pendant une durée réglable après sa publication (**14 jours par défaut**).

## Entités

| Entité | Description |
|---|---|
| `sensor.travaux_besancon` | Nombre d'arrêtés actifs sur vos zones. Attribut `arretes` : liste détaillée (rues, quartiers, type, date, résumé, lien PDF) |
| `binary_sensor.travaux_<zone>` | Une entité par zone suivie — `on` si au moins un arrêté actif la concerne |
| `event.travaux_besancon_nouvel_arrete` | Se déclenche pour chaque nouvel arrêté détecté sur vos zones |
| `geo_location.travaux_<rue>` | Un marqueur par chantier géolocalisé (état = distance au domicile en km), avec le résumé complet en attributs |

Le **nom affiché** du capteur principal reflète les zones surveillées : « Travaux St-Claude-Torcols » pour un quartier, « Travaux St-Claude-Torcols, Rue De Vesoul » pour plusieurs zones (« +N » au-delà de trois), et « Travaux Besançon » en mode ville entière. Les capteurs binaires portent chacun le nom de leur zone.

À la première synchronisation, les arrêtés déjà en cours sont mémorisés **sans** déclencher de notifications.

## Automatisation d'exemple

```yaml
automation:
  - alias: "Notification travaux dans ma rue"
    triggers:
      - trigger: event
        event_type: travaux_besancon_nouvel_arrete
    actions:
      - action: notify.mobile_app_mon_telephone
        data:
          title: "🚧 Nouvel arrêté de voirie"
          message: >-
            {{ trigger.event.data.titre }}
            ({{ trigger.event.data.date_publication }})
          data:
            url: "{{ trigger.event.data.url_pdf }}"
```

Le payload de l'événement contient : `id`, `titre`, `type` (`circulation` / `stationnement` / `circulation_stationnement`), `rues`, `quartiers`, `date_publication`, `date_acte`, `url_pdf`, `zones` (les zones de veille touchées).

## Carte des chantiers (map)

Chaque arrêté actif sur vos zones devient un **marqueur géolocalisé** (pastille cône, colorée selon le type : orange circulation, bleu stationnement). Deux façons de l'afficher :

**Recommandé — le mode carte de la carte incluse**, avec un panneau de détail intégré : un clic sur un marqueur affiche directement le chantier — type, motif (« travaux de réfection des enrobés »…), période réelle, horaires (« de 8h00 à 17h00 », « de nuit »…), numéro dans la rue, restrictions, demandeur, quartiers et bouton vers le PDF :

```yaml
type: custom:travaux-besancon-card
mode: carte
entity: sensor.travaux_besancon
map_height: 320   # optionnel, en pixels
```

**Alternative — la carte Map native** de Home Assistant (le clic ouvre alors la fiche d'entité standard, avec les mêmes informations dans la section « Attributs ») :

```yaml
type: map
geo_location_sources:
  - travaux_besancon
default_zoom: 13
```

Le géocodage des rues (BAN + OpenStreetMap) est embarqué dans l'intégration : ~93 % des rues ont des coordonnées ; les quelques voies inconnues des géocodeurs (certains sentiers ou chemins) n'affichent pas de marqueur mais restent visibles dans la liste.

## Résumé des arrêtés (PDF)

Le détail d'un chantier (dates réelles, motif, horaires, restrictions) n'est publié que dans le PDF de chaque arrêté. L'intégration télécharge les PDF des arrêtés qui concernent vos zones (15 max par cycle), en extrait un résumé structuré et le met en cache définitivement — chaque PDF n'est lu qu'une seule fois. Le résumé alimente la carte map, la carte Lovelace et les attributs des capteurs.

Les PDF étant océrisés par la Ville, l'extraction est tolérante aux fautes d'OCR et restaure les accents et apostrophes des mots courants (« réfection », « déménagement », « d'une »…) ; en cas d'échec sur un champ, il est simplement omis.

Dans les arrêtés couvrant plusieurs rues, la carte Lovelace affiche **en gras les rues qui relèvent de vos zones de veille** — les autres restent en gris.

## Carte Lovelace

La carte `travaux-besancon-card` est enregistrée automatiquement à l'installation. Ajoutez-la depuis l'éditeur de tableau de bord (**Ajouter une carte → Travaux Besançon**) — un éditeur visuel permet de tout configurer sans YAML.

### Mode flux (liste détaillée)

```yaml
type: custom:travaux-besancon-card
entity: sensor.travaux_besancon
mode: flux
group_by: quartier   # optionnel : none | rue | quartier
max_items: 10
```

### Mode compact

```yaml
type: custom:travaux-besancon-card
entity: sensor.travaux_besancon
mode: compact
title: Travaux
```

## Sources de données et limites

- **Flux des actes** : `https://datasets.grandbesancon.fr/actes.php?method=getActesVilleDeBesancon` — mis à jour plusieurs fois par mois, interrogé toutes les 6 heures.
- **Référentiel rues/quartiers** : dataset officiel [« Rues et quartiers »](https://data.grandbesancon.fr/opendata/dataset/rueQuartiers) — une copie est embarquée dans l'intégration (fonctionnement hors ligne) et rafraîchie automatiquement au démarrage.
- Le flux couvre la **Ville de Besançon uniquement** (pas les autres communes de Grand Besançon Métropole).
- Le flux ne publie que le **mois courant** et le détail des chantiers (dates précises, nature) n'est disponible que dans le PDF de chaque arrêté.
- Une rue traversant plusieurs quartiers (ex. rue de Dole) déclenche l'alerte de chacun de ses quartiers.

## Licence

[MIT](LICENSE) — données publiques de la Ville de Besançon / Grand Besançon Métropole.
