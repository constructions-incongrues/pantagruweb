"""Tests de la logique pure de purge des zones communes put.io.

Fixtures réelles capturées le 2026-08-31 via le montage /mnt/remote/putio
(voir fixtures/). Les scénarios testés sont ceux de la spec
`purge-zones-communes` du change `purger-les-zones-communes-putio`
(dépôt secretariat).
"""

import unittest
from datetime import date
from pathlib import Path

import purge_zones_communes as pzc

FIXTURES = Path(__file__).parent / "fixtures"
RACINE_MONTAGE = "/mnt/remote/putio"


def charger_fixture_racine():
    """Noms des entrées à la racine du montage (dossiers et fichiers en vrac)."""
    entrees = []
    for ligne in (FIXTURES / "fixture-racine.tsv").read_text(encoding="utf-8").splitlines():
        type_, chemin = ligne.split("\t", 1)
        if chemin == RACINE_MONTAGE:
            continue
        entrees.append((type_, chemin[len(RACINE_MONTAGE) + 1 :]))
    return entrees


def charger_fixture_zones():
    """Listing (chemin relatif, taille) des fichiers des deux zones communes."""
    fichiers = []
    for ligne in (FIXTURES / "fixture-zones.tsv").read_text(encoding="utf-8").splitlines():
        taille, _mtime, chemin = ligne.split("\t", 2)
        fichiers.append((chemin[len(RACINE_MONTAGE) + 1 :], int(taille)))
    return fichiers


class TestFiltrageListeBlanche(unittest.TestCase):
    """Spec — Requirement : Liste blanche nominative, défaut protecteur."""

    def test_conserve_les_fichiers_des_zones_declarees(self):
        chemins = [c for c, _ in charger_fixture_zones()]
        retenus = pzc.filtrer_zones(chemins, zones=("chill.institute", "putflix"))
        self.assertEqual(sorted(retenus), sorted(chemins))

    def test_exclut_les_dossiers_non_declares(self):
        """Scénario : un dossier non déclaré est intouchable — noms réels de la racine."""
        chemins = [
            "Chez Tritri/un-film.mkv",
            "__Neeeeee/autre.mkv",
            "••Mange Lapin••/film à accents é.avi",
            "PANTAGRUWEB/Grisbis/Tristan/garde.mkv",
        ]
        self.assertEqual(pzc.filtrer_zones(chemins, zones=("chill.institute", "putflix")), [])

    def test_exclut_les_noms_approchants(self):
        """Scénario : la correspondance de nom est stricte (casse, suffixe, espace)."""
        chemins = [
            "Chill.Institute/film.mkv",
            "chill.institute2/film.mkv",
            "putflix /film.mkv",
            " putflix/film.mkv",
        ]
        self.assertEqual(pzc.filtrer_zones(chemins, zones=("chill.institute", "putflix")), [])

    def test_exclut_les_fichiers_en_vrac_a_la_racine(self):
        """Un fichier sans dossier n'appartient à aucune zone."""
        chemins = ["Last.Action.Hero.1993.MULTi.VF2.1080p.HDLight.AC3.5.1.H264-LiHDL.mkv"]
        self.assertEqual(pzc.filtrer_zones(chemins, zones=("chill.institute", "putflix")), [])

    def test_une_zone_declaree_sans_entree_est_signalee(self):
        """Scénario : une zone déclarée renommée sort du champ — l'écart est signalé."""
        chemins = ["chill.institute/film.mkv"]
        self.assertEqual(
            pzc.zones_absentes(chemins, zones=("chill.institute", "putflix")),
            ["putflix"],
        )


