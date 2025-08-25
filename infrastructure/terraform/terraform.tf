terraform {
  backend "remote" {
    hostname = "app.terraform.io"
    organization = "constructions-incongrues"

    workspaces {
      name = "superlarsen"
    }
  }

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }

    hcloud = {
      source = "hetznercloud/hcloud"
      version = "1.52.0"
    }
  }
  required_version = ">= 1.0"
}