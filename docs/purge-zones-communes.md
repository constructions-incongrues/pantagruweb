# Purge des zones communes put.io

Procédure d'exploitation du script [`scripts/purge_zones_communes.py`](../scripts/purge_zones_communes.py).
Conception et règle complète : change `purger-les-zones-communes-putio` du dépôt
`secretariat` (pantagruweb.club).

## La règle

Les zones communes sont déclarées nommément : `chill.institute`, `putflix`.
Tout dossier non déclaré est réputé personnel et n'est **jamais** touché.
Dans une zone commune, un fichier observé depuis plus de **30 jours** est
supprimé, après un préavis publié **14 jours** avant (30 jours au premier
cycle). La corbeille put.io garde les fichiers **7 jours** après la purge,
puis est vidée — des seuls fichiers du cycle. Sauver un fichier = le
**déplacer** : chez soi pour le garder, dans `PANTAGRUWEB/` pour le préserver.

L'âge est la **date de première observation par le relevé** — jamais le mtime,
qui reflète souvent la date du contenu d'origine.

## Le cycle (manuel — rien ne tourne seul)

Sur `gabelle`, en tant que `pantagruweb`. L'état vit dans
`~/purge-zones-communes/` (`observations.json` ; sa perte est sans danger :
compteurs à zéro, rien d'éligible).

1. **Relevé** : `python3 purge_zones_communes.py releve`
   (premier cycle : ajouter `--inventaire-initial`).
   Produit `preavis-<date>.md` (à poster sur discutons), `preavis-<date>.json`
   (pour la purge) et `occupation-<date>.md`.
2. **Poster le préavis** sur discutons. Sans publication, pas de purge.
3. **À l'échéance** : `python3 purge_zones_communes.py purge --from ~/purge-zones-communes/preavis-<date>.json`.
   La commande refuse un préavis non échu, affiche son dry-run — **le lire en
   entier** — puis demande deux confirmations. Elle produit
   `compte-rendu-<date>.md` (à poster) et `purge-<date>.json`.
4. **Poster le compte rendu** sur discutons.
5. **À J+7** : `python3 purge_zones_communes.py corbeille --from ~/purge-zones-communes/purge-<date>.json`
   imprime la liste de contrôle, puis dans <https://app.put.io/trash> :
   - si la corbeille ne contient **que** ces fichiers : « Empty trash » est
     équivalent au tri ;
   - sinon : supprimer **uniquement** ces fichiers, un à un.
   Poster ensuite le complément de compte rendu (espace effectivement libéré).

## Interdits et replis

- **Jamais `rclone cleanup putio:`** — vide *toute* la corbeille, y compris
  les suppressions manuelles des membres. L'API v2 documentée n'expose pas la
  corbeille (vérifié le 2026-08-31) : le vidage est un geste web, guidé par la
  liste de contrôle.
- La liste des zones est une constante du script (`ZONES_COMMUNES`), à
  correspondance exacte — l'étendre est une décision du collectif, republiée
  sur discutons avant d'agir, jamais un réglage de confort.
- Tout changement de paramètre (`AGE_JOURS`, `PREAVIS_JOURS`,
  `CORBEILLE_JOURS`) est republié avant de prendre effet.

## Déduplication d'œuvre

Le même film existe souvent en plusieurs encodages (x265 vs x264, 1080p vs
720p), ou traîne encore en zone commune alors qu'une version est déjà
préservée. `deduplication_oeuvres.py` les repère et prépare un arbitrage —
mais **ne supprime jamais seul** : un humain désigne l'exemplaire à garder.

Films seulement : les séries (SxxExx, saison, coffret) et les noms sans
année sont écartés comme « incertains », jamais purgés.

1. **Relevé** : `python3 deduplication_oeuvres.py releve`
   Produit `doublons-<date>.txt` (éditable) et `.json`. Chaque groupe montre
   les encodages classés (résolution, codec) et un champ `garder:` pré-rempli.
2. **Arbitrer** : éditer le champ `garder:` de chaque groupe — un numéro pour
   conserver cet encodage, ou `préservé` pour garder la version déjà en
   sécurité. La proposition pré-remplie peut être renversée.
3. **Préavis** : `python3 deduplication_oeuvres.py preavis --from doublons-<date>.txt`
   Valide les choix (`valider_cibles` refuse toute cible hors zone commune,
   même un `..`), liste les fichiers des encodages écartés, et produit un
   préavis au format de la purge des zones communes.
4. **Publier puis purger** : poster le préavis sur discutons, et à échéance
   `python3 purge_zones_communes.py purge --from preavis-doublons-<date>.json`.
   La suppression emprunte le régime préavis + corbeille ci-dessus — une seule
   porte destructive.

**Prérequis** : lancer d'abord `purge_zones_communes.py releve` (au moins une
fois), pour que les fichiers à purger soient dans l'état d'observation ; un
fichier non observé est sauté par la purge (côté sûr), pas supprimé.

## Tests

```bash
cd scripts && python3 -m unittest test_purge_zones_communes test_deduplication_oeuvres
```

Fixtures réelles dans `scripts/fixtures/` (listings du 2026-08-31).