class TestAgeParObservation(unittest.TestCase):
    """Design D3 — l'âge est la date de première observation, jamais le mtime."""

    def test_un_nouveau_fichier_est_date_du_jour(self):
        etat, apparus, disparus = pzc.maj_observations(
            {}, ["chill.institute/Nouveau Film (2026)/film.mkv"], date(2026, 8, 31)
        )
        self.assertEqual(etat, {"chill.institute/Nouveau Film (2026)/film.mkv": "2026-08-31"})
        self.assertEqual(apparus, ["chill.institute/Nouveau Film (2026)/film.mkv"])
        self.assertEqual(disparus, [])

    def test_un_fichier_disparu_sort_de_l_etat(self):
        etat, apparus, disparus = pzc.maj_observations(
            {"putflix/parti.mkv": "2026-07-01", "putflix/reste.mkv": "2026-07-01"},
            ["putflix/reste.mkv"],
            date(2026, 8, 31),
        )
        self.assertEqual(etat, {"putflix/reste.mkv": "2026-07-01"})
        self.assertEqual(apparus, [])
        self.assertEqual(disparus, ["putflix/parti.mkv"])

    def test_une_observation_existante_garde_sa_date(self):
        etat, _, _ = pzc.maj_observations(
            {"putflix/deja-vu.mkv": "2026-07-01"}, ["putflix/deja-vu.mkv"], date(2026, 8, 31)
        )
        self.assertEqual(etat["putflix/deja-vu.mkv"], "2026-07-01")

    def test_etat_vide_rien_d_eligible(self):
        """Échec du côté sûr : état perdu = compteurs à zéro = aucune purge possible."""
        self.assertEqual(pzc.eligibles({}, date(2026, 8, 31)), [])

    def test_eligible_strictement_au_dela_de_l_age(self):
        """« Depuis plus de 30 jours » : 30 jours pile ne suffit pas."""
        etat = {
            "chill.institute/pile-30j.mkv": "2026-08-01",
            "chill.institute/31-jours.mkv": "2026-07-31",
        }
        self.assertEqual(
            pzc.eligibles(etat, date(2026, 8, 31), age_jours=30),
            ["chill.institute/31-jours.mkv"],
        )

    def test_le_mtime_n_entre_jamais_dans_l_age(self):
        """Un fichier au mtime très ancien, observé aujourd'hui, n'est pas éligible."""
        chemin_vieux_mtime, _ = charger_fixture_zones()[0]
        etat, _, _ = pzc.maj_observations({}, [chemin_vieux_mtime], date(2026, 8, 31))
        self.assertEqual(pzc.eligibles(etat, date(2026, 8, 31)), [])


class TestTripleConditionDePurge(unittest.TestCase):
    """Spec — aucune suppression sans préavis publié ; design D6."""

    def setUp(self):
        self.etat = {
            "chill.institute/vieux/film.mkv": "2026-07-01",
            "putflix/ancien.mkv": "2026-07-01",
        }
        self.preavis = pzc.construire_preavis(
            [("chill.institute/vieux/film.mkv", 100), ("putflix/ancien.mkv", 200)],
            date_emission=date(2026, 8, 31),
            delai_jours=14,
        )

    def test_le_preavis_porte_emission_et_date_de_purge(self):
        self.assertEqual(self.preavis["date_emission"], "2026-08-31")
        self.assertEqual(self.preavis["date_purge"], "2026-09-14")
        self.assertEqual(len(self.preavis["fichiers"]), 2)

    def test_purge_uniquement_les_fichiers_du_preavis(self):
        """Un fichier devenu éligible après le préavis attend le cycle suivant."""
        listing = [
            "chill.institute/vieux/film.mkv",
            "putflix/ancien.mkv",
            "chill.institute/eligible-depuis-hier.mkv",
        ]
        etat = dict(self.etat, **{"chill.institute/eligible-depuis-hier.mkv": "2026-07-02"})
        resultat = pzc.purgeables(self.preavis, listing, etat, date(2026, 9, 14))
        self.assertEqual(
            sorted(resultat), ["chill.institute/vieux/film.mkv", "putflix/ancien.mkv"]
        )

    def test_refus_avant_la_date_de_purge(self):
        with self.assertRaises(pzc.PreavisNonEchu):
            pzc.purgeables(
                self.preavis,
                ["chill.institute/vieux/film.mkv"],
                self.etat,
                date(2026, 9, 13),
            )

    def test_un_fichier_deplace_n_est_pas_purge(self):
        """Scénario : sauver = déplacer — le fichier absent du listing est épargné."""
        listing = ["putflix/ancien.mkv"]
        resultat = pzc.purgeables(self.preavis, listing, self.etat, date(2026, 9, 14))
        self.assertEqual(resultat, ["putflix/ancien.mkv"])

    def test_un_fichier_revenu_apres_le_preavis_n_est_pas_purge(self):
        """Même chemin, mais réobservé après l'émission : c'est un autre fichier."""
        etat_revenu = dict(self.etat, **{"chill.institute/vieux/film.mkv": "2026-09-05"})
        listing = ["chill.institute/vieux/film.mkv", "putflix/ancien.mkv"]
        resultat = pzc.purgeables(self.preavis, listing, etat_revenu, date(2026, 9, 14))
        self.assertEqual(resultat, ["putflix/ancien.mkv"])

    def test_une_zone_retiree_de_la_liste_est_protegee(self):
        """La triple condition revérifie l'appartenance aux zones déclarées."""
        listing = ["chill.institute/vieux/film.mkv", "putflix/ancien.mkv"]
        resultat = pzc.purgeables(
            self.preavis, listing, self.etat, date(2026, 9, 14), zones=("chill.institute",)
        )
        self.assertEqual(resultat, ["chill.institute/vieux/film.mkv"])


