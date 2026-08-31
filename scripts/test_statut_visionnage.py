"""Tests du lecteur de statut de visionnage (API put.io) — logique isolée.

Change `purger-selon-le-visionnage-putio`. Le module touche seul au jeton et
au réseau ; ces tests couvrent sa logique pure (reconstruction des chemins,
ensemble des vus) et ses gardes (non-fuite du jeton, repli côté sûr), sans
réseau. L'accès API réel est vérifié à part sur gabelle (tâche 3.1).
"""

import json
import unittest
from pathlib import Path

import statut_visionnage as sv

FIXTURES = Path(__file__).parent / "fixtures"


def _index_depuis_fixture():
    """Construit un mock `get(parent_id) -> [fichiers]` depuis la fixture API."""
    data = json.loads((FIXTURES / "api-files-list.json").read_text(encoding="utf-8"))
    index = {data["chill_id"]: []}
    for f in data["niveau1"]:
        index[data["chill_id"]].append({k: f.get(k) for k in ("id", "name", "file_type", "first_accessed_at")})
        if "enfants" in f:
            index[f["id"]] = f["enfants"]
    return data["chill_id"], (lambda pid: index.get(pid, []))


class TestReconstructionChemins(unittest.TestCase):
    """Tâche 1.2 — le chemin reconstruit a la même forme que scanner_zones."""

    def test_chemins_relatifs_prefixes_par_la_zone(self):
        chill_id, get = _index_depuis_fixture()
        mapping = sv.mapping_visionnage(get, {"chill.institute": chill_id})
        self.assertTrue(mapping, "la fixture doit produire des fichiers")
        for chemin in mapping:
            self.assertTrue(chemin.startswith("chill.institute/"))
            self.assertNotIn("//", chemin)


class TestEnsembleVus(unittest.TestCase):
    """Tâche 1.3 — un first_accessed_at non nul entre dans `vus`, un null non."""

    def test_seuls_les_dates_non_nulles_comptent(self):
        mapping = {
            "chill.institute/vu.mkv": "2026-08-20T10:00:00",
            "chill.institute/jamais.mkv": None,
        }
        self.assertEqual(sv.ensemble_vus(mapping), {"chill.institute/vu.mkv"})

    def test_sur_la_fixture_reelle(self):
        chill_id, get = _index_depuis_fixture()
        mapping = sv.mapping_visionnage(get, {"chill.institute": chill_id})
        vus = sv.ensemble_vus(mapping)
        self.assertTrue(all(mapping[c] for c in vus))  # tout vu a une date


class TestReplitEtNonFuite(unittest.TestCase):
    """Tâches 1.4 / 1.5 — échec côté sûr, le jeton ne fuit jamais."""

    def test_erreur_donne_vus_vide_sans_exception(self):
        def producteur_qui_leve():
            raise RuntimeError("boom réseau")
        vus, erreur = sv.statut_sur(producteur_qui_leve)
        self.assertEqual(vus, set())
        self.assertIsNotNone(erreur)

    def test_le_jeton_ne_fuit_pas_dans_le_message(self):
        JETON = "SECRET-oauth-abc123"
        def producteur_qui_leve():
            raise RuntimeError(f"échec avec le jeton {JETON}")
        _, erreur = sv.statut_sur(producteur_qui_leve)
        self.assertNotIn(JETON, erreur)  # seul le type d'erreur remonte, jamais son message

    def test_succes_donne_vus_et_pas_d_erreur(self):
        vus, erreur = sv.statut_sur(lambda: {"chill.institute/vu.mkv": "2026-08-20"})
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
