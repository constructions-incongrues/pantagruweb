locals {
  # Valeurs communes pour les enregistrements DNS
  default_ttl     = 300
  default_proxied = false
  zone_id         = data.cloudflare_zone.main.id

  # Configuration des enregistrements CNAME pointant vers gabelle
  gabelle_cnames = {
    archive = "archive"
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
