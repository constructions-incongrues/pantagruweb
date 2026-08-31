# Purge des zones communes put.io

Procédure d'exploitation du script [`scripts/purge_zones_communes.py`](../scripts/purge_zones_communes.py).
Conception et règle complète : change `purger-les-zones-communes-putio` du dépôt
`secretariat` (pantagruweb.club).

## La règle

Les zones communes sont déclarées nommément : `chill.institute`, `putflix`.
Tout dossier non déclaré est réputé personnel et n'est **jamais** touché.
Dans une zone commune, un fichier est supprimé quand il est **présent depuis
plus de 14 jours**, ou dès **7 jours s'il a déjà été visionné** (voir la
section « Visionnage » ci-dessous). Un préavis est publié **7 jours** avant.
La corbeille put.io garde les fichiers **7 jours** après la purge, puis est
vidée — des seuls fichiers du cycle. Sauver un fichier = le **déplacer** :
chez soi pour le garder, dans `PANTAGRUWEB/` pour le préserver.

*Seuils resserrés le 2026-08-31 (change `purger-selon-le-visionnage-putio`) :
seuil de base 30→14 j, préavis 14→7 j, seuil du visionné = 7 j. Délai total
avant suppression : 14 j pour un fichier vu, 21 j pour un non-vu.*

