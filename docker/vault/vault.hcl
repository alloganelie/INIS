# INIS — configuration Vault (§19, gestion des secrets).
#
# Mode *dev* uniquement : stockage en mémoire, jeton root connu, écoute en
# clair. C'est ce mode que la pile compose utilise pour rester reproductible.
# En production : stockage Raft, `tls_disable = 0`, jeton approle, scellement
# manuel — la configuration correspondante doit être fournie par la plateforme
# d'exécution, jamais versionnée avec ses secrets.

storage "inmem" {
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true
}

# `api_addr` est l'adresse annoncée aux clients (le nom du service compose).
api_addr     = "http://vault:8200"
cluster_addr = "http://vault:8201"

# `dev` sert les secrets sans scellement : à ne jamais exposer au-delà du
# réseau local du poste de développement.
ui            = true
disable_mlock = true

