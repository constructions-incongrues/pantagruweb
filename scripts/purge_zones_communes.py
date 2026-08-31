"""Purge des zones communes de put.io — logique et procédure manuelle.

Change `purger-les-zones-communes-putio` (dépôt secretariat). Règle :
les zones communes sont déclarées nommément ; tout dossier non déclaré
est réputé personnel et n'est jamais touché. L'âge d'un fichier est sa
date de première observation par le relevé — jamais son mtime.

Usage (sur gabelle, à la main — rien ne tourne seul) :

    python3 purge_zones_communes.py releve [--inventaire-initial]
    python3 purge_zones_communes.py purge --from <preavis-AAAA-MM-JJ.json>

`releve` met à jour l'état d'observation et génère le préavis prêt à
poster ; `purge` exige le préavis échu, affiche son dry-run et demande
confirmation avant toute suppression.
"""

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ZONES_COMMUNES = ("chill.institute", "putflix")
AGE_JOURS = 30
PREAVIS_JOURS = 14
CORBEILLE_JOURS = 7


def filtrer_zones(chemins, zones=ZONES_COMMUNES):
    """Ne garde que les chemins strictement sous une zone déclarée.

    Correspondance exacte du premier segment (sensible à la casse et aux
    espaces). Un chemin sans dossier (fichier en vrac à la racine)
    n'appartient à aucune zone.
    """
    retenus = []
    for chemin in chemins:
        premier, separateur, reste = chemin.partition("/")
        if separateur and reste and premier in zones:
            retenus.append(chemin)
    return retenus


def zones_absentes(chemins, zones=ZONES_COMMUNES):
    """Zones déclarées dont aucun chemin ne relève — écart à signaler."""
    presentes = {chemin.partition("/")[0] for chemin in chemins}
    return [zone for zone in zones if zone not in presentes]


def maj_observations(etat, chemins, aujourdhui):
    """Met à jour l'état des premières observations.

    Un chemin nouveau est daté du jour ; un chemin disparu sort de l'état
    (s'il revient, il repart de zéro — c'est la garde « fichier revenu »).
    Retourne (nouvel_etat, apparus, disparus).
    """
    presents = set(chemins)
    nouvel_etat = {c: d for c, d in etat.items() if c in presents}
    apparus = [c for c in chemins if c not in etat]
    for chemin in apparus:
        nouvel_etat[chemin] = aujourdhui.isoformat()
    disparus = sorted(c for c in etat if c not in presents)
    return nouvel_etat, apparus, disparus


def scanner_zones(racine, zones=ZONES_COMMUNES):
    """Listing (chemin relatif, taille) des fichiers des seules zones déclarées.

    Ne descend jamais dans un dossier non déclaré : les dossiers
    personnels ne sont même pas parcourus.
    """
    racine = Path(racine)
    listing = []
    for zone in zones:
        dossier = racine / zone
        if not dossier.is_dir():
            continue
        for parent, _dossiers, fichiers in os.walk(dossier):
            for nom in fichiers:
                chemin = Path(parent) / nom
                listing.append(
                    (str(chemin.relative_to(racine)), chemin.stat().st_size)
                )
    return sorted(listing)


def re_remplissage(apparus, tailles, zones=ZONES_COMMUNES):
    """Nouveautés par zone depuis le cycle précédent — fichiers et octets.

    Toute zone déclarée figure au résultat, même à zéro : le silence est
    un chiffre, pas une absence.
    """
    compte = {zone: {"fichiers": 0, "octets": 0} for zone in zones}
    for chemin in filtrer_zones(apparus, zones):
        zone = chemin.partition("/")[0]
        compte[zone]["fichiers"] += 1
        compte[zone]["octets"] += tailles.get(chemin, 0)
    return compte


def occupation_depuis_du(sortie_du):
    """Parse la sortie de `du -sh` : lignes « TAILLE\\tCHEMIN » → (dossier, taille)."""
    lignes = []
    for ligne in sortie_du.splitlines():
        if not ligne.strip():
            continue
        taille, _, chemin = ligne.partition("\t")
        lignes.append((chemin.rstrip("/").rpartition("/")[2], taille.strip()))
    return lignes


class PreavisNonEchu(ValueError):
    """La date de purge du préavis n'est pas atteinte : purge refusée."""


def construire_preavis(fichiers_avec_tailles, date_emission, delai_jours=PREAVIS_JOURS):
    """Structure de préavis : émission, date de purge, fichiers listés."""
    return {
        "date_emission": date_emission.isoformat(),
        "date_purge": (date_emission + timedelta(days=delai_jours)).isoformat(),
        "fichiers": [
            {"chemin": chemin, "taille": taille} for chemin, taille in fichiers_avec_tailles
        ],
    }


