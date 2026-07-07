#!/usr/bin/env bash
# ==============================================================================
# Chaos Engineering Helper Script
# Used by the GitHub Actions workflow to capture baselines and validate SLOs.
# ==============================================================================
set -euo pipefail

PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"
ACTION="${1:-}"

if [[ "$ACTION" == "--capture-baseline" ]]; then
  echo "📊 Capturing baseline metrics from Prometheus..."
  # Fetch P99 Latency
  P99=$(curl -s "${PROMETHEUS_URL}/api/v1/query?query=histogram_quantile(0.99,sum(rate(http_request_duration_seconds_bucket[5m]))by(le))" | jq -r '.data.result[0].value[1] // 0')
  # Fetch Error Rate
  ERRORS=$(curl -s "${PROMETHEUS_URL}/api/v1/query?query=sum(rate(http_request_duration_seconds_count{status=~\"5..\"}[5m]))/sum(rate(http_request_duration_seconds_count[5m]))" | jq -r '.data.result[0].value[1] // 0')
  
  echo "{" > chaos-report.json
  echo "  \"baseline\": {" >> chaos-report.json
  echo "    \"p99_latency_seconds\": $P99," >> chaos-report.json
  echo "    \"error_rate\": $ERRORS" >> chaos-report.json
  echo "  }" >> chaos-report.json
  echo "}" >> chaos-report.json
  
  echo "Baseline captured: P99=${P99}s, ErrorRate=${ERRORS}"

elif [[ "$ACTION" == "--validate-slo" ]]; then
  echo "⚖️ Validating SLOs post-chaos recovery..."
  # Wait for stabilization window
  sleep 60
  
  P99=$(curl -s "${PROMETHEUS_URL}/api/v1/query?query=histogram_quantile(0.99,sum(rate(http_request_duration_seconds_bucket[5m]))by(le))" | jq -r '.data.result[0].value[1] // 0')
  
  if (( $(echo "$P99 > 2.0" | bc -l) )); then
    echo "❌ SLO Violation: P99 latency failed to recover. Current: ${P99}s (Target: < 2.0s)"
    exit 1
  fi
  
  echo "✅ SLO Validated: System successfully recovered from chaos injection. P99=${P99}s"
else
  echo "Usage: ./chaos_test.sh [--capture-baseline | --validate-slo]"
  exit 1
fi