L'âge est la **date d'ajout à put.io** (`created_at`, lue par l'API) — jamais le
mtime, qui reflète souvent la date du contenu d'origine, et **plus** une
observation accumulée. *Change `baser-l-age-de-purge-sur-created-at`, 2026-08-31 :
le relevé est désormais sans état — il lit l'âge réel par l'API à chaque cycle,
au lieu de le compter depuis sa première observation. Conséquence : la purge
dépend entièrement de l'API pour l'âge ; API injoignable = cycle sauté, aucun
repli.*

## Déploiement des scripts (préalable)

Les scripts ne sont **pas** copiés à la main : ils sont déployés par le
**Komodo Repo `pantagruweb-main`**, qui clone ce dépôt sur `gabelle` dans
`/etc/komodo/repos/pantagruweb-main/`. Un lien de confort y mène :
`~/scripts-purge -> /etc/komodo/repos/pantagruweb-main/scripts` (posé une fois,
il suit les pulls).

**Avant tout cycle, si le code a changé : déclencher un `pull` du Repo depuis
l'UI Komodo.** Sinon tu exécutes une version périmée. Le `pull` est la première
étape, non négociable — aucun contrôle ne le vérifie, c'est à toi de le faire.

Les commandes ci-dessous se lancent depuis le clone, en `pantagruweb` :

```bash
cd ~/scripts-purge
```

## Le cycle (manuel — rien ne tourne seul)

Sur `gabelle`, en tant que `pantagruweb`, depuis `~/scripts-purge` (le clone
Komodo). **Le relevé est sans état** : il ne tient plus aucun fichier
d'observation, il lit l'âge (dates d'ajout) et le visionnage par l'API à chaque
cycle. Seuls les préavis et comptes rendus vivent dans `~/purge-zones-communes/`
— de la sortie, pas de l'état à préserver, et hors du clone : ils survivent aux
pulls.

1. **Relevé** : `python3 purge_zones_communes.py releve`
   Lit l'API (dates d'ajout + visionnage) et le montage (tailles, occupation).
   Produit `preavis-<date>.md` (à poster sur discutons), `preavis-<date>.json`
   (pour la purge) et `occupation-<date>.md`. **API injoignable = préavis vide,
   cycle sauté** (aucun repli — c'est la décision du remplacement franc).
2. **Poster le préavis** sur discutons. Sans publication, pas de purge.
3. **À l'échéance** : `python3 purge_zones_communes.py purge --from ~/purge-zones-communes/preavis-<date>.json`.
   La commande refuse un préavis non échu, **relit les dates d'ajout par l'API**
   (protection re-upload : un fichier ré-ajouté au même chemin après l'émission
   est épargné ; API injoignable = purge refusée), affiche son dry-run — **le
   lire en entier** — puis demande deux confirmations. Elle produit
   `compte-rendu-<date>.md` (à poster) et `purge-<date>.json`.
4. **Poster le compte rendu** sur discutons.
5. **À J+7** : `python3 purge_zones_communes.py corbeille --from ~/purge-zones-communes/purge-<date>.json`
   imprime la liste de contrôle, puis dans <https://app.put.io/trash> :
   - si la corbeille ne contient **que** ces fichiers : « Empty trash » est
     équivalent au tri ;
   - sinon : supprimer **uniquement** ces fichiers, un à un.
   Poster ensuite le complément de compte rendu (espace effectivement libéré).

## Forcer avant l'échéance (décision du mainteneur)

La purge refuse par défaut de s'exécuter avant la date d'échéance du préavis —
c'est la garde qui donne aux membres 7 jours pour déplacer ce qu'ils veulent
garder. Le mainteneur peut passer outre avec `--force` :

```bash
python3 purge_zones_communes.py purge --from ~/purge-zones-communes/preavis-<date>.json --force
```

`--force` saute **le seul** contrôle d'échéance. Tout le reste tient : liste
blanche, revérification `created_at`, présence en zone, et surtout la
**corbeille**. Le forçage exige une **double confirmation** : d'abord taper
`purger sans preavis echu` (qui nomme ce qu'on abandonne), puis la confirmation
finale `purger N fichiers`. Une phrase erronée annule tout, sans rien supprimer.

**Ce que ça coûte, et le seul recours qui reste.** Forcer, c'est supprimer sans
que les membres aient eu le préavis complet. Leur recours se déplace de
« déplacer avant » à « récupérer après » : les fichiers restent en corbeille
7 jours, et le compte-rendu le dit noir sur blanc. **Ce recours n'existe que si
tu postes le compte-rendu** — sinon personne ne sait qu'il faut aller voir la
corbeille. Poster le compte-rendu d'une purge forcée n'est pas optionnel.

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

La purge des doublons emprunte la même porte que la purge par âge : elle relit
les dates d'ajout par l'API et n'exécute que les fichiers dont `created_at` est
antérieur à l'émission du préavis. Un encodage à écarter, ancien, passe ; un
fichier ré-ajouté au même chemin depuis l'émission est épargné. (Plus de
prérequis d'« état d'observation » : le relevé est sans état depuis le change
`baser-l-age-de-purge-sur-created-at`.)

## Visionnage : le vu part plus tôt

Un fichier déjà **consommé** (streamé/ouvert) n'attend plus personne : il
devient éligible dès **7 jours** au lieu de 14. Le statut vient de l'API
put.io (`first_accessed_at`), lu par `statut_visionnage.py` — **le seul
module qui détient le jeton OAuth**, en lecture seule. Depuis le change
`baser-l-age-de-purge-sur-created-at`, ce module porte aussi les **dates
d'ajout** (`created_at`, la source d'âge), et il est appelé par le `releve`
**comme par la `purge`** (qui relit `created_at` pour sa protection re-upload).

- Le `releve` normal interroge l'API automatiquement : il affiche
  « Visionnage : N fichiers vus » et marque chaque fichier concerné du
  préavis d'un « · vu, part plus tôt » (sans nommer qui a regardé — le
  compte put.io est partagé).
- **`first_accessed_at` = premier accès** (streaming, ouverture), y compris
  les annexes d'un film streamé ; `null` = jamais ouvert (garde le seuil de
  14 j).
- **Si l'API est injoignable, le cycle est sauté** : sans dates d'ajout, le
  relevé rend un préavis vide et la purge refuse. Il n'y a **plus de repli**
  (l'ancienne horloge d'observation et le drapeau `--sans-visionnage` ont
  disparu) — c'est le prix assumé du remplacement franc : la purge s'appuie
  désormais entièrement sur l'API pour l'âge.

Le jeton n'apparaît jamais dans un message, un préavis ou un fichier de
travail (garde testée).

## Tests

```bash
cd scripts && python3 -m unittest test_purge_zones_communes test_deduplication_oeuvres test_statut_visionnage
```

Fixtures réelles dans `scripts/fixtures/` (listings du 2026-08-31).