def purgeables(preavis, listing, etat, date_execution, zones=ZONES_COMMUNES):
    """Applique la triple condition de la spec, revérifiée à l'exécution.

    Un chemin n'est purgeable que s'il est (1) listé dans le préavis,
    (2) encore présent dans une zone déclarée, (3) observé depuis avant
    l'émission du préavis — un fichier revenu sous un nom listé repart
    de zéro. Lève PreavisNonEchu tant que la date de purge n'est pas
    atteinte : jamais de suppression anticipée.
    """
    if date_execution < date.fromisoformat(preavis["date_purge"]):
        raise PreavisNonEchu(
            f"préavis échu le {preavis['date_purge']}, nous sommes le {date_execution}"
        )
    presents = set(filtrer_zones(listing, zones))
    emission = preavis["date_emission"]
    return [
        f["chemin"]
        for f in preavis["fichiers"]
        if f["chemin"] in presents and etat.get(f["chemin"], "9999-12-31") <= emission
    ]


def taille_lisible(octets):
    """Taille décimale en français : « 1,5 Go », « 340,0 Mo »."""
    for seuil, unite in ((1e12, "To"), (1e9, "Go"), (1e6, "Mo"), (1e3, "ko")):
        if octets >= seuil:
            return f"{octets / seuil:.1f}".replace(".", ",") + f" {unite}"
    return f"{octets} o"


def _bloc_inerte(lignes):
    """Encadre des noms de fichiers dans un bloc où la syntaxe est inerte."""
    return "~~~~\n" + "\n".join(lignes) + "\n~~~~"


def texte_preavis(preavis):
    """Le préavis prêt à poster sur le canal de coordination."""
    total = sum(f["taille"] for f in preavis["fichiers"])
    lignes = [
        f"{f['chemin']}  ({taille_lisible(f['taille'])})" for f in preavis["fichiers"]
    ]
    return "\n".join(
        [
            f"**Préavis de purge des zones communes put.io** — émis le {preavis['date_emission']}",
            "",
            f"Les fichiers ci-dessous ({len(preavis['fichiers'])} fichiers, "
            f"{taille_lisible(total)}) seront supprimés le **{preavis['date_purge']}**.",
            "",
            "Pour sauver un fichier : le **déplacer** hors de la zone commune — "
            "chez vous pour le garder sous la main, dans `PANTAGRUWEB/` pour le préserver.",
            "",
            _bloc_inerte(lignes),
        ]
    )


def construire_compte_rendu(
    supprimes, tailles, sauves, re_rempl, ecarts, date_execution, corbeille_jours=CORBEILLE_JOURS
):
    """Structure du compte rendu d'exécution d'une purge."""
    return {
        "date": date_execution.isoformat(),
        "supprimes": supprimes,
        "octets_supprimes": sum(tailles.get(c, 0) for c in supprimes),
        "sauves": sauves,
        "re_remplissage": re_rempl,
        "ecarts": ecarts,
        "liberation_corbeille": (date_execution + timedelta(days=corbeille_jours)).isoformat(),
    }


def texte_compte_rendu(cr):
    """Le compte rendu prêt à poster — même une purge sans effet rend compte."""
    parties = [f"**Compte rendu de purge des zones communes** — {cr['date']}", ""]
    if cr["supprimes"]:
        parties += [
            f"Supprimés : {len(cr['supprimes'])} fichiers, "
            f"{taille_lisible(cr['octets_supprimes'])} — partis en corbeille, "
            f"espace libéré le **{cr['liberation_corbeille']}**.",
            "",
            _bloc_inerte(cr["supprimes"]),
            "",
        ]
    else:
        parties += ["Aucun fichier supprimé ce cycle.", ""]
    if cr["sauves"]:
        parties += [
            f"Sauvés par déplacement : {len(cr['sauves'])} fichiers.",
            "",
            _bloc_inerte(cr["sauves"]),
            "",
        ]
    parties.append("Re-remplissage depuis le cycle précédent :")
    for zone, compte in cr["re_remplissage"].items():
        parties.append(
            f"- {zone} : {compte['fichiers']} fichiers, {taille_lisible(compte['octets'])}"
        )
    if cr["ecarts"]:
        parties += ["", "Écarts constatés :"]
        parties += [f"- {e}" for e in cr["ecarts"]]
    return "\n".join(parties)


def eligibles(etat, aujourdhui, age_jours=AGE_JOURS):
    """Chemins observés depuis strictement plus de `age_jours` jours.

    Ne dépend que de l'état d'observation — jamais du mtime (design D3).
    """
    return [
        chemin
        for chemin, premiere in sorted(etat.items())
        if (aujourdhui - date.fromisoformat(premiere)).days > age_jours
    ]


