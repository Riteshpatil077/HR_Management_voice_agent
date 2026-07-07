# Incident Response Runbook

This document outlines the standard operating procedures for resolving common alerts triggered by the HR Voice Agent monitoring stack.

## 🚨 Alert: `VoiceServiceHighErrorRate`
**Condition:** Voice service HTTP 5xx error rate > 1% over 5 minutes.
**Impact:** End-users are experiencing dropped calls or inability to initiate interviews.

### Resolution Steps:
1. **Check LLM Provider Status:** Look at the Grafana `LLM Metrics` dashboard. Are we seeing 429 (Rate Limit) or 5xx from OpenAI/Anthropic?
   - *Fix:* Ensure the `LLMRouter` failover mechanism is functioning. Manually force the circuit breaker open for the failing provider using the Kong admin API if necessary.
2. **Check Database Connections:** Are pods crash-looping with SQLAlchemy `TimeoutError`?
   - *Fix:* Check RDS Aurora metrics in AWS Console. Ensure the Serverless v2 capacity hasn't hit its max limit (64 ACU). If so, identify the query causing the load (using RDS Performance Insights) and kill the PID.
3. **Check Vault:** If the service cannot fetch dynamic credentials, it will throw 500s.
   - *Fix:* Check the Vault HA cluster status `kubectl get pods -n hr-voice-agent -l app=vault`. Restart the active Vault node if it is deadlocked.

## 🚨 Alert: `RabbitMQQueueDepthHigh`
**Condition:** `call.analytics` queue has > 1000 pending messages for 10 minutes.
**Impact:** Post-call analytics (cost calculations, interview transcripts) are delayed. No impact to live calling.

### Resolution Steps:
1. **Verify KEDA Autoscaling:** Check if KEDA is successfully scaling the `analytics-service` or `voice-service`.
   - `kubectl get hpa -n hr-voice-agent`
   - *Fix:* If KEDA is blocked due to node capacity, check Karpenter logs in the `kube-system` namespace to see why new nodes aren't provisioning (e.g., AWS EC2 instance limits reached).
2. **Check Outbox Relay Backlog:** If the relay worker is blocked, it might be pushing messages too slowly.
   - *Fix:* Scale the `outbox-relay` deployment or investigate if a poison pill message is causing the worker to crash-loop.

## 🚨 Alert: `LLMDailyCostExceeded`
**Condition:** A specific tenant has spent > $500 on LLM inference today.
**Impact:** Potential budget overrun, prompt injection attack, or infinite loop bug.

### Resolution Steps:
1. **Identify the Tenant:** Check the Slack alert payload for the `tenant_id`.
2. **Investigate Call Logs:** Query Loki for the tenant's trace IDs to see if a single call is spinning in a loop, or if they are initiating thousands of legitimate calls.
3. **Action:** If malicious or anomalous, temporarily disable the tenant via the Tenant Service API:
   `curl -X PATCH -H "Authorization: Bearer <admin-token>" https://api.yourdomain.com/v1/tenants/{tenant_id}/status -d '{"status":"suspended"}'`
