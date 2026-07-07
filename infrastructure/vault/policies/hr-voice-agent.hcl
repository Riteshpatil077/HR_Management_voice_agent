# ==============================================================================
# Vault Policy — hr-voice-agent
# Grants microservices access to secrets, PKI, and transit encryption engine
# ==============================================================================

# ── Application Secrets ────────────────────────────────────────────────────────
path "secret/data/hr-voice-agent/*" {
  capabilities = ["read", "list"]
}

path "secret/metadata/hr-voice-agent/*" {
  capabilities = ["read", "list"]
}

# ── PKI — Issue certificates for service mTLS ─────────────────────────────────
path "pki/issue/hr-voice-agent" {
  capabilities = ["create", "update"]
}

path "pki/cert/ca" {
  capabilities = ["read"]
}

# ── Transit Encryption Engine — for at-rest field encryption (PII) ────────────
path "transit/encrypt/hr-voice-agent-pii" {
  capabilities = ["create", "update"]
}

path "transit/decrypt/hr-voice-agent-pii" {
  capabilities = ["create", "update"]
}

path "transit/rewrap/hr-voice-agent-pii" {
  capabilities = ["create", "update"]
}

# ── Database Dynamic Credentials (PostgreSQL) ─────────────────────────────────
path "database/creds/hr-voice-agent-rw" {
  capabilities = ["read"]
}

path "database/creds/hr-voice-agent-ro" {
  capabilities = ["read"]
}

# ── AWS Dynamic Credentials (STS for S3 access) ───────────────────────────────
path "aws/creds/hr-voice-agent-s3" {
  capabilities = ["read"]
}

# ── Token Self-Renewal ─────────────────────────────────────────────────────────
path "auth/token/renew-self" {
  capabilities = ["update"]
}

path "auth/token/lookup-self" {
  capabilities = ["read"]
}

# ── System Health Check ────────────────────────────────────────────────────────
path "sys/health" {
  capabilities = ["read", "sudo"]
}
