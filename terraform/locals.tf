locals {
  # Valeurs communes pour les enregistrements DNS
  default_ttl     = 300
  default_proxied = false
  zone_id         = data.cloudflare_zone.main.id

  # Configuration des enregistrements CNAME pointant vers gabelle
  #
  # `archive` a ete retire de cette boucle le 2026-08-30, et ce retrait DECRIT
  # la realite plutot qu'il ne la change : archive.pantagruweb.club existe
  # comme enregistrement A (-> 91.99.119.85), pas comme CNAME, et n'a jamais
  # figure dans l'etat Terraform. Le declarer ici faisait planifier la creation
  # d'un CNAME en conflit avec un A existant, ce que Cloudflare refuse : tout
  # plan echouait sur cette seule ligne, depuis le commit 72ae0be du
  # 2025-11-09 qui a consolide ces enregistrements en boucle.
  #
  # Le nom sert Plex (conteneur plex_video, route par Traefik sur gabelle).
  # Le convertir en CNAME comme ses voisins serait coherent, mais c'est une
  # modification DNS sur un service en usage : elle merite sa propre decision,
  # pas un effet de bord.
  # `ytdl` a ete retire le 2026-08-30, apres la decision D8 de ne plus router
  # ytdl-server publiquement. Le nom resolvait toujours vers gabelle, qui
  # repondait 404 faute de route Traefik : un enregistrement DNS valide devant
  # un service qui n'ecoute pas est un piege pour celui qui diagnostique — il
  # conclut « le service est tombe » la ou il faut lire « il n'y a plus de
  # route, et c'est voulu ».
  #
  # Verifie avant retrait : plus aucun workflow n8n n'appelle ce nom (n8n
  # l'appelle desormais en http://gabelle.pantagruweb.club:8000, filtre par
  # pare-feu au seul cartons). Les seules occurrences restantes sont
  # documentaires et historiques.
  gabelle_cnames = {
    nhuitn  = "nhuitn"
    panurge = "panurge"
    papiers = "papiers"
  }

  # Configuration des enregistrements CNAME pointant vers GitHub Pages
  github_pages_cnames = {
    kiosque = "kiosque"
    status  = "status"
  }

  # Cible commune pour les enregistrements gabelle
  gabelle_target = "gabelle.pantagruweb.club"
  github_target  = "constructions-incongrues.github.io"
}