# ---------------------------------------------------------------------------
# Procédure (I/O) — vérifiée par exécution réelle sur gabelle, cf. tasks 3.1/3.2


def _charger_observations(chemin_etat):
    """L'état d'observation ; absent ou illisible = vide (échec du côté sûr)."""
    try:
        return json.loads(Path(chemin_etat).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def commande_releve(racine, travail, inventaire_initial=False, aujourdhui=None, avec_occupation=True):
    """Relevé : met à jour l'état, écrit préavis (JSON + texte) et résumé."""
    aujourdhui = aujourdhui or date.today()
    travail = Path(travail)
    travail.mkdir(parents=True, exist_ok=True)
    chemin_etat = travail / "observations.json"

    listing = scanner_zones(racine)
    chemins = [c for c, _ in listing]
    tailles = dict(listing)

    etat_avant = _charger_observations(chemin_etat)
    etat, apparus, disparus = maj_observations(etat_avant, chemins, aujourdhui)
    chemin_etat.write_text(
        json.dumps(etat, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8"
    )

    if inventaire_initial:
        vises = chemins
        delai = AGE_JOURS  # la fenêtre initiale vaut l'âge limite : 30 jours
    else:
        vises = eligibles(etat, aujourdhui)
        delai = PREAVIS_JOURS

    preavis = construire_preavis(
        [(c, tailles.get(c, 0)) for c in vises], aujourdhui, delai_jours=delai
    )
    nom = f"preavis-{aujourdhui.isoformat()}"
    (travail / f"{nom}.json").write_text(
        json.dumps(preavis, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (travail / f"{nom}.md").write_text(texte_preavis(preavis) + "\n", encoding="utf-8")

    if avec_occupation:
        import subprocess

        entrees = sorted(str(p) for p in Path(racine).iterdir())
        du = subprocess.run(
            ["du", "-sh", *entrees], capture_output=True, text=True, check=False
        )
        lignes = [
            f"| {dossier} | {taille} |" for dossier, taille in occupation_depuis_du(du.stdout)
        ]
        (travail / f"occupation-{aujourdhui.isoformat()}.md").write_text(
            "\n".join(
                [f"**Occupation put.io par dossier** — relevé du {aujourdhui.isoformat()}",
                 "", "| Dossier | Taille |", "|---|---:|", *lignes]
            ) + "\n",
            encoding="utf-8",
        )

    ecarts = [f"zone déclarée introuvable : {z}" for z in zones_absentes(chemins)]
    print(f"Relevé du {aujourdhui} — {len(chemins)} fichiers dans les zones déclarées.")
    print(f"Apparus : {len(apparus)} · disparus : {len(disparus)} · visés : {len(vises)}")
    for ecart in ecarts:
        print(f"ÉCART : {ecart}")
    print(f"Préavis : {travail / nom}.md (à poster) et .json (pour la purge)")
    return 0


def commande_purge(racine, travail, chemin_preavis, aujourdhui=None, confirmer=input):
    """Purge : triple condition revérifiée, dry-run, confirmation, suppression."""
    aujourdhui = aujourdhui or date.today()
    racine = Path(racine)
    travail = Path(travail)
    preavis = json.loads(Path(chemin_preavis).read_text(encoding="utf-8"))
    etat = _charger_observations(travail / "observations.json")

    listing = scanner_zones(racine)
    chemins = [c for c, _ in listing]
    tailles = dict(listing)

    try:
        a_purger = purgeables(preavis, chemins, etat, aujourdhui)
    except PreavisNonEchu as refus:
        print(f"REFUS : {refus}", file=sys.stderr)
        return 1

    listes = [f["chemin"] for f in preavis["fichiers"]]
    sauves = [c for c in listes if c not in a_purger]

    print(f"Dry-run — {len(a_purger)} fichiers seraient supprimés "
          f"({taille_lisible(sum(tailles.get(c, 0) for c in a_purger))}) :")
    for chemin in a_purger:
        print(f"  {chemin}")
    print(f"Sauvés (déplacés depuis le préavis) : {len(sauves)}")

    if not a_purger:
        print("Rien à purger.")
    else:
        if confirmer("Le préavis a-t-il été posté sur le canal ? [oui/NON] ").strip().lower() != "oui":
            print("Purge annulée : le préavis doit être publié d'abord.", file=sys.stderr)
            return 1
        attendu = f"purger {len(a_purger)} fichiers"
        if confirmer(f"Pour confirmer, tapez « {attendu} » : ").strip() != attendu:
            print("Purge annulée.", file=sys.stderr)
            return 1

    ecarts = [f"zone déclarée introuvable : {z}" for z in zones_absentes(chemins)]
    supprimes = []
    for chemin in a_purger:
        cible = (racine / chemin).resolve()
        if racine.resolve() not in cible.parents:
            ecarts.append(f"chemin hors racine, ignoré : {chemin}")
            continue
        try:
            cible.unlink()
            supprimes.append(chemin)
        except OSError as erreur:
            ecarts.append(f"échec de suppression : {chemin} ({erreur})")

    # Les dossiers vidés par la purge, et eux seuls, sont retirés — sous les zones uniquement.
    for zone in ZONES_COMMUNES:
        dossier_zone = racine / zone
        if not dossier_zone.is_dir():
            continue
        for parent, dossiers, fichiers in os.walk(dossier_zone, topdown=False):
            if parent != str(dossier_zone) and not dossiers and not fichiers:
                try:
                    Path(parent).rmdir()
                except OSError:
                    pass

    apparus_depuis_etat = [c for c in chemins if c not in etat]
    cr = construire_compte_rendu(
        supprimes=supprimes,
        tailles={**tailles, **{f["chemin"]: f["taille"] for f in preavis["fichiers"]}},
        sauves=sauves,
        re_rempl=re_remplissage(apparus_depuis_etat, tailles),
        ecarts=ecarts,
        date_execution=aujourdhui,
    )
    nom = f"purge-{aujourdhui.isoformat()}"
    (travail / f"{nom}.json").write_text(
        json.dumps(cr, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (travail / f"compte-rendu-{aujourdhui.isoformat()}.md").write_text(
        texte_compte_rendu(cr) + "\n", encoding="utf-8"
    )
    print(f"Supprimés : {len(supprimes)} · écarts : {len(ecarts)}")
    print(f"Compte rendu : {travail / 'compte-rendu-' }{aujourdhui.isoformat()}.md (à poster)")
    print(f"Liste pour le vidage de corbeille à J+{CORBEILLE_JOURS} : {travail / nom}.json")
    return 0


def noms_pour_corbeille(compte_rendu):
    """Noms de fichiers (sans chemin) à retrouver dans la corbeille put.io.

    La corbeille de l'interface web affiche les fichiers à plat : la
    comparaison se fait sur les noms, triés et dédoublonnés.
    """
    return sorted({chemin.rpartition("/")[2] for chemin in compte_rendu["supprimes"]})


def commande_corbeille(chemin_purge):
    """Liste de contrôle pour le vidage sélectif à J+7 — geste manuel, web.

    L'API v2 documentée de put.io n'expose pas la corbeille (vérifié le
    2026-08-31) ; le vidage est donc un geste dans l'interface web,
    guidé par cette liste. `rclone cleanup` est proscrit : il viderait
    toute la corbeille, suppressions manuelles des membres comprises.
    """
    cr = json.loads(Path(chemin_purge).read_text(encoding="utf-8"))
    noms = noms_pour_corbeille(cr)
    print(f"Vidage sélectif de la corbeille — cycle du {cr['date']}, "
          f"prévu le {cr['liberation_corbeille']}.")
    print(f"{len(noms)} noms à retrouver dans https://app.put.io/trash :\n")
    for nom in noms:
        print(f"  {nom}")
    print(
        "\nProcédure : comparer le contenu de la corbeille à cette liste.\n"
        "- Si la corbeille ne contient QUE ces fichiers : « Empty trash » est équivalent au tri.\n"
        "- Sinon : sélectionner et supprimer uniquement ces fichiers, un à un.\n"
        "- JAMAIS `rclone cleanup` : il vide tout, y compris ce qui n'est pas au cycle."
    )
    return 0


def main(argv=None):
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--racine", default="/mnt/remote/putio")
    parseur.add_argument("--travail", default=str(Path.home() / "purge-zones-communes"))
    sous = parseur.add_subparsers(dest="commande", required=True)
    p_releve = sous.add_parser("releve", help="met à jour l'état et génère le préavis")
    p_releve.add_argument("--inventaire-initial", action="store_true",
                          help="premier cycle : tout lister, fenêtre de 30 jours")
    p_purge = sous.add_parser("purge", help="exécute un préavis échu, après confirmation")
    p_purge.add_argument("--from", dest="preavis", required=True,
                         help="le fichier preavis-AAAA-MM-JJ.json à exécuter")
    p_corbeille = sous.add_parser(
        "corbeille", help="liste de contrôle du vidage sélectif à J+7 (geste web)"
    )
    p_corbeille.add_argument("--from", dest="purge", required=True,
                             help="le fichier purge-AAAA-MM-JJ.json du cycle")
    args = parseur.parse_args(argv)
    if args.commande == "releve":
        return commande_releve(args.racine, args.travail, args.inventaire_initial)
    if args.commande == "corbeille":
        return commande_corbeille(args.purge)
    return commande_purge(args.racine, args.travail, args.preavis)


if __name__ == "__main__":
    sys.exit(main())
