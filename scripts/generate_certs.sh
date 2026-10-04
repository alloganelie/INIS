#!/bin/sh
# Génération de certificats mTLS auto-signés pour l'authentification inter-agents (§19).
set -eu

CERTS_DIR="${CERTS_DIR:-./certs}"
DAYS="${DAYS:-365}"

mkdir -p "${CERTS_DIR}"

echo "Génération de l'autorité de certification (CA)..."
openssl req -new -x509 -days "${DAYS}" -nodes \
    -out "${CERTS_DIR}/ca.crt" \
    -keyout "${CERTS_DIR}/ca.key" \
    -subj "/CN=INIS-CA/O=INIS/OU=Security"

echo "Génération du certificat serveur INIS..."
openssl req -new -nodes \
    -out "${CERTS_DIR}/server.csr" \
    -keyout "${CERTS_DIR}/server.key" \
    -subj "/CN=localhost/O=INIS/OU=API"

openssl x509 -req -days "${DAYS}" \
    -in "${CERTS_DIR}/server.csr" \
    -CA "${CERTS_DIR}/ca.crt" \
    -CAkey "${CERTS_DIR}/ca.key" \
    -CAcreateserial \
    -out "${CERTS_DIR}/server.crt"

echo "Génération du certificat agent client..."
# Le CN est l'identité de l'agent (§19.2). Il doit rester dans l'espace de
# nommage `AGENT_` que le validateur exige : un CN hors de cet espace est refusé
# (`certificate_identity_unusable`).
openssl req -new -nodes \
    -out "${CERTS_DIR}/client.csr" \
    -keyout "${CERTS_DIR}/client.key" \
    -subj "/CN=AGENT_agent-default/O=INIS/OU=Agents"

openssl x509 -req -days "${DAYS}" \
    -in "${CERTS_DIR}/client.csr" \
    -CA "${CERTS_DIR}/ca.crt" \
    -CAkey "${CERTS_DIR}/ca.key" \
    -CAcreateserial \
    -out "${CERTS_DIR}/client.crt"

rm -f "${CERTS_DIR}"/*.csr "${CERTS_DIR}"/*.srl
chmod 600 "${CERTS_DIR}"/*.key
echo "Certificats mTLS générés dans ${CERTS_DIR}/"

