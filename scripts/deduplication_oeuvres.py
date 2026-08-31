"""Détection des doublons d'œuvre sur put.io — parsing, appariement, classement.

Change `purger-les-doublons-d-oeuvre-putio` (dépôt secretariat). Le même
film existe souvent en plusieurs encodages ; ce module reconnaît qu'il
s'agit de la même œuvre (par titre et année lus du nom de release),
compare les zones communes à elles-mêmes et à la préservation, et propose
un classement — mais ne supprime jamais seul. La suppression est déléguée
au régime préavis + corbeille de `purge_zones_communes`.

Films seulement : les séries (SxxExx, Sxx, saison, intégrale) sont
écartées comme « incertaines » (design D1) — les dédupliquer est un autre
problème.
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

import purge_zones_communes as pzc

ZONES = pzc.ZONES_COMMUNES

# Marqueurs qui font tomber un nom dans l'incertain, avant même l'année.
_SERIE = re.compile(r"(?:s\d{2}(?:e\d{2})?|saison|season|int[ée]grale|complete|coffret|collection)", re.I)
_ANNEE = re.compile(r"(?:^|[.\s(\[_-])(19\d{2}|20[0-3]\d)(?:$|[.\s)\]_-])")


def cle_oeuvre(nom):
    """(titre normalisé, année) — ou None si le nom est incertain.

    Incertain = série/saison/coffret, ou année absente, ou titre vide après
    normalisation. Dans le doute, on ne produit pas de clé : un nom sans clé
    n'entre dans aucune proposition de suppression (design D2, spec).
    """
    if _SERIE.search(nom):
        return None
    m = _ANNEE.search(nom)
    if not m:
        return None
    titre = nom[: m.start(1)]
    titre = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", titre)
    titre = re.sub(r"[._]", " ", titre)
    titre = "".join(c for c in unicodedata.normalize("NFD", titre) if unicodedata.category(c) != "Mn")
    titre = re.sub(r"[^a-z0-9 ]", " ", titre.lower())
    titre = re.sub(r"\s+", " ", titre).strip()
    return (titre, m.group(1)) if titre else None


def _nom_release(chemin):
    """Le nom de release d'un chemin `zone/release[/fichier]` (segment sous la zone)."""
    parts = chemin.split("/")
    return parts[1] if len(parts) > 1 else parts[0]


def grouper(chemins):
    """Groupes de doublons d'œuvre : {clé: [chemins]} pour les clés à ≥2 chemins.

    Les noms incertains (série, sans année, titre vide) n'ont pas de clé et
    n'entrent dans aucun groupe.
    """
    par_cle = {}
    for chemin in chemins:
        k = cle_oeuvre(_nom_release(chemin))
        if k:
            par_cle.setdefault(k, []).append(chemin)
    return {k: v for k, v in par_cle.items() if len(v) > 1}


def doublons_internes(chemins_zone_commune):
    """Doublons d'œuvre au sein des zones communes (front interne, design D3)."""
    return grouper(chemins_zone_commune)


_EDITIONS = ("criterion", "masters of cinema", "remaster")


def resolution(nom):
    """Résolution lisible dans le nom, normalisée (2160p pour 4K)."""
    n = nom.lower()
    if "2160p" in n or "4k" in n:
        return "2160p"
    for tag in ("1080p", "720p", "480p"):
        if tag in n:
            return tag
    return "SD"


def codec(nom):
    """Codec lisible dans le nom, normalisé."""
    n = nom.lower()
    for tag, norm in (("x265", "x265"), ("h265", "x265"), ("hevc", "x265"),
                      ("av1", "av1"), ("x264", "x264"), ("h264", "x264"), ("xvid", "xvid")):
        if tag in n:
            return norm
    return "?"


def edition(nom):
    """Édition de référence reconnue dans le nom, ou None."""
    n = nom.lower()
    return next((e for e in _EDITIONS if e in n), None)


def _rang(nom):
    """Clé de tri décroissante : résolution, puis codec, puis édition connue."""
    res = {"2160p": 4, "1080p": 3, "720p": 2, "480p": 1, "SD": 0}[resolution(nom)]
    cod = {"av1": 3, "x265": 3, "x264": 2, "xvid": 1, "?": 0}[codec(nom)]
    return (res, cod, 1 if edition(nom) else 0)


def classer(noms):
    """Encodages triés du meilleur au moins bon, avec leurs caractéristiques.

    Le tri (résolution, codec, édition) est une PROPOSITION lisible — chaque
    encodage garde son nom visible pour que le mainteneur puisse renverser
    (spec « proposition argumentée »). La fonction ne décide ni ne supprime.
    """
    encodages = [
        {"nom": n, "resolution": resolution(n), "codec": codec(n), "edition": edition(n)}
        for n in noms
    ]
    encodages.sort(key=lambda e: _rang(e["nom"]), reverse=True)
    return encodages


