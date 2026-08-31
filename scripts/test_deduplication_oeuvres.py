"""Tests de la détection de doublons d'œuvre sur put.io.

Fixtures réelles capturées le 2026-08-31 (voir fixtures/noms-*.txt). Les
scénarios testés sont ceux de la spec `deduplication-oeuvres` du change
`purger-les-doublons-d-oeuvre-putio` (dépôt secretariat).
"""

import unittest
from pathlib import Path

import deduplication_oeuvres as dedup

FIXTURES = Path(__file__).parent / "fixtures"


def noms(fichier):
    lignes = (FIXTURES / fichier).read_text(encoding="utf-8").splitlines()
    return [l for l in lignes if l and not l.startswith("#")]


class TestParsingCleOeuvre(unittest.TestCase):
    """Spec — Appariement par titre et année ; design D2."""

    def test_film_classique_donne_titre_et_annee(self):
        self.assertEqual(
            dedup.cle_oeuvre("Wake in Fright 1971 1080p BluRay x264-nikt0"),
            ("wake in fright", "1971"),
        )

    def test_titre_avec_annee_entre_parentheses(self):
        self.assertEqual(
            dedup.cle_oeuvre("The Kids (2021) [1080p] [WEBRip] [YTS.MX]"),
            ("the kids", "2021"),
        )

    def test_titre_a_points_normalise(self):
        self.assertEqual(
            dedup.cle_oeuvre("Boundless.2024.MULTi.1080p.WEB.x264-FW.mkv"),
            ("boundless", "2024"),
        )

    def test_accents_translitteres(self):
        self.assertEqual(
            dedup.cle_oeuvre("Le.Gendarme.De.Saint-Tropez.1964.2160p.4K.BluRay.x265.mkv"),
            ("le gendarme de saint tropez", "1964"),
        )

    def test_sans_annee_est_incertain(self):
        self.assertIsNone(dedup.cle_oeuvre("Un Film Sans Annee 1080p BluRay.mkv"))

    def test_titre_vide_est_incertain(self):
        self.assertIsNone(dedup.cle_oeuvre("1971 1080p BluRay.mkv"))


class TestExclusionDesSeries(unittest.TestCase):
    """Spec — les correspondances incertaines sont exclues ; design D1."""

    def test_episode_sxxexx_exclu(self):
        for nom in [
            "Futurama.S14E01.1080p.HEVC.x265-MeGusta[EZTVx.to].mkv",
            "President.Curtis.S01E02.1080p.WEB.h264-EDITH[EZTVx.to].mkv",
        ]:
            self.assertIsNone(dedup.cle_oeuvre(nom), nom)

    def test_serie_avec_annee_reste_exclue(self):
        """« Silo 2023 S03E03 » a une année, mais le marqueur série prime."""
        self.assertIsNone(dedup.cle_oeuvre("Silo 2023 S03E03 720p WEB H264-JFF[EZTVx.to].mkv"))

    def test_saison_complete_exclue(self):
        self.assertIsNone(dedup.cle_oeuvre("Kaiju.No.8.S02.MULTi.1080p.BluRay.x265-KAF"))

    def test_coffret_ou_integrale_exclu(self):
        self.assertIsNone(dedup.cle_oeuvre("Kubrick Intégrale 1080p Collection"))

    def test_toutes_les_series_de_la_fixture_sont_ecartees(self):
        """Aucun nom portant SxxExx/Sxx ne doit produire une clé."""
        import re
        marqueur = re.compile(r"S\d{2}(E\d{2})?", re.I)
        for nom in noms("noms-zones-communes.txt"):
            if marqueur.search(nom):
                self.assertIsNone(dedup.cle_oeuvre(nom), f"série non écartée : {nom}")


