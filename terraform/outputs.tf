output "zone_info" {
  description = "Informations sur la zone"
  value = {
    zone_id = data.cloudflare_zone.main.id
    name    = data.cloudflare_zone.main.name
    status  = data.cloudflare_zone.main.status
  }
}
