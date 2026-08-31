"""Purge des zones communes de put.io — logique et procédure manuelle.

Changes `purger-les-zones-communes-putio` puis `baser-l-age-de-purge-sur-created-at`
(dépôt secretariat). Règle : les zones communes sont déclarées nommément ; tout
dossier non déclaré est réputé personnel et n'est jamais touché. L'âge d'un
fichier est sa **date d'ajout à put.io** (`created_at`, via l'API) — jamais son
mtime, et plus une observation accumulée. Le relevé est sans état.

Usage (sur gabelle, à la main — rien ne tourne seul) :

    python3 purge_zones_communes.py releve
    python3 purge_zones_communes.py purge --from <preavis-AAAA-MM-JJ.json>

`releve` lit l'API (dates d'ajout + visionnage) et génère le préavis prêt à
poster ; `purge` exige le préavis échu, **relit les dates d'ajout par l'API**
(protection re-upload), affiche son dry-run et demande confirmation avant toute
suppression. Sans l'API, le relevé rend un préavis vide et la purge refuse.
"""

import argparse
import json
import os
import sys
import unicodedata
from datetime import date, timedelta
from pathlib import Path

ZONES_COMMUNES = ("chill.institute", "putflix")
AGE_JOURS = 14          # seuil long (tout fichier), resserré de 30→14 le 2026-08-31
AGE_VU_JOURS = 7        # seuil court : un fichier visionné part dès 7 jours
PREAVIS_JOURS = 7       # préavis resserré de 14→7 pour ne pas annuler le seuil de base
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


def construire_preavis(fichiers_avec_tailles, date_emission, delai_jours=PREAVIS_JOURS, vus=None):
    """Structure de préavis : émission, date de purge, fichiers listés.

    `vus` (ensemble de chemins visionnés) marque chaque fichier d'un `vu`
    booléen — le préavis dit ainsi pourquoi un fichier part plus tôt, sans
    nommer qui l'a regardé (compte partagé, design D5).
    """
    vus = vus or set()
    return {
        "date_emission": date_emission.isoformat(),
        "date_purge": (date_emission + timedelta(days=delai_jours)).isoformat(),
        "fichiers": [
            {"chemin": chemin, "taille": taille, "vu": chemin in vus}
            for chemin, taille in fichiers_avec_tailles
        ],
    }


def purgeables(preavis, listing, created_at, date_execution, zones=ZONES_COMMUNES, force=False):
    """Applique la triple condition de la spec, revérifiée à l'exécution.

    Un chemin n'est purgeable que s'il est (1) listé dans le préavis,
    (2) encore présent dans une zone déclarée, (3) d'une date d'ajout put.io
    **courante** antérieure ou égale à l'émission du préavis — un fichier
    ré-ajouté sous un nom listé (nouveau `created_at`, postérieur) est un autre
    fichier, on l'épargne (protection re-upload, design D-E). Une date d'ajout
    absente (fichier disparu du listing API) vaut « 9999 » : épargné, côté sûr.

    Lève PreavisNonEchu tant que la date de purge n'est pas atteinte — SAUF si
    `force` (change `forcer-la-purge-avant-echeance`) : le mainteneur saute
    alors le SEUL contrôle d'échéance, les autres conditions ci-dessus tenant
    toutes. incongru-voix: lessig — purge sans préavis échu régulée par
    architecture (--force) — recours: corbeille 7 j + compte-rendu (voir proposal).
    """
    # incongru-voix: lessig — purge sans préavis échu régulée par architecture (--force) — recours: corbeille 7 j + compte-rendu
    if not force and date_execution < date.fromisoformat(preavis["date_purge"]):
        raise PreavisNonEchu(
            f"préavis échu le {preavis['date_purge']}, nous sommes le {date_execution}"
        )
    presents = set(filtrer_zones(listing, zones))
    emission = preavis["date_emission"]
    return [
        f["chemin"]
        for f in preavis["fichiers"]
        if f["chemin"] in presents and created_at.get(f["chemin"], "9999-12-31") <= emission
    ]


def taille_lisible(octets):
    """Taille décimale en français : « 1,5 Go », « 340,0 Mo »."""
    for seuil, unite in ((1e12, "To"), (1e9, "Go"), (1e6, "Mo"), (1e3, "ko")):
        if octets >= seuil:
            return f"{octets / seuil:.1f}".replace(".", ",") + f" {unite}"
    return f"{octets} o"


