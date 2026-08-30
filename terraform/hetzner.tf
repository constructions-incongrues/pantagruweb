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

# Adresse publique de cartons, seul appelant legitime des services internes de
# gabelle. Les deux machines sont dans des datacentres differents et n'ont
# aucun reseau prive : le trafic passe par l'internet public.
locals {
  cartons_ipv4 = "37.27.5.164/32"
}

# ATTENTION — LIRE AVANT D'APPLIQUER
#
# Un pare-feu Hetzner Cloud est en REFUS PAR DEFAUT en entree des qu'il est
# attache. Tout port absent de ce fichier devient injoignable, SSH compris.
# Les regles ci-dessous enumerent donc l'integralite de ce qui ecoute
# publiquement sur gabelle, releve le 2026-08-30 :
#
#   TCP 22 80 443 8120   UDP 443
#
# Avant d'ajouter un service qui ecoute publiquement, ajouter sa regle ICI
# d'abord. Sinon il sera silencieusement injoignable.
resource "hcloud_firewall" "gabelle" {
  name = "gabelle"

  rule {
    description = "SSH"
    direction   = "in"
    protocol    = "tcp"
    port        = "22"
    source_ips  = ["0.0.0.0/0", "::/0"]
  }

  rule {
    description = "HTTP (Traefik)"
    direction   = "in"
    protocol    = "tcp"
    port        = "80"
    source_ips  = ["0.0.0.0/0", "::/0"]
  }

  rule {
    description = "HTTPS (Traefik)"
    direction   = "in"
    protocol    = "tcp"
    port        = "443"
    source_ips  = ["0.0.0.0/0", "::/0"]
  }

  rule {
    description = "HTTP/3 QUIC (Traefik)"
    direction   = "in"
    protocol    = "udp"
    port        = "443"
    source_ips  = ["0.0.0.0/0", "::/0"]
  }

  # Agent Komodo. Ouvert au monde aujourd'hui — cette regle preserve l'etat
  # existant, elle ne l'aggrave pas. Le restreindre a cartons est une
  # amelioration reelle mais distincte de ce change : si cartons n'est pas son
  # seul client, Komodo perdrait la main sur gabelle. A instruire a part.
  rule {
    description = "Komodo periphery"
    direction   = "in"
    protocol    = "tcp"
    port        = "8120"
    source_ips  = ["0.0.0.0/0", "::/0"]
  }

  # API ytdl-server. AUCUNE AUTHENTIFICATION : ni jeton, ni cle, ni controle
  # d'acces sur /jobs, /config, /meta, /health. Cette regle est la SEULE chose
  # qui empeche n'importe qui de faire telecharger des URL arbitraires par le
  # serveur, vers un stockage que l'association paie.
  # Ne pas elargir cette source sans avoir d'abord authentifie l'API.
  rule {
    description = "ytdl-server API (cartons uniquement)"
    direction   = "in"
    protocol    = "tcp"
    port        = "8000"
    source_ips  = [local.cartons_ipv4]
  }
}

resource "hcloud_firewall_attachment" "gabelle" {
  firewall_id = hcloud_firewall.gabelle.id
  server_ids  = [data.hcloud_server.gabelle.id]
}