def redondants_avec_preservation(chemins_zone_commune, noms_preservation):
    """Fichiers de zone commune dont l'œuvre est déjà dans le circuit de conservation.

    Le circuit a deux étages (PANTAGRUWEB/ sur put.io + Storage Box) ; on
    reçoit ici leurs noms de release. La cible d'une éventuelle suppression
    est toujours le fichier de zone commune — jamais la préservation (spec).
    """
    deja = _cles_preservees(noms_preservation)
    redondants = []
    for chemin in chemins_zone_commune:
        k = cle_oeuvre(_nom_release(chemin))
        if k and k in deja:
            redondants.append({"cible": chemin, "deja_preserve": deja[k], "cle": k})
    return redondants


def _cles_preservees(noms_preservation):
    deja = {}
    for nom in noms_preservation:
        k = cle_oeuvre(nom)
        if k:
            deja.setdefault(k, nom)
    return deja


def _classer_chemins(chemins):
    return sorted(chemins, key=lambda c: _rang(_nom_release(c)), reverse=True)


def groupes_a_arbitrer(chemins_zone_commune, noms_preservation):
    """Groupes soumis au mainteneur : doublons internes et croisements préservation.

    Un groupe dont l'œuvre est déjà préservée est de type « préservé » (la
    version en sécurité est nommée) ; sinon un groupe de ≥2 encodages de zone
    commune est de type « interne ». Les encodages sont classés (meilleur en
    tête) ; le choix humain tranche.
    """
    deja = _cles_preservees(noms_preservation)
    par_cle = {}
    for chemin in chemins_zone_commune:
        k = cle_oeuvre(_nom_release(chemin))
        if k:
            par_cle.setdefault(k, []).append(chemin)
    groupes = []
    for cle, chemins in par_cle.items():
        if cle in deja:
            groupes.append({"cle": cle, "type": "préservé",
                            "encodages": _classer_chemins(chemins), "deja_preserve": deja[cle]})
        elif len(chemins) > 1:
            groupes.append({"cle": cle, "type": "interne",
                            "encodages": _classer_chemins(chemins), "deja_preserve": None})
    return groupes


def lire_choix(texte):
    """Les valeurs des lignes « garder: … » d'un fichier de propositions, dans l'ordre."""
    return [l.split(":", 1)[1].strip() for l in texte.splitlines() if l.strip().startswith("garder:")]


def chemins_a_purger(groupes, choix):
    """Chemins de zone commune écartés par le choix — jamais la préservation.

    « préservé » purge tous les encodages de zone commune du groupe (la version
    préservée demeure). Un index N garde le N-ième encodage et purge les autres.
    Un choix vide ou None ne purge rien (spec « aucune suppression sans choix »).
    """
    if len(choix) != len(groupes):
        raise ValueError(
            f"{len(choix)} choix « garder: » pour {len(groupes)} groupes — "
            "un bloc a dû être ajouté ou supprimé ; relance le relevé."
        )
    cibles = []
    for groupe, ch in zip(groupes, choix):
        if not ch:
            continue
        encodages = groupe["encodages"]
        if ch.lower().startswith("préserv") or ch.lower().startswith("preserv"):
            cibles += encodages
            continue
        try:
            garde = int(ch)
        except ValueError:
            raise ValueError(f"choix illisible « {ch} » — attendu : un numéro ou « préservé »")
        if not 1 <= garde <= len(encodages):
            raise ValueError(
                f"choix « {ch} » hors plage [1, {len(encodages)}] — "
                "un numéro hors plage purgerait tout le groupe ; corrige-le."
            )
        cibles += [e for i, e in enumerate(encodages, 1) if i != garde]
    return cibles


def valider_cibles(cibles, zones=ZONES):
    """Refuse toute cible hors zone commune — défense en profondeur (spec).

    Lève ValueError si un chemin ne relève pas d'une zone déclarée : la
    dédup ne supprime jamais dans la préservation ni dans un dossier
    personnel, même si le fichier de propositions a été altéré à la main.
    """
    for cible in cibles:
        segments = cible.split("/")
        if segments[0] not in zones or ".." in segments or "" in segments[1:]:
            raise ValueError(f"cible hors zone commune, refusée : {pzc.assainir(cible)}")
    return cibles


def construire_propositions(chemins_zone_commune, noms_preservation, aujourdhui):
    """Le fichier de propositions éditable (texte) et sa structure (pour la relecture).

    Un bloc par groupe, encodages classés, champ « garder: » pré-rempli avec
    la proposition (le meilleur pour un doublon interne, « préservé » quand
    une version est déjà en sécurité). Les noms sont assainis (entrée non
    fiable, cf. audit du change purge).
    """
    groupes = groupes_a_arbitrer(chemins_zone_commune, noms_preservation)
    lignes = [
        f"# Doublons d'œuvre — relevé du {aujourdhui.isoformat()}",
        "# Édite « garder: » (un numéro pour conserver cet encodage, ou « préservé »",
        "# pour garder la version déjà en sécurité), puis :",
        "#   python3 deduplication_oeuvres.py preavis --from <ce fichier>",
        "",
    ]
    for groupe in groupes:
        titre, annee = groupe["cle"]
        if groupe["type"] == "préservé":
            lignes.append(
                f"## [préservé] {titre} ({annee}) — déjà en sécurité : {pzc.assainir(groupe['deja_preserve'])}"
            )
            defaut = "préservé"
        else:
            lignes.append(f"## [interne] {titre} ({annee}) — {len(groupe['encodages'])} encodages")
            defaut = "1"
        for i, chemin in enumerate(groupe["encodages"], 1):
            rel = _nom_release(chemin)
            lignes.append(f"#   {i}. {resolution(rel)} / {codec(rel)} — {pzc.assainir(chemin)}")
        lignes += [f"garder: {defaut}", ""]
    return "\n".join(lignes), {"date": aujourdhui.isoformat(), "groupes": groupes}


