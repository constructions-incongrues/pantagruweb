# Configuration du provider avec les credentials
provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

# Data source pour récupérer les informations de la zone
data "cloudflare_zone" "main" {
  zone_id = var.zone_id
}

# Enregistrement A pour gabelle (serveur principal)
resource "cloudflare_record" "gabelle" {
  zone_id = local.zone_id
  name    = "gabelle"
  content = data.hcloud_server.gabelle.ipv4_address
  type    = "A"
  ttl     = local.default_ttl
  proxied = local.default_proxied
}

# Enregistrements CNAME pointant vers gabelle
resource "cloudflare_record" "gabelle_cnames" {
  for_each = local.gabelle_cnames

  zone_id = local.zone_id
  name    = each.value
  content = local.gabelle_target
  type    = "CNAME"
  ttl     = local.default_ttl
  proxied = local.default_proxied
}

# Enregistrements CNAME pointant vers GitHub Pages
resource "cloudflare_record" "github_pages_cnames" {
  for_each = local.github_pages_cnames

  zone_id = local.zone_id
  name    = each.value
  content = local.github_target
  type    = "CNAME"
  ttl     = local.default_ttl
  proxied = local.default_proxied
}

# Enregistrement wildcard pour gargamelle
resource "cloudflare_record" "gargamelle_wildcard" {
  zone_id = local.zone_id
  name    = "*.gargamelle"
  content = local.gabelle_target
  type    = "CNAME"
  ttl     = local.default_ttl
  proxied = local.default_proxied
}

# Enregistrement wildcard principal
resource "cloudflare_record" "wildcard" {
  zone_id = local.zone_id
  name    = "*"
  content = local.gabelle_target
  type    = "CNAME"
  ttl     = local.default_ttl
  proxied = local.default_proxied
}
