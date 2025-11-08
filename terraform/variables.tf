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