def assainir(texte):
    """Retire les caractères de contrôle Unicode (catégorie C*).

    Les noms de fichiers viennent de torrents et des membres — entrée non
    fiable (audit /cso du 2026-08-31). Sans ce passage, un nom porteur de
    séquences ANSI/ESC peut masquer une ligne du dry-run au moment où le
    mainteneur décide de supprimer (finding #3), et un retour à la ligne
    casse le rendu des messages postés.
    """
    return "".join(c if unicodedata.category(c)[0] != "C" else "?" for c in texte)


def _inline(nom):
    """Nom en code inline Markdown — réellement inerte, y compris sur Rocket.Chat.

    Rocket.Chat n'implémente pas les clôtures à tildes ; un nom laissé nu y
    est rendu comme Markdown actif (lien, @mention, faux texte de
    gouvernance — finding #1). Le code inline à backtick, lui, est supporté
    et neutralise le Markdown à l'intérieur ; on retire d'abord les
    backticks (et les contrôles) du nom pour qu'il ne puisse pas en sortir.
    """
    return "`" + assainir(nom).replace("`", "'") + "`"


def ligne_occupation(dossier, taille):
    """Une ligne du tableau d'occupation, cellule de nom neutralisée.

    Le `|` d'un nom de dossier casserait la structure du tableau posté et
    injecterait du Markdown (variante du finding #1) ; il est remplacé par
    une barre brisée visuellement proche mais inoffensive.
    """
    return f"| {_inline(dossier).replace('|', '¦')} | {assainir(taille)} |"


def lignes_dry_run(chemins):
    """Les lignes du dry-run de purge, assainies avant affichage terminal."""
    return [f"  {assainir(chemin)}" for chemin in chemins]


def texte_preavis(preavis):
    """Le préavis prêt à poster sur le canal de coordination."""
    total = sum(f["taille"] for f in preavis["fichiers"])
    lignes = [
        f"- {_inline(f['chemin'])}  ({taille_lisible(f['taille'])})"
        + ("  · vu, part plus tôt" if f.get("vu") else "")
        for f in preavis["fichiers"]
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
            *lignes,
        ]
    )


