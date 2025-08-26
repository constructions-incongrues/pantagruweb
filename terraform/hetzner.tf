variable "hcloud_token" {
  description = "Hetzner Cloud API token"
  type        = string
  sensitive   = true
}

provider "hcloud" {
  token = var.hcloud_token
}

data "hcloud_server" "gabelle" {
  name = "gabelle"
}
