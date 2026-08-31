"""Lecteur put.io (API) : dates d'ajout et statut de visionnage des zones communes.

Changes `purger-selon-le-visionnage-putio` puis `baser-l-age-de-purge-sur-created-at`.
**Ce module est le seul à toucher au jeton OAuth et au réseau** — il est isolé
pour que la surface à auditer (fuite de secret) tienne dans un seul fichier. Il
ne fait que LIRE (`/files/list`, champs `created_at` et `first_accessed_at`) ;
il ne supprime jamais.

Contrat : `statut_fichiers()` retourne `(created_at, vus, erreur)` où
`created_at` est `{chemin: 'AAAA-MM-JJ'}` (date d'ajout put.io, source d'âge
**unique** de la purge), `vus` l'ensemble des chemins visionnés, et `erreur`
vaut `None` en cas de succès. Toute défaillance retombe sur `({}, set(), message)`
— échec du côté sûr : sans date d'ajout, aucun fichier n'est éligible et le
cycle est sauté. Le jeton n'apparaît jamais dans un message ou une sortie.
"""

import configparser
import json
import os
import urllib.parse
import urllib.request
from datetime import date

CONF_DEFAUT = os.path.expanduser("~/.config/rclone/rclone.conf")
API = "https://api.put.io/v2"
ZONES = ("chill.institute", "putflix")


def lire_jeton(conf=CONF_DEFAUT):
    """Le jeton OAuth put.io, lu depuis rclone.conf. Lève si absent/illisible."""
    parseur = configparser.ConfigParser()
    parseur.read(conf, encoding="utf-8")
    return json.loads(parseur["putio"]["token"])["access_token"]


def mapping_fichiers(get, zone_ids):
    """`{chemin_relatif: {"first_accessed_at":…, "created_at": 'AAAA-MM-JJ'|None}}`.

    `get(parent_id)` renvoie une liste de dicts `{id, name, file_type,
    first_accessed_at, created_at}` — injectable (mock en test, API réelle en
    prod). Le chemin reconstruit a la même forme que `scanner_zones` :
    `zone/.../fichier`. La date d'ajout est ramenée à la date seule (`[:10]`)
    pour se comparer proprement aux seuils en jours.
    """
    mapping = {}
    for zone_nom, zone_id in zone_ids.items():
        _descendre(get, zone_id, zone_nom, mapping)
    return mapping


def _descendre(get, parent_id, prefixe, mapping):
    for f in get(parent_id):
        chemin = f"{prefixe}/{f['name']}"
        if f.get("file_type") == "FOLDER":
            _descendre(get, f["id"], chemin, mapping)
        else:
            cree = f.get("created_at")
            mapping[chemin] = {
                "first_accessed_at": f.get("first_accessed_at"),
                "created_at": cree[:10] if cree else None,
            }


def ensemble_vus(mapping):
    """Les chemins dont le statut de visionnage n'est pas nul (déjà vus)."""
    return {chemin for chemin, info in mapping.items() if info.get("first_accessed_at")}


def _est_date(valeur):
    """Vrai si `valeur` est une date ISO analysable — garde de frontière."""
    try:
        date.fromisoformat(valeur)
        return True
    except (TypeError, ValueError):
        return False


def dates_creation(mapping):
    """`{chemin: 'AAAA-MM-JJ'}` — seuls les fichiers dont l'API donne une date
    d'ajout **analysable**.

    Un fichier sans date d'ajout, ou dont la date est illisible (API douteuse —
    validation à la frontière, principe déclaratif), est absent : il ne sera
    éligible à aucun seuil (échec du côté sûr — on ne devine pas un âge, et une
    date pourrie ne fait pas planter le relevé au `date.fromisoformat`).
    """
    return {
        chemin: info["created_at"]
        for chemin, info in mapping.items()
        if _est_date(info.get("created_at"))
    }


def collecte(get, zone_ids):
    """`(created_at, vus)` depuis un `get()` injectable — pur, testable hors ligne."""
    mapping = mapping_fichiers(get, zone_ids)
    return dates_creation(mapping), ensemble_vus(mapping)


def _sur(producteur):
    """Enveloppe côté sûr : `producteur()` -> (created_at, vus), ou ({}, set(), message).

    N'importe quelle exception devient un repli. Le message ne porte que le
    TYPE de l'erreur — jamais son texte, où le jeton pourrait s'être glissé.
    """
    try:
        created_at, vus = producteur()
        return created_at, vus, None
    except Exception as erreur:  # noqa: BLE001 — repli total voulu (échec côté sûr)
        return {}, set(), f"statut put.io indisponible ({type(erreur).__name__}) — cycle sauté"


# --- Accès API réel (couche réseau) — vérifié sur gabelle ---


def _api(jeton, path, **params):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    requete = urllib.request.Request(url, headers={"Authorization": "Bearer " + jeton})
    with urllib.request.urlopen(requete, timeout=30) as reponse:
        return json.load(reponse)


def statut_fichiers(zones=ZONES, conf=CONF_DEFAUT):
    """`(created_at, vus, erreur)` réel : lit le jeton, interroge l'API, calcule."""
    def producteur():
        jeton = lire_jeton(conf)
        racine = _api(jeton, "/files/list", parent_id=0, per_page=1000)["files"]
        zone_ids = {f["name"]: f["id"] for f in racine if f["name"] in zones}
        return collecte(
            lambda pid: _api(jeton, "/files/list", parent_id=pid, per_page=1000)["files"],
            zone_ids,
        )
    return _sur(producteur)
