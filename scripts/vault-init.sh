#!/usr/bin/env sh
# =============================================================================
# Vault Dev-Mode Initialisation Script
# Runs once at container startup to seed secrets for local development.
# =============================================================================
set -e

echo "⏳ Waiting for Vault to be ready..."
until vault status > /dev/null 2>&1; do
  sleep 2
done
echo "✅ Vault is ready."

# Enable KV v2 secrets engine at 'secret/'
vault secrets enable -path=secret kv-v2 2>/dev/null || echo "KV v2 already enabled."

# Write placeholder secrets used by the platform
vault kv put secret/hr-voice-agent/openai \
  api_key="${OPENAI_API_KEY:-sk-placeholder}" \
  model="gpt-4o" \
  mini_model="gpt-4o-mini"

vault kv put secret/hr-voice-agent/anthropic \
  api_key="${ANTHROPIC_API_KEY:-sk-ant-placeholder}" \
  model="claude-3-5-sonnet-20241022"

vault kv put secret/hr-voice-agent/gemini \
  api_key="${GEMINI_API_KEY:-placeholder}" \
  model="gemini-1.5-flash"

vault kv put secret/hr-voice-agent/deepgram \
  api_key="${DEEPGRAM_API_KEY:-placeholder}"

vault kv put secret/hr-voice-agent/elevenlabs \
  api_key="${ELEVENLABS_API_KEY:-placeholder}"

vault kv put secret/hr-voice-agent/database \
  url="postgresql+asyncpg://hrvoice:ritu123@postgres:5432/hrvoice"

vault kv put secret/hr-voice-agent/jwt \
  secret_key="dev-secret-change-me-in-production-32chars!!"

echo "✅ Vault initialisation complete."
