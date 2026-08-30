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
  gabelle_cnames = {
    nhuitn  = "nhuitn"
    panurge = "panurge"
    papiers = "papiers"
    ytdl    = "ytdl"
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