class TestAppariement(unittest.TestCase):
    """Spec — même (titre, année) ⇒ groupe ; homonymes d'années ≠ ⇒ pas de groupe."""

    def test_deux_encodages_meme_oeuvre_apparies(self):
        groupes = dedup.grouper(
            [
                "chill.institute/The Kids (2021) [1080p] [WEBRip] [YTS.MX]",
                "chill.institute/The Kids (2021) [720p] [WEBRip] [YTS.MX]",
            ]
        )
        self.assertEqual(len(groupes), 1)
        self.assertEqual(len(groupes[("the kids", "2021")]), 2)

    def test_homonymes_annees_differentes_non_apparies(self):
        groupes = dedup.grouper(
            [
                "chill.institute/Wake in Fright 1971 1080p x264.mkv",
                "chill.institute/Wake in Fright 2010 1080p x264.mkv",
            ]
        )
        self.assertEqual(groupes, {})  # aucune paire : deux œuvres distinctes

    def test_fichier_seul_ne_forme_pas_de_groupe(self):
        groupes = dedup.grouper(["chill.institute/Solo Movie 2020 1080p.mkv"])
        self.assertEqual(groupes, {})

    def test_incertain_ignore_dans_le_groupement(self):
        groupes = dedup.grouper(
            [
                "chill.institute/Silo 2023 S03E03 720p.mkv",
                "chill.institute/Silo 2023 S03E03 1080p.mkv",
            ]
        )
        self.assertEqual(groupes, {})  # séries écartées, pas de doublon d'œuvre


class TestDeuxFronts(unittest.TestCase):
    """Spec — comparaison sur deux fronts ; la préservation jamais en cible."""

    def test_doublon_interne_aux_zones_communes(self):
        zc = [c for c in noms("noms-zones-communes.txt")]
        zc = ["chill.institute/" + n for n in zc]
        internes = dedup.doublons_internes(zc)
        cles = {k for k in internes}
        self.assertIn(("the kids", "2021"), cles)

    def test_croisement_avec_preservation(self):
        """Wake in Fright x264 (zone commune) redondant avec la version préservée."""
        zc = ["chill.institute/Wake in Fright 1971 1080p BluRay x264-nikt0"]
        preserv = noms("noms-preservation.txt")
        redondants = dedup.redondants_avec_preservation(zc, preserv)
        self.assertEqual(len(redondants), 1)
        self.assertEqual(redondants[0]["cible"], zc[0])
        self.assertIn("Masters of Cinema", redondants[0]["deja_preserve"])

    def test_preservation_jamais_en_cible(self):
        """Un fichier de préservation n'est jamais proposé à la suppression."""
        zc = ["chill.institute/Wake in Fright 1971 1080p BluRay x264-nikt0"]
        preserv = noms("noms-preservation.txt")
        for r in dedup.redondants_avec_preservation(zc, preserv):
            self.assertTrue(r["cible"].startswith("chill.institute/"))
            self.assertNotIn("PANTAGRUWEB", r["cible"])


class TestClassement(unittest.TestCase):
    """Spec — la proposition est argumentée, jamais opaque ; design D4."""

    def test_resolution_prime(self):
        classe = dedup.classer(
            [
                "The Kids (2021) [720p] [WEBRip] [YTS.MX]",
                "The Kids (2021) [1080p] [WEBRip] [YTS.MX]",
            ]
        )
        self.assertIn("1080p", classe[0]["nom"])  # le meilleur en tête
        self.assertIn("720p", classe[-1]["nom"])

    def test_codec_departage_a_resolution_egale(self):
        classe = dedup.classer(
            [
                "Film 2020 1080p BluRay x264-GRP",
                "Film 2020 1080p BluRay x265-GRP",
            ]
        )
        self.assertIn("x265", classe[0]["nom"])  # HEVC préféré à qualité égale

    def test_chaque_encodage_montre_ses_caracteristiques(self):
        classe = dedup.classer(["Wake in Fright 1971 1080p BluRay x264-nikt0"])
        e = classe[0]
        self.assertEqual(e["resolution"], "1080p")
        self.assertEqual(e["codec"], "x264")
        self.assertIn("nom", e)  # le nom reste visible pour l'arbitrage humain

    def test_le_classement_propose_ne_decide_pas(self):
        """La sortie est un ordre proposé + une raison, pas une suppression."""
        classe = dedup.classer(["A 2020 2160p x265", "B 2020 1080p x264"])
        self.assertTrue(all("garder" not in e and "supprimer" not in e for e in classe))
        self.assertEqual(classe[0]["resolution"], "2160p")