class TestReRemplissageEtOccupation(unittest.TestCase):
    """Règle 4 du design : le compte rendu publie le re-remplissage."""

    def test_re_remplissage_par_zone(self):
        apparus = [
            "chill.institute/nouveau1.mkv",
            "chill.institute/nouveau2.mkv",
            "putflix/nouveau.mkv",
        ]
        tailles = {
            "chill.institute/nouveau1.mkv": 1000,
            "chill.institute/nouveau2.mkv": 500,
            "putflix/nouveau.mkv": 200,
        }
        self.assertEqual(
            pzc.re_remplissage(apparus, tailles),
            {
                "chill.institute": {"fichiers": 2, "octets": 1500},
                "putflix": {"fichiers": 1, "octets": 200},
            },
        )

    def test_re_remplissage_zone_sans_nouveaute(self):
        """Une zone sans apparition figure à zéro — le silence chiffré, pas l'absence."""
        self.assertEqual(
            pzc.re_remplissage([], {}),
            {
                "chill.institute": {"fichiers": 0, "octets": 0},
                "putflix": {"fichiers": 0, "octets": 0},
            },
        )

    def test_occupation_depuis_du(self):
        """Parse la sortie réelle de `du -sh` (relevé du 2026-08-31)."""
        sortie = (
            "134G\t/mnt/remote/putio/chill.institute\n"
            "14G\t/mnt/remote/putio/putflix\n"
            "287G\t/mnt/remote/putio/Chez Tritri\n"
        )
        self.assertEqual(
            pzc.occupation_depuis_du(sortie),
            [
                ("chill.institute", "134G"),
                ("putflix", "14G"),
                ("Chez Tritri", "287G"),
            ],
        )


class TestGenerationDesTextes(unittest.TestCase):
    """Préavis et compte rendu : textes prêts à poster, noms inertes."""

    def test_le_preavis_texte_porte_dates_fichiers_et_geste(self):
        preavis = pzc.construire_preavis(
            [("chill.institute/Un Film (2026)/film.mkv", 1_500_000_000)],
            date_emission=date(2026, 8, 31),
            delai_jours=14,
        )
        texte = pzc.texte_preavis(preavis)
        self.assertIn("2026-09-14", texte)
        self.assertIn("chill.institute/Un Film (2026)/film.mkv", texte)
        self.assertIn("1,5 Go", texte)
        self.assertIn("déplacer", texte)
        self.assertIn("PANTAGRUWEB", texte)

    def test_les_noms_sont_inertes_dans_le_texte(self):
        """Un nom portant de la syntaxe est confiné dans un span de code inline.

        Rocket.Chat ne rend pas les clôtures à tildes ; la protection réelle
        est le code inline à backtick, dont le nom ne peut pas s'évader (ses
        propres backticks sont remplacés par des apostrophes).
        """
        preavis = pzc.construire_preavis(
            [("putflix/`echo pwned` **gras** [lien](x).mkv", 10)],
            date_emission=date(2026, 8, 31),
        )
        ligne = next(l for l in pzc.texte_preavis(preavis).split("\n") if "echo pwned" in l)
        self.assertTrue(ligne.startswith("- `"))
        self.assertEqual(ligne.split("  (")[0].count("`"), 2)  # un seul span, pas d'évasion
        self.assertNotIn("`echo pwned`", ligne)  # les backticks du nom sont neutralisés

    def test_compte_rendu_sans_effet(self):
        """Scénario : une purge sans effet rend compte aussi."""
        cr = pzc.construire_compte_rendu(
            supprimes=[],
            tailles={},
            sauves=[],
            re_rempl=pzc.re_remplissage([], {}),
            ecarts=[],
            date_execution=date(2026, 9, 14),
        )
        texte = pzc.texte_compte_rendu(cr)
        self.assertIn("aucun fichier", texte.lower())

    def test_compte_rendu_complet(self):
        cr = pzc.construire_compte_rendu(
            supprimes=["chill.institute/vieux.mkv"],
            tailles={"chill.institute/vieux.mkv": 2_000_000_000},
            sauves=["putflix/sauve.mkv"],
            re_rempl=pzc.re_remplissage(
                ["chill.institute/frais.mkv"], {"chill.institute/frais.mkv": 500_000_000}
            ),
            ecarts=["zone déclarée introuvable : putflix"],
            date_execution=date(2026, 9, 14),
        )
        self.assertEqual(cr["liberation_corbeille"], "2026-09-21")
        texte = pzc.texte_compte_rendu(cr)
        self.assertIn("chill.institute/vieux.mkv", texte)
        self.assertIn("2,0 Go", texte)
        self.assertIn("putflix/sauve.mkv", texte)
        self.assertIn("2026-09-21", texte)
        self.assertIn("zone déclarée introuvable : putflix", texte)
        self.assertIn("500,0 Mo", texte)