# ---------------------------------------------------------------------------
# Procédure (I/O) — vérifiée par exécution réelle sur gabelle (tâches 3.1/3.2)


def scanner_preservation(putio="/mnt/remote/putio", vip="/mnt/remote/vip_video", profondeur=3):
    """Noms de release du circuit de conservation : PANTAGRUWEB/ (put.io) + vip_video."""
    noms = []
    for racine in (Path(putio) / "PANTAGRUWEB", Path(vip)):
        if racine.is_dir():
            noms += _dossiers_profonds(racine, profondeur)
    return noms


def _dossiers_profonds(base, profondeur):
    """Noms des dossiers jusqu'à `profondeur` niveaux — candidats releases."""
    out, niveau = [], [base]
    for _ in range(profondeur):
        suivant = []
        for d in niveau:
            try:
                enfants = [x for x in d.iterdir() if x.is_dir()]
            except OSError:
                enfants = []
            out += [x.name for x in enfants]
            suivant += enfants
        niveau = suivant
    return out


def fichiers_de_release(release_relative, racine="/mnt/remote/putio"):
    """Fichiers (chemin relatif, taille) sous un dossier de release, ou le fichier seul."""
    base = Path(racine) / release_relative
    if base.is_file():
        return [(release_relative, base.stat().st_size)]
    out = []
    for parent, _dossiers, fichiers in os.walk(base):
        for nom in fichiers:
            p = Path(parent) / nom
            out.append((str(p.relative_to(racine)), p.stat().st_size))
    return out


def commande_releve(racine, travail, aujourdhui=None):
    aujourdhui = aujourdhui or date.today()
    travail = Path(travail)
    travail.mkdir(parents=True, exist_ok=True)
    chemins_zc = [c for c, _ in pzc.scanner_zones(racine)]
    releases_zc = sorted({z + "/" + c.split("/", 2)[1] for c in chemins_zc for z in [c.split("/", 1)[0]]})
    noms_preserv = scanner_preservation(racine)
    texte, structure = construire_propositions(releases_zc, noms_preserv, aujourdhui)
    base = travail / f"doublons-{aujourdhui.isoformat()}"
    base.with_suffix(".txt").write_text(texte + "\n", encoding="utf-8")
    base.with_suffix(".json").write_text(
        json.dumps(structure, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"Relevé du {aujourdhui} — {len(structure['groupes'])} groupes à arbitrer.")
    print(f"Propositions : {base}.txt (édite « garder: », puis preavis --from)")
    return 0


def commande_preavis(fichier_propositions, racine, travail, aujourdhui=None):
    aujourdhui = aujourdhui or date.today()
    txt = Path(fichier_propositions)
    structure = json.loads(txt.with_suffix(".json").read_text(encoding="utf-8"))
    choix = lire_choix(txt.read_text(encoding="utf-8"))
    cibles = valider_cibles(chemins_a_purger(structure["groupes"], choix))
    if not cibles:
        print("Aucune suppression retenue — rien à annoncer.")
        return 0
    fichiers = []
    for release in cibles:
        fichiers += fichiers_de_release(release, racine)
    preavis = pzc.construire_preavis(fichiers, aujourdhui, delai_jours=pzc.PREAVIS_JOURS)
    dest = Path(travail) / f"preavis-doublons-{aujourdhui.isoformat()}"
    dest.with_suffix(".json").write_text(
        json.dumps(preavis, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    dest.with_suffix(".md").write_text(pzc.texte_preavis(preavis) + "\n", encoding="utf-8")
    print(f"{len(cibles)} encodages retenus, {len(fichiers)} fichiers, "
          f"{pzc.taille_lisible(sum(t for _, t in fichiers))}.")
    print(f"Préavis : {dest}.md (à publier). Puis, à échéance :")
    print(f"  python3 purge_zones_communes.py purge --from {dest}.json")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--racine", default="/mnt/remote/putio")
    p.add_argument("--travail", default=str(Path.home() / "purge-zones-communes"))
    sous = p.add_subparsers(dest="commande", required=True)
    sous.add_parser("releve", help="détecte les doublons et écrit le fichier de propositions")
    pp = sous.add_parser("preavis", help="depuis un fichier de propositions édité, produit le préavis")
    pp.add_argument("--from", dest="propositions", required=True)
    args = p.parse_args(argv)
    if args.commande == "releve":
        return commande_releve(args.racine, args.travail)
    return commande_preavis(args.propositions, args.racine, args.travail)


if __name__ == "__main__":
    sys.exit(main())
