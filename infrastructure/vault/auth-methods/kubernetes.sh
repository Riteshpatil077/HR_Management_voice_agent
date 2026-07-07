#!/usr/bin/env bash
# ==============================================================================
# Vault Kubernetes Auth Setup
# Run this after the EKS cluster and Vault are deployed.
# ==============================================================================
set -euo pipefail

VAULT_ADDR="${VAULT_ADDR:-http://vault:8200}"
NAMESPACE="hr-voice-agent"
KUBERNETES_HOST=$(kubectl config view --raw --minify --flatten -o jsonpath='{.clusters[].cluster.server}')

echo "[INFO] Enabling Kubernetes auth method..."
vault auth enable kubernetes || true

echo "[INFO] Configuring Kubernetes auth backend..."
vault write auth/kubernetes/config \
  kubernetes_host="${KUBERNETES_HOST}" \
  kubernetes_ca_cert=@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt \
  token_reviewer_jwt="$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)"

echo "[INFO] Creating Vault roles for each microservice..."

for SERVICE in voice-service hr-service interview-service onboarding-service notification-service auth-service tenant-service analytics-service; do
  echo "[INFO] Binding ${SERVICE}..."
  vault write "auth/kubernetes/role/${SERVICE}" \
    bound_service_account_names="${SERVICE}" \
    bound_service_account_namespaces="${NAMESPACE}" \
    policies="hr-voice-agent,${SERVICE}" \
    ttl="1h" \
    max_ttl="24h"
done

echo "[INFO] Creating service-specific policies (override secrets paths)..."

# Example: voice-service gets extra access to transit engine
cat <<EOF | vault policy write voice-service -
path "transit/encrypt/hr-voice-agent-pii" { capabilities = ["create","update"] }
path "transit/decrypt/hr-voice-agent-pii" { capabilities = ["create","update"] }
path "secret/data/hr-voice-agent/voice-service/*" { capabilities = ["read"] }
EOF

echo "[✅] Vault Kubernetes auth configured successfully."
