"""Statut de visionnage des fichiers de zone commune, via l'API put.io.

Change `purger-selon-le-visionnage-putio`. **Ce module est le seul à toucher
au jeton OAuth et au réseau** — il est isolé pour que la surface à auditer
(fuite de secret) tienne dans un seul fichier. Il ne fait que LIRE
(`/files/list`, champ `first_accessed_at`) ; il ne supprime jamais.

Contrat : `statut_visionnage()` retourne `(vus, erreur)` où `vus` est
l'ensemble des chemins visionnés et `erreur` vaut `None` en cas de succès.
Toute défaillance (jeton illisible, réseau, réponse inattendue) retombe sur
`(set(), message)` — échec du côté sûr : `eligibles()` n'appliquera alors que
le seuil long. Le jeton n'apparaît jamais dans un message ou une sortie.
"""

import configparser
import json
import os
import urllib.parse
import urllib.request

CONF_DEFAUT = os.path.expanduser("~/.config/rclone/rclone.conf")
API = "https://api.put.io/v2"
ZONES = ("chill.institute", "putflix")


def lire_jeton(conf=CONF_DEFAUT):
    """Le jeton OAuth put.io, lu depuis rclone.conf. Lève si absent/illisible."""
    parseur = configparser.ConfigParser()
    parseur.read(conf, encoding="utf-8")
    return json.loads(parseur["putio"]["token"])["access_token"]


def mapping_visionnage(get, zone_ids):
    """`{chemin_relatif: first_accessed_at}` pour les fichiers des zones.

    `get(parent_id)` renvoie une liste de dicts `{id, name, file_type,
    first_accessed_at}` — injectable (mock en test, API réelle en prod). Le
    chemin reconstruit a la même forme que `scanner_zones` : `zone/.../fichier`.
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
            mapping[chemin] = f.get("first_accessed_at")


def ensemble_vus(mapping):
    """Les chemins dont le statut de visionnage n'est pas nul (déjà vus)."""
    return {chemin for chemin, date in mapping.items() if date}


def statut_sur(producteur):
    """Enveloppe côté sûr : `producteur()` -> mapping, ou (set(), message).

    N'importe quelle exception devient un repli silencieux. Le message ne
    porte que le TYPE de l'erreur — jamais son texte, où le jeton pourrait
    s'être glissé.
    """
    try:
        return ensemble_vus(producteur()), None
    except Exception as erreur:  # noqa: BLE001 — repli total voulu (design D3)
        return set(), f"visionnage indisponible ({type(erreur).__name__}) — repli sur le seuil de base"


# --- Accès API réel (couche réseau) — vérifié sur gabelle, tâche 3.1 ---


def _api(jeton, path, **params):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    requete = urllib.request.Request(url, headers={"Authorization": "Bearer " + jeton})
    with urllib.request.urlopen(requete, timeout=30) as reponse:
        return json.load(reponse)


def statut_visionnage(zones=ZONES, conf=CONF_DEFAUT):
    """`(vus, erreur)` réel : lit le jeton, interroge l'API, calcule `vus`."""
    def producteur():
        jeton = lire_jeton(conf)
        racine = _api(jeton, "/files/list", parent_id=0, per_page=1000)["files"]
        zone_ids = {f["name"]: f["id"] for f in racine if f["name"] in zones}
        return mapping_visionnage(
            lambda pid: _api(jeton, "/files/list", parent_id=pid, per_page=1000)["files"],
            zone_ids,
        )
    return statut_sur(producteur)
