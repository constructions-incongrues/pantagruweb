# Configuration du provider avec les credentials
provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

# Variables
variable "cloudflare_api_token" {
  description = "Token API Cloudflare"
  type        = string
  sensitive   = true
}

variable "domain_name" {
  description = "Nom de domaine principal"
  type        = string
  default     = "example.com"
}

variable "zone_id" {
  description = "ID de la zone Cloudflare"
  type        = string
}

variable "cloudflare_account_id" {
  description = "ID du compte Cloudflare"
  type        = string
}
# Data source pour récupérer les informations de la zone
data "cloudflare_zone" "main" {
  zone_id = var.zone_id
}

# Enregistrement CNAME
resource "cloudflare_record" "nhuitn" {
  zone_id = data.cloudflare_zone.main.id
  name    = "nhuitn"
  content = "gabelle.pantagruweb.club"
  type    = "CNAME"
  ttl     = 300
  proxied = false
}

# Outputs
output "zone_info" {
  description = "Informations sur la zone"
  value = {
    zone_id = data.cloudflare_zone.main.id
    name    = data.cloudflare_zone.main.name
    status  = data.cloudflare_zone.main.status
  }
}