class TestListeDeControleCorbeille(unittest.TestCase):
    """Le vidage sélectif : liste de contrôle depuis le JSON de purge (D5)."""

    def test_noms_pour_corbeille_tries_et_uniques(self):
        cr = {
            "supprimes": [
                "chill.institute/Un Film (2026)/film.mkv",
                "chill.institute/Un Film (2026)/sous-titres.srt",
                "putflix/autre.mkv",
            ]
        }
        self.assertEqual(
            pzc.noms_pour_corbeille(cr),
            ["autre.mkv", "film.mkv", "sous-titres.srt"],
        )


class TestNeutralisationDesNomsHostiles(unittest.TestCase):
    """Audit /cso 2026-08-31 : noms = entrée non fiable (torrents, membres).

    Les noms ne doivent jamais être du markdown actif dans un message posté,
    ni porter de séquences de contrôle dans le terminal du mainteneur.
    """

    NOM_HOSTILE = "A\x1b[2K[cliquez](http://evil) @all `code` |x\nligne2"

    def test_assainir_retire_les_caracteres_de_controle(self):
        assaini = pzc.assainir(self.NOM_HOSTILE)
        self.assertNotIn("\x1b", assaini)   # ESC (séquence ANSI, finding #3)
        self.assertNotIn("\n", assaini)     # saut de ligne (casse tout)
        self.assertTrue(all(ord(c) >= 0x20 or c == " " for c in assaini))

    def test_le_preavis_neutralise_le_markdown_actif(self):
        """Finding #1 : un nom-lien ne doit pas rester un lien cliquable."""
        preavis = pzc.construire_preavis(
            [(f"chill.institute/{self.NOM_HOSTILE}.mkv", 10)], date(2026, 8, 31)
        )
        texte = pzc.texte_preavis(preavis)
        self.assertNotIn("\x1b", texte)             # séquence ANSI retirée
        ligne = next(l for l in texte.split("\n") if "cliquez" in l)
        self.assertTrue(ligne.startswith("- `"))    # confiné en code inline
        self.assertEqual(ligne.split("  (")[0].count("`"), 2)  # un seul span : lien et @all inertes
        self.assertNotIn("\n@all", texte)           # pas de @mention échappée en début de ligne

    def test_la_table_occupation_neutralise_le_pipe(self):
        """Variante : un nom de dossier avec | ne casse pas la cellule."""
        ligne = pzc.ligne_occupation("dossier|piégé", "42G")
        self.assertEqual(ligne.count("|"), 3)  # les 3 délimiteurs de cellule, pas un de plus
        self.assertIn("¦", ligne)              # le pipe du nom a été remplacé

    def test_le_dry_run_terminal_est_assaini(self):
        """Finding #3 : la liste imprimée au moment de décider ne cache rien."""
        for ligne in pzc.lignes_dry_run(["chill.institute/" + self.NOM_HOSTILE]):
            self.assertNotIn("\x1b", ligne)
            self.assertNotIn("\n", ligne.rstrip("\n"))


class TestScanDesZones(unittest.TestCase):
    """Le scan ne parcourt que les zones déclarées — jamais les dossiers personnels."""

    def test_scanner_ne_liste_que_les_zones(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            (racine / "chill.institute" / "Un Film").mkdir(parents=True)
            (racine / "chill.institute" / "Un Film" / "film.mkv").write_bytes(b"x" * 10)
            (racine / "Chez Tritri").mkdir()
            (racine / "Chez Tritri" / "prive.mkv").write_bytes(b"y" * 20)
            (racine / "en-vrac.mkv").write_bytes(b"z")

            listing = pzc.scanner_zones(racine, zones=("chill.institute", "putflix"))

            self.assertEqual(listing, [("chill.institute/Un Film/film.mkv", 10)])


if __name__ == "__main__":
    unittest.main()
