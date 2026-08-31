"""Tests du lecteur put.io (API) — logique isolée.

Changes `purger-selon-le-visionnage-putio` puis `baser-l-age-de-purge-sur-created-at`.
Le module touche seul au jeton et au réseau ; ces tests couvrent sa logique pure
(reconstruction des chemins, dates d'ajout, ensemble des vus) et ses gardes
(non-fuite du jeton, repli côté sûr), sans réseau. L'accès API réel est vérifié
à part sur gabelle.
"""

import json
import unittest
from pathlib import Path

import statut_visionnage as sv

FIXTURES = Path(__file__).parent / "fixtures"


def _index_depuis_fixture():
    """Construit un mock `get(parent_id) -> [fichiers]` depuis la fixture API."""
    data = json.loads((FIXTURES / "api-files-list.json").read_text(encoding="utf-8"))
    champs = ("id", "name", "file_type", "first_accessed_at", "created_at")
    index = {data["chill_id"]: []}
    for f in data["niveau1"]:
        index[data["chill_id"]].append({k: f.get(k) for k in champs})
        if "enfants" in f:
            index[f["id"]] = f["enfants"]
    return data["chill_id"], (lambda pid: index.get(pid, []))


class TestReconstructionChemins(unittest.TestCase):
    """Le chemin reconstruit a la même forme que scanner_zones."""

    def test_chemins_relatifs_prefixes_par_la_zone(self):
        chill_id, get = _index_depuis_fixture()
        mapping = sv.mapping_fichiers(get, {"chill.institute": chill_id})
        self.assertTrue(mapping, "la fixture doit produire des fichiers")
        for chemin in mapping:
            self.assertTrue(chemin.startswith("chill.institute/"))
            self.assertNotIn("//", chemin)


class TestDatesCreation(unittest.TestCase):
    """`baser-l-age-de-purge-sur-created-at` — la date d'ajout, en date seule."""

    def test_created_at_ramene_a_la_date_seule(self):
        mapping = {
            "chill.institute/a.mkv": {"first_accessed_at": None, "created_at": "2026-08-14"},
            "chill.institute/b.mkv": {"first_accessed_at": None, "created_at": None},
        }
        self.assertEqual(sv.dates_creation(mapping), {"chill.institute/a.mkv": "2026-08-14"})

    def test_created_at_malforme_est_ecarte(self):
        """Validation à la frontière : une date d'ajout illisible (API douteuse)
        est écartée, jamais propagée à un `date.fromisoformat` qui planterait."""
        mapping = {
            "chill.institute/ok.mkv": {"first_accessed_at": None, "created_at": "2026-08-14"},
            "chill.institute/pourri.mkv": {"first_accessed_at": None, "created_at": "pas-date"},
            "chill.institute/vide.mkv": {"first_accessed_at": None, "created_at": ""},
        }
        self.assertEqual(sv.dates_creation(mapping), {"chill.institute/ok.mkv": "2026-08-14"})

    def test_sur_la_fixture_dates_seules_et_connues(self):
        chill_id, get = _index_depuis_fixture()
        dates = sv.dates_creation(sv.mapping_fichiers(get, {"chill.institute": chill_id}))
        self.assertTrue(dates, "des fichiers doivent porter une date d'ajout")
        for valeur in dates.values():
            self.assertRegex(valeur, r"^\d{4}-\d{2}-\d{2}$")  # date seule, pas d'heure
        # un fichier de niveau 1 et un fichier imbriqué, dates connues de la fixture
        self.assertEqual(
            dates["chill.institute/The.Simpsons.S37E12.The.Fall.Guy.Yi.Yi.720p.HDTV.DD5.1.x264-Slurpuff.mkv"],
            "2026-08-30",
        )
        self.assertEqual(
            dates["chill.institute/Wheel Of Time (2003) [720p] [BluRay] [YTS.MX]/"
                  "Wheel.Of.Time.2003.720p.BluRay.x264.AAC-[YTS.MX].mp4"],
            "2026-08-30",
        )


class TestEnsembleVus(unittest.TestCase):
    """Un first_accessed_at non nul entre dans `vus`, un null non."""

    def test_seuls_les_dates_non_nulles_comptent(self):
        mapping = {
            "chill.institute/vu.mkv": {"first_accessed_at": "2026-08-20T10:00:00", "created_at": "2026-08-14"},
            "chill.institute/jamais.mkv": {"first_accessed_at": None, "created_at": "2026-08-14"},
        }
        self.assertEqual(sv.ensemble_vus(mapping), {"chill.institute/vu.mkv"})

    def test_sur_la_fixture_reelle(self):
        chill_id, get = _index_depuis_fixture()
        mapping = sv.mapping_fichiers(get, {"chill.institute": chill_id})
        vus = sv.ensemble_vus(mapping)
        self.assertTrue(all(mapping[c]["first_accessed_at"] for c in vus))


class TestCollecteEtRepli(unittest.TestCase):
    """Échec côté sûr, le jeton ne fuit jamais — contrat (created_at, vus, erreur)."""

    def test_collecte_donne_dates_et_vus(self):
        chill_id, get = _index_depuis_fixture()
        created_at, vus = sv.collecte(get, {"chill.institute": chill_id})
        self.assertTrue(created_at and vus)
        self.assertTrue(all(c in created_at for c in vus))  # tout vu est daté

    def test_erreur_donne_vide_sans_exception(self):
        def producteur_qui_leve():
            raise RuntimeError("boom réseau")
        created_at, vus, erreur = sv._sur(producteur_qui_leve)
        self.assertEqual((created_at, vus), ({}, set()))
        self.assertIsNotNone(erreur)

    def test_le_jeton_ne_fuit_pas_dans_le_message(self):
        JETON = "SECRET-oauth-abc123"
        def producteur_qui_leve():
            raise RuntimeError(f"échec avec le jeton {JETON}")
        _, _, erreur = sv._sur(producteur_qui_leve)
        self.assertNotIn(JETON, erreur)  # seul le type d'erreur remonte, jamais son message

    def test_succes_donne_le_triple_sans_erreur(self):
        created_at, vus, erreur = sv._sur(
            lambda: ({"chill.institute/vu.mkv": "2026-08-20"}, {"chill.institute/vu.mkv"})
        )
        self.assertEqual(created_at, {"chill.institute/vu.mkv": "2026-08-20"})
        self.assertEqual(vus, {"chill.institute/vu.mkv"})
        self.assertIsNone(erreur)


class TestLireJeton(unittest.TestCase):
    """Le jeton se lit depuis rclone.conf ; un fichier absent lève proprement."""

    def test_lit_le_token_depuis_une_conf(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False, encoding="utf-8") as f:
            f.write('[putio]\ntype = putio\ntoken = {"access_token":"abc","token_type":"bearer"}\n')
            chemin = f.name
        try:
            self.assertEqual(sv.lire_jeton(chemin), "abc")
        finally:
            os.unlink(chemin)


if __name__ == "__main__":
    unittest.main()
