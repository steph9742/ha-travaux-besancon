# custom_components/travaux_besancon/const.py
DOMAIN = "travaux_besancon"

URL_ACTES    = "https://datasets.grandbesancon.fr/actes.php?method=getActesVilleDeBesancon"
URL_RUES_CSV = "https://datasets.grandbesancon.fr/fichiers/rues.csv"

# Le flux est mis à jour quelques fois par mois : 6 h de polling suffisent largement.
SCAN_INTERVAL_HEURES = 6

SIRET_VILLE = "21250056500016"

CONF_TOUTE_LA_VILLE   = "toute_la_ville"
CONF_QUARTIERS        = "quartiers"
CONF_RUES             = "rues"
CONF_JOURS_EXPIRATION = "jours_expiration"

DEFAUT_JOURS_EXPIRATION = 14
MIN_JOURS_EXPIRATION    = 1
MAX_JOURS_EXPIRATION    = 60

# Événement envoyé sur le bus HA pour chaque nouvel arrêté correspondant aux zones suivies
EVENEMENT_NOUVEL_ARRETE = f"{DOMAIN}_nouvel_arrete"

# Nombre maximum de PDF d'arrêtés téléchargés et résumés par refresh
# (le rattrapage initial s'étale sur quelques refreshs pour ménager le serveur)
MAX_PDF_PAR_REFRESH = 15

# Types d'arrêtés déduits du titre
TYPE_CIRCULATION    = "circulation"
TYPE_STATIONNEMENT  = "stationnement"
TYPE_MIXTE          = "circulation_stationnement"
TYPE_AUTRE          = "autre"
