#!/usr/bin/env bash
# ==============================================================================
# Smoke Test Script
# Validates core platform endpoints after a deployment.
# Usage: ./smoke_test.sh https://staging.api.yourdomain.com
# Requires: SMOKE_TEST_JWT environment variable
# ==============================================================================
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
TOKEN="${SMOKE_TEST_JWT:-}"

if [[ -z "$TOKEN" ]]; then
  echo "❌ Error: SMOKE_TEST_JWT environment variable is required."
  exit 1
fi

echo "🔍 Starting Smoke Tests against ${BASE_URL}..."

# 1. Health Probe
echo "Testing /health..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/health")
if [[ "$HTTP_STATUS" != "200" ]]; then
  echo "❌ Health check failed. Status: $HTTP_STATUS"
  exit 1
fi
echo "✅ Health check passed."

# 2. HR Service: Get Departments
echo "Testing HR Service..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer ${TOKEN}" \
  "${BASE_URL}/v1/hr/departments")
if [[ "$HTTP_STATUS" != "200" ]]; then
  echo "❌ HR Service check failed. Status: $HTTP_STATUS"
  exit 1
fi
echo "✅ HR Service passed."

# 3. Interview Service: Create Mock Interview
echo "Testing Interview Service..."
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: smoke-test-$(date +%s)" \
  -d '{"candidate_name": "Smoke Test", "candidate_email": "smoke@test.com", "role": "Tester"}' \
  "${BASE_URL}/v1/interviews/schedule")

BODY=$(echo "$RESPONSE" | head -n -1)
STATUS=$(echo "$RESPONSE" | tail -n 1)

if [[ "$STATUS" != "200" ]]; then
  echo "❌ Interview scheduling failed. Status: $STATUS | Response: $BODY"
  exit 1
fi
echo "✅ Interview Service passed."

echo "🎉 All smoke tests passed successfully!"
