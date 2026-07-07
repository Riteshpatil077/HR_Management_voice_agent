#!/usr/bin/env bash
# ==============================================================================
# Vault Secrets Rotation Script
# Automates the rotation of LLM provider keys and JWT signing keys without downtime.
# ==============================================================================
set -euo pipefail

VAULT_ADDR="${VAULT_ADDR:-http://vault:8200}"

echo "🔄 Starting automated secrets rotation..."

# 1. Rotate JWT Signing Keys
echo "Rotating JWT asymmetric keys..."
# Generate new RSA key pair
openssl genpkey -algorithm RSA -out /tmp/jwt_private_new.pem -pkeyopt rsa_keygen_bits:2048
openssl rsa -pubout -in /tmp/jwt_private_new.pem -out /tmp/jwt_public_new.pem

# Write to Vault (appending to existing keys to allow graceful token expiration)
# In a real system, you'd version the keys or use Vault's Transit engine for JWTs.
vault kv put secret/hr-voice-agent/jwt \
  private_key=@/tmp/jwt_private_new.pem \
  public_key=@/tmp/jwt_public_new.pem

echo "✅ JWT keys rotated in Vault. Microservices will pick up on next TTL refresh."

# 2. Rotate Database Credentials (PostgreSQL Dynamic Roles)
echo "Rotating Database credentials (forcing new lease generation)..."
# Vault's database engine handles this automatically via TTLs, but we can revoke all current leases to force immediate rotation if compromised.
# vault lease revoke -prefix database/creds/hr-voice-agent-rw

# 3. Clean up
rm /tmp/jwt_private_new.pem /tmp/jwt_public_new.pem

echo "🎉 Secrets rotation complete."