class TestArbitrage(unittest.TestCase):
    """Spec — aucune suppression sans choix humain ; cibles en zone commune seule."""

    KIDS = [
        "chill.institute/The Kids (2021) [1080p] [WEBRip] [YTS.MX]",
        "chill.institute/The Kids (2021) [720p] [WEBRip] [YTS.MX]",
    ]
    WAKE_ZC = ["chill.institute/Wake in Fright 1971 1080p BluRay x264-nikt0"]
    WAKE_PRESERV = ["Wake in Fright (1971) Masters of Cinema (1080p BluRay x265 10bit r00t)"]

    def test_groupes_melent_interne_et_croisement(self):
        groupes = dedup.groupes_a_arbitrer(self.KIDS + self.WAKE_ZC, self.WAKE_PRESERV)
        types = {g["cle"]: g["type"] for g in groupes}
        self.assertEqual(types[("the kids", "2021")], "interne")
        self.assertEqual(types[("wake in fright", "1971")], "préservé")

    def test_lire_choix_parse_index_et_preserve(self):
        texte = "## x\ngarder: 1\n## y\ngarder: préservé\n"
        self.assertEqual(dedup.lire_choix(texte), ["1", "préservé"])

    def test_rien_a_purger_sans_choix(self):
        """Aucun choix enregistré ⇒ aucune cible (spec)."""
        groupes = dedup.groupes_a_arbitrer(self.KIDS, [])
        self.assertEqual(dedup.chemins_a_purger(groupes, [None]), [])

    def test_interne_garde_un_purge_les_autres(self):
        groupes = dedup.groupes_a_arbitrer(self.KIDS, [])
        # groupe unique ; garder l'index 1 (le mieux classé, 1080p)
        cibles = dedup.chemins_a_purger(groupes, ["1"])
        self.assertEqual(cibles, ["chill.institute/The Kids (2021) [720p] [WEBRip] [YTS.MX]"])

    def test_preserve_purge_la_copie_zone_commune(self):
        groupes = dedup.groupes_a_arbitrer(self.WAKE_ZC, self.WAKE_PRESERV)
        cibles = dedup.chemins_a_purger(groupes, ["préservé"])
        self.assertEqual(cibles, self.WAKE_ZC)

    def test_une_cible_hors_zone_commune_est_refusee(self):
        groupes = dedup.groupes_a_arbitrer(self.WAKE_ZC, self.WAKE_PRESERV)
        for cible in dedup.chemins_a_purger(groupes, ["préservé"]):
            self.assertTrue(cible.startswith(("chill.institute/", "putflix/")))
            self.assertNotIn("PANTAGRUWEB", cible)


class TestValiderCibles(unittest.TestCase):
    """Défense en profondeur : refuser une cible hors zone commune même falsifiée."""

    def test_cibles_zone_commune_acceptees(self):
        cibles = ["chill.institute/x", "putflix/y"]
        self.assertEqual(dedup.valider_cibles(cibles), cibles)

    def test_cible_preservation_refusee(self):
        with self.assertRaises(ValueError):
            dedup.valider_cibles(["PANTAGRUWEB/Patrimoine/Ted Kotcheff/x"])

    def test_cible_dossier_personnel_refusee(self):
        with self.assertRaises(ValueError):
            dedup.valider_cibles(["Chez Tritri/film.mkv"])


class TestRoundTripPropositions(unittest.TestCase):
    """Le fichier généré, réédité, redonne des cibles cohérentes (money path)."""

    def test_propositions_generees_relues_donnent_les_bonnes_cibles(self):
        from datetime import date

        zc = [
            "chill.institute/The Kids (2021) [1080p] [WEBRip] [YTS.MX]",
            "chill.institute/The Kids (2021) [720p] [WEBRip] [YTS.MX]",
            "chill.institute/Wake in Fright 1971 1080p BluRay x264-nikt0",
        ]
        preserv = ["Wake in Fright (1971) Masters of Cinema (1080p BluRay x265 10bit r00t)"]
        texte, structure = dedup.construire_propositions(zc, preserv, date(2026, 8, 31))

        # Le texte pré-remplit une proposition par groupe et reste lisible.
        self.assertIn("garder:", texte)
        self.assertIn("The Kids", texte)
        self.assertIn("déjà en sécurité", texte)  # le groupe préservé nomme la version sûre

        # Relu tel quel (choix pré-remplis acceptés), il purge le 720p et la copie zc de Wake.
        choix = dedup.lire_choix(texte)
        cibles = dedup.chemins_a_purger(structure["groupes"], choix)
        self.assertIn("chill.institute/The Kids (2021) [720p] [WEBRip] [YTS.MX]", cibles)
        self.assertIn("chill.institute/Wake in Fright 1971 1080p BluRay x264-nikt0", cibles)
        self.assertNotIn("chill.institute/The Kids (2021) [1080p] [WEBRip] [YTS.MX]", cibles)
        for c in cibles:
            self.assertTrue(c.startswith(("chill.institute/", "putflix/")))


if __name__ == "__main__":
    unittest.main()
