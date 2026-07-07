#!/usr/bin/env bash
# ==============================================================================
# Vault PKI Engine Setup
# Configures an internal CA for mTLS between microservices.
# ==============================================================================
set -euo pipefail

VAULT_ADDR="${VAULT_ADDR:-http://vault:8200}"
PKI_MOUNT="pki"
DOMAIN="hr-voice-agent.internal"

echo "[INFO] Enabling PKI secrets engine..."
vault secrets enable -path="${PKI_MOUNT}" pki || true

echo "[INFO] Setting max TTL for root CA (10 years)..."
vault secrets tune -max-lease-ttl=87600h "${PKI_MOUNT}"

echo "[INFO] Generating root CA..."
vault write -format=json "${PKI_MOUNT}/root/generate/internal" \
  common_name="${DOMAIN} Root CA" \
  issuer_name="root-${DOMAIN}" \
  ttl=87600h \
  key_type=rsa \
  key_bits=4096 \
  | jq -r '.data.certificate' > /tmp/root-ca.crt

echo "[INFO] Setting CRL and issuing URLs..."
vault write "${PKI_MOUNT}/config/urls" \
  issuing_certificates="${VAULT_ADDR}/v1/${PKI_MOUNT}/ca" \
  crl_distribution_points="${VAULT_ADDR}/v1/${PKI_MOUNT}/crl"

echo "[INFO] Enabling intermediate PKI engine..."
vault secrets enable -path="${PKI_MOUNT}_int" pki || true
vault secrets tune -max-lease-ttl=43800h "${PKI_MOUNT}_int"

echo "[INFO] Generating intermediate CA CSR..."
vault write -format=json "${PKI_MOUNT}_int/intermediate/generate/internal" \
  common_name="${DOMAIN} Intermediate CA" \
  issuer_name="intermediate-${DOMAIN}" \
  key_type=rsa \
  key_bits=4096 \
  | jq -r '.data.csr' > /tmp/pki-int.csr

echo "[INFO] Signing intermediate CA with root..."
vault write -format=json "${PKI_MOUNT}/root/sign-intermediate" \
  issuer_ref="root-${DOMAIN}" \
  csr=@/tmp/pki-int.csr \
  format=pem_bundle \
  ttl=43800h \
  | jq -r '.data.certificate' > /tmp/intermediate.cert.pem

echo "[INFO] Importing signed intermediate certificate..."
vault write "${PKI_MOUNT}_int/intermediate/set-signed" \
  certificate=@/tmp/intermediate.cert.pem

echo "[INFO] Creating PKI role for hr-voice-agent services..."
vault write "${PKI_MOUNT}_int/roles/hr-voice-agent" \
  issuer_ref="$(vault read -field=default ${PKI_MOUNT}_int/config/issuers)" \
  allowed_domains="${DOMAIN}" \
  allow_subdomains=true \
  allow_bare_domains=false \
  max_ttl=720h \
  ttl=72h \
  generate_lease=true \
  require_cn=false \
  server_flag=true \
  client_flag=true

echo "[✅] Vault PKI engine configured. Intermediate CA ready."
echo "[INFO] Root CA certificate saved to /tmp/root-ca.crt"
