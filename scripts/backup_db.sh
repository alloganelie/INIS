#!/bin/sh
# Sauvegarde de la base PostgreSQL avec rotation (§20, ARCHITECTURE.md §1.2)
set -eu

BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%SZ")
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-inis}"
POSTGRES_DB="${POSTGRES_DB:-inis_db}"

mkdir -p "${BACKUP_DIR}"
BACKUP_FILE="${BACKUP_DIR}/inis_db_${TIMESTAMP}.sql.gz"

echo "Sauvegarde de la base ${POSTGRES_DB} sur ${POSTGRES_HOST}:${POSTGRES_PORT}..."
pg_dump -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" | gzip > "${BACKUP_FILE}"
echo "Sauvegarde créée : ${BACKUP_FILE}"

echo "Nettoyage des sauvegardes de plus de ${RETENTION_DAYS} jours..."
find "${BACKUP_DIR}" -name "inis_db_*.sql.gz" -type f -mtime +"${RETENTION_DAYS}" -delete
echo "Rotation terminée."