def construire_compte_rendu(
    supprimes, tailles, sauves, re_rempl, ecarts, date_execution,
    corbeille_jours=CORBEILLE_JOURS, force=False,
):
    """Structure du compte rendu d'exécution d'une purge.

    `force` (purge exécutée avant l'échéance du préavis) est consigné : le texte
    du compte-rendu en fait un avertissement de récupération, seul recours des
    membres qui n'ont pas eu le préavis complet.
    """
    return {
        "date": date_execution.isoformat(),
        "force": force,
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
    if cr.get("force") and cr["supprimes"]:
        parties += [
            "⚠ **Purge exécutée sans attendre l'échéance du préavis.** Les fichiers "
            f"ci-dessous sont **récupérables en corbeille jusqu'au {cr['liberation_corbeille']}** "
            "— déplace-les d'ici là si tu les voulais ; passé cette date, c'est définitif.",
            "",
        ]
    if cr["supprimes"]:
        parties += [
            f"Supprimés : {len(cr['supprimes'])} fichiers, "
            f"{taille_lisible(cr['octets_supprimes'])} — partis en corbeille, "
            f"espace libéré le **{cr['liberation_corbeille']}**.",
            "",
            *[f"- {_inline(chemin)}" for chemin in cr["supprimes"]],
            "",
        ]
    else:
        parties += ["Aucun fichier supprimé ce cycle.", ""]
    if cr["sauves"]:
        parties += [
            f"Sauvés par déplacement : {len(cr['sauves'])} fichiers.",
            "",
            *[f"- {_inline(chemin)}" for chemin in cr["sauves"]],
            "",
        ]
    parties.append("Re-remplissage depuis le cycle précédent :")
    for zone, compte in cr["re_remplissage"].items():
        parties.append(
            f"- {_inline(zone)} : {compte['fichiers']} fichiers, {taille_lisible(compte['octets'])}"
        )
    if cr["ecarts"]:
        parties += ["", "Écarts constatés :"]
        parties += [f"- {assainir(e)}" for e in cr["ecarts"]]
    return "\n".join(parties)


def eligibles(created_at, aujourdhui, vus=None, age_jours=AGE_JOURS, age_vu_jours=AGE_VU_JOURS):
    """Chemins éligibles à la purge, par âge d'ajout put.io et statut de visionnage.

    `created_at` est `{chemin: 'AAAA-MM-JJ'}`, la date d'ajout à put.io (source
    d'âge unique — change `baser-l-age-de-purge-sur-created-at`). Éligible si
    `(âge > age_jours)` — le seuil long, inconditionnel — OU `(chemin ∈ vus ET
    âge > age_vu_jours)` — le seuil court, réservé au visionné. Le visionnage
    n'est qu'un accélérateur : il ne retarde jamais. `vus` absent (None) ⇒ seul
    le seuil long s'applique. Un fichier sans date d'ajout est absent de
    `created_at` : il n'est éligible par aucun seuil (échec du côté sûr).
    L'âge est la date d'ajout, jamais le mtime.
    """
    vus = vus or set()
    retenus = []
    for chemin, ajout in sorted(created_at.items()):
        age = (aujourdhui - date.fromisoformat(ajout)).days
        if age > age_jours or (chemin in vus and age > age_vu_jours):
            retenus.append(chemin)
    return retenus


# ---------------------------------------------------------------------------
# Procédure (I/O) — vérifiée par exécution réelle sur gabelle, cf. tasks 3.1/3.2


def commande_releve(racine, travail, created_at, vus=None, aujourdhui=None, avec_occupation=True):
    """Relevé sans état : l'éligibilité vient des dates d'ajout put.io, pas d'un
    état accumulé (change `baser-l-age-de-purge-sur-created-at`).

    `created_at` ({chemin: 'AAAA-MM-JJ'}) et `vus` viennent de la couche API
    (statut_visionnage). Rien n'est écrit hors du préavis. `created_at` vide
    (API indisponible) ⇒ aucun éligible, préavis vide, cycle sauté.
    """
    aujourdhui = aujourdhui or date.today()
    travail = Path(travail)
    travail.mkdir(parents=True, exist_ok=True)

    listing = scanner_zones(racine)
    chemins = [c for c, _ in listing]
    tailles = dict(listing)

    vises = eligibles(created_at, aujourdhui, vus=vus)
    preavis = construire_preavis(
        [(c, tailles.get(c, 0)) for c in vises], aujourdhui, delai_jours=PREAVIS_JOURS, vus=vus
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
            ligne_occupation(dossier, taille)
            for dossier, taille in occupation_depuis_du(du.stdout)
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
    print(f"Datés par l'API : {len(created_at)} · éligibles : {len(vises)}")
    for ecart in ecarts:
        print(f"ÉCART : {ecart}")
    if not created_at:
        print("AVERTISSEMENT : aucune date d'ajout (API indisponible) — préavis vide, cycle sauté.")
    print(f"Préavis : {travail / nom}.md (à poster) et .json (pour la purge)")
    return 0


def commande_purge(racine, travail, chemin_preavis, created_at, aujourdhui=None, confirmer=input, force=False):
    """Purge : conditions revérifiées (dont la date d'ajout courante), dry-run,
    confirmation, suppression.

    `created_at` ({chemin: 'AAAA-MM-JJ'}) est relu par l'API au moment d'exécuter
    (design D-E) : il porte la protection re-upload. `main` refuse en amont si
    l'API est injoignable — la purge ne s'exécute jamais sans dates d'ajout.

    `force` (change `forcer-la-purge-avant-echeance`) saute le contrôle
    d'échéance ; il exige alors une confirmation supplémentaire qui nomme ce
    qu'on abandonne, et marque le compte-rendu (récupération en corbeille).
    """
    aujourdhui = aujourdhui or date.today()
    racine = Path(racine)
    travail = Path(travail)
    preavis = json.loads(Path(chemin_preavis).read_text(encoding="utf-8"))

    listing = scanner_zones(racine)
    chemins = [c for c, _ in listing]
    tailles = dict(listing)

    try:
        a_purger = purgeables(preavis, chemins, created_at, aujourdhui, force=force)
    except PreavisNonEchu as refus:
        print(f"REFUS : {refus}", file=sys.stderr)
        return 1

    listes = [f["chemin"] for f in preavis["fichiers"]]
    sauves = [c for c in listes if c not in a_purger]

    print(f"Dry-run — {len(a_purger)} fichiers seraient supprimés "
          f"({taille_lisible(sum(tailles.get(c, 0) for c in a_purger))}) :")
    for ligne in lignes_dry_run(a_purger):
        print(ligne)
    print(f"Sauvés (déplacés depuis le préavis) : {len(sauves)}")

    if not a_purger:
        print("Rien à purger.")
    else:
        # Double confirmation. Chemin forcé : la 1re nomme ce qu'on abandonne
        # (préavis non échu), le chemin normal la remplace par « préavis posté ? ».
        if force:
            print(f"FORÇAGE — purge AVANT l'échéance du préavis ({preavis['date_purge']}).",
                  file=sys.stderr)
            print("  Les membres n'ont pas eu le préavis complet. Leur seul recours devient la "
                  f"corbeille (7 j) et le compte-rendu : POSTE-LE.", file=sys.stderr)
            phrase = "purger sans preavis echu"
            if confirmer(f"Pour forcer, tapez « {phrase} » : ").strip() != phrase:
                print("Purge forcée annulée.", file=sys.stderr)
                return 1
        elif confirmer("Le préavis a-t-il été posté sur le canal ? [oui/NON] ").strip().lower() != "oui":
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
            ecarts.append(f"chemin hors racine, ignoré : {assainir(chemin)}")
            continue
        try:
            cible.unlink()
            supprimes.append(chemin)
        except OSError as erreur:
            ecarts.append(f"échec de suppression : {assainir(chemin)} ({assainir(str(erreur))})")

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

    emission = preavis["date_emission"]
    apparus = [c for c in chemins if created_at.get(c, "0000-00-00") > emission]
    cr = construire_compte_rendu(
        supprimes=supprimes,
        tailles={**tailles, **{f["chemin"]: f["taille"] for f in preavis["fichiers"]}},
        sauves=sauves,
        re_rempl=re_remplissage(apparus, tailles),
        ecarts=ecarts,
        date_execution=aujourdhui,
        force=force,
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
        print(f"  {assainir(nom)}")
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
    sous.add_parser("releve", help="lit l'API put.io et génère le préavis")
    p_purge = sous.add_parser("purge", help="exécute un préavis échu, après confirmation")
    p_purge.add_argument("--from", dest="preavis", required=True,
                         help="le fichier preavis-AAAA-MM-JJ.json à exécuter")
    p_purge.add_argument("--force", action="store_true",
                         help="DÉCISION DU MAINTENEUR : purger AVANT l'échéance du préavis "
                              "(double confirmation ; corbeille + compte-rendu restent le recours)")
    p_corbeille = sous.add_parser(
        "corbeille", help="liste de contrôle du vidage sélectif à J+7 (geste web)"
    )
    p_corbeille.add_argument("--from", dest="purge", required=True,
                             help="le fichier purge-AAAA-MM-JJ.json du cycle")
    args = parseur.parse_args(argv)

    if args.commande == "corbeille":
        return commande_corbeille(args.purge)

    # releve et purge lisent tous deux l'âge par l'API (source unique, design D-A/D-E)
    import statut_visionnage  # le seul module à jeton/réseau
    created_at, vus, erreur = statut_visionnage.statut_fichiers(zones=ZONES_COMMUNES)

    if args.commande == "releve":
        if erreur:
            print(f"AVERTISSEMENT — {erreur} : préavis vide, cycle sauté.", file=sys.stderr)
        else:
            print(f"API put.io : {len(created_at)} fichiers datés, {len(vus)} vus "
                  f"(partent dès {AGE_VU_JOURS} j).")
        return commande_releve(args.racine, args.travail, created_at, vus=vus)

    # purge : sans dates d'ajout, pas de revérification re-upload ⇒ refus (design D-E)
    if erreur:
        print(f"REFUS : {erreur}. La purge exige les dates d'ajout put.io pour revérifier "
              f"chaque fichier — rien n'est supprimé.", file=sys.stderr)
        return 1
    return commande_purge(args.racine, args.travail, args.preavis, created_at, force=args.force)


if __name__ == "__main__":
    sys.exit(main())
