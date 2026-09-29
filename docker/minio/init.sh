#!/bin/sh
# INIS — provisionnement du stockage objet S3-compatible (§4.3).
#
# Crée le bucket d'artefacts au premier démarrage. Le service compose utilise
# RustFS (`rustfs/rustfs:1.0.0-rc.5`), que le module de tests pin déjà ; l'image
# MinIO historique n'est plus distribuée sur Quay.io. Le script n'utilise que
# l'API S3, il fonctionne donc avec l'un comme avec l'autre :
#
#   docker exec -e S3_ACCESS_KEY=... -e S3_SECRET_KEY=... inis-object-storage \
#       sh /docker/minio/init.sh
#
# Variables attendues (voir .env.example) :
#   S3_ENDPOINT       ex. http://object-storage:9000
#   S3_ACCESS_KEY     identifiant (RUSTFS_ACCESS_KEY pour RustFS)
#   S3_SECRET_KEY     secret     (RUSTFS_SECRET_KEY pour RustFS)
#   S3_BUCKET         bucket à créer (défaut : inis-artifacts)
set -eu

S3_ENDPOINT="${S3_ENDPOINT:-http://object-storage:9000}"
S3_BUCKET="${S3_BUCKET:-inis-artifacts}"
S3_REGION="${S3_REGION:-eu-west-3}"

if [ -z "${S3_ACCESS_KEY:-}" ] || [ -z "${S3_SECRET_KEY:-}" ]; then
    echo "init.sh: S3_ACCESS_KEY et S3_SECRET_KEY sont requis" >&2
    exit 1
fi

export AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY}"
export AWS_SECRET_ACCESS_KEY="${S3_SECRET_KEY}"
export AWS_DEFAULT_REGION="${S3_REGION}"

# Attente active : RustFS/MinIO répondent sur le port avant que la table de
# routage S3 ne soit prête, un premier appel trop tôt échoue en connexion.
attempt=0
until aws --endpoint-url "${S3_ENDPOINT}" s3 ls >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "${attempt}" -ge 30 ]; then
        echo "init.sh: stockage objet injoignable sur ${S3_ENDPOINT}" >&2
        exit 1
    fi
    sleep 2
done

if aws --endpoint-url "${S3_ENDPOINT}" s3api head-bucket --bucket "${S3_BUCKET}" >/dev/null 2>&1; then
    echo "init.sh: bucket ${S3_BUCKET} deja present"
    exit 0
fi

aws --endpoint-url "${S3_ENDPOINT}" s3 mb "s3://${S3_BUCKET}" --region "${S3_REGION}"
echo "init.sh: bucket ${S3_BUCKET} cree sur ${S3_ENDPOINT}"

